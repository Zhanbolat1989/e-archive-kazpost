import hashlib
import io
import json
import zipfile
from collections import defaultdict
from datetime import datetime, date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import extract, func
from sqlalchemy.orm import Session, load_only

from ..db import get_db
from ..models import (
    User, Role, Document, DocStatus, Case, CaseStatus,
    RegCard, DestructionAct, DestructionActItem, ActStatus,
)
from ..schemas import (
    RegCardOut, RegCardUpdate,
    DestructionActCreate, DestructionActOut, DestructionActDetail, DestructionActUpdate,
)
from ..security import get_current_user, require_roles
from ..services import search as search_svc
from ..services import access, storage, audit
from ..services import forms as forms_svc
from ..services import packages, printpack
from ..services import xlsx

router = APIRouter(prefix="/api", tags=["lifecycle"])


# ---------- ЭРКК ----------
@router.get("/regcards/on-control", response_model=list[RegCardOut])
def on_control(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return (db.query(RegCard)
            .filter(RegCard.on_control.is_(True), RegCard.executed_at.is_(None))
            .order_by(RegCard.due_date.asc().nullslast()).all())


@router.get("/regcards/{doc_id}", response_model=RegCardOut)
def get_card(doc_id: str, db: Session = Depends(get_db),
             _: User = Depends(get_current_user)):
    card = db.query(RegCard).filter(RegCard.document_id == doc_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Карточка не найдена")
    return card


@router.patch("/regcards/{doc_id}", response_model=RegCardOut)
def update_card(doc_id: str, payload: RegCardUpdate,
                db: Session = Depends(get_db),
                _: User = Depends(require_roles(Role.admin, Role.archivist))):
    card = db.query(RegCard).filter(RegCard.document_id == doc_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Карточка не найдена")
    for f, v in payload.model_dump(exclude_none=True).items():
        setattr(card, f, v)
    db.commit()
    db.refresh(card)
    return card


# ---------- Акты о выделении к уничтожению ----------
def _act_out(act: DestructionAct) -> DestructionActOut:
    out = DestructionActOut.model_validate(act)
    out.items_count = len(act.items)
    return out


@router.get("/destruction-acts", response_model=list[DestructionActOut])
def list_acts(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    acts = (db.query(DestructionAct)
            .order_by(DestructionAct.created_at.desc()).all())
    return [_act_out(a) for a in acts]


@router.post("/destruction-acts", response_model=DestructionActDetail, status_code=201)
def create_act(payload: DestructionActCreate,
               db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.admin, Role.archivist))):
    today = date.today()
    docs = (db.query(Document)
            .filter(Document.id.in_(payload.document_ids)).all())
    if not docs:
        raise HTTPException(status_code=400, detail="Документы не найдены")
    # В акт попадают только документы с истёкшим сроком (и не постоянного хранения)
    bad = [d.title for d in docs
           if d.permanent or d.retention_until is None or d.retention_until >= today
           or d.destroyed_at is not None]
    if bad:
        raise HTTPException(
            status_code=400,
            detail="Срок хранения не истёк (или уже уничтожено): " + "; ".join(bad[:3]),
        )
    seq = db.query(DestructionAct).filter(
        DestructionAct.number.like(f"АУ-{today.year}/%")).count() + 1
    act = DestructionAct(
        number=f"АУ-{today.year}/{seq:02d}",
        is_electronic=payload.is_electronic,
        note=payload.note,
        created_by=user.full_name or user.email,
    )
    act.items = [DestructionActItem(document_id=d.id) for d in docs]
    db.add(act)
    db.commit()
    db.refresh(act)
    return get_act(act.id, db, user)


@router.get("/destruction-acts/{act_id}", response_model=DestructionActDetail)
def get_act(act_id: str, db: Session = Depends(get_db),
            _: User = Depends(get_current_user)):
    act = db.get(DestructionAct, act_id)
    if not act:
        raise HTTPException(status_code=404, detail="Акт не найден")
    docs = [db.get(Document, i.document_id) for i in act.items]
    out = DestructionActDetail.model_validate(act)
    out.items_count = len(act.items)
    out.documents = [d for d in docs if d]
    return out


@router.patch("/destruction-acts/{act_id}", response_model=DestructionActDetail)
def update_act(act_id: str, payload: DestructionActUpdate,
               db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.admin, Role.archivist))):
    """Правка проекта акта: протокол ЦЭК (ЭК) и примечание. Утверждённый акт
    не правится — он уже основание для уничтожения."""
    act = db.get(DestructionAct, act_id)
    if not act:
        raise HTTPException(status_code=404, detail="Акт не найден")
    if act.status == ActStatus.approved:
        raise HTTPException(status_code=409, detail="Утверждённый акт не редактируется")
    changes = payload.model_dump(exclude_none=True)
    for field, value in changes.items():
        setattr(act, field, value.strip() if isinstance(value, str) else value)
    db.commit()
    audit.record(db, user, "destruction.update", "act", act.id,
                 ", ".join(changes) or "без изменений")
    return get_act(act_id, db, user)


@router.post("/destruction-acts/{act_id}/approve", response_model=DestructionActDetail)
def approve_act(act_id: str, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.admin))):
    """Утверждение акта: документы помечаются уничтоженными и удаляются из
    поискового индекса. Каталожная запись сохраняется; оригинал в WORM остаётся
    до истечения объектной блокировки."""
    act = db.get(DestructionAct, act_id)
    if not act:
        raise HTTPException(status_code=404, detail="Акт не найден")
    if act.status == ActStatus.approved:
        raise HTTPException(status_code=409, detail="Акт уже утверждён")
    if act.kind == "ecopy" and not act.commission_protocol:
        # ТС-176 п. 11.7: акт об уничтожении электронных копий утверждается
        # руководителем «по согласованию с ЦЭК (ЭК)» — без протокола комиссии
        # основания для уничтожения нет.
        raise HTTPException(
            status_code=409,
            detail="Акт об уничтожении электронных копий утверждается по согласованию "
                   "с ЦЭК (ЭК) — укажите номер и дату протокола комиссии",
        )
    today = date.today()
    touched_cases: set[str] = set()
    for item in act.items:
        doc = db.get(Document, item.document_id)
        if doc is None or doc.destroyed_at is not None:
            continue
        doc.destroyed_at = today
        doc.status_detail = f"Уничтожено по акту {act.number}"
        if doc.case_id:
            touched_cases.add(doc.case_id)
        search_svc.delete_document(doc.id)
    # Дело со всеми уничтоженными документами переводится в «Уничтожено»
    for cid in touched_cases:
        case = db.get(Case, cid)
        alive = (db.query(Document)
                 .filter(Document.case_id == cid, Document.destroyed_at.is_(None))
                 .count())
        if case and alive == 0:
            case.status = CaseStatus.destroyed
    act.status = ActStatus.approved
    act.approved_by = user.full_name or user.email
    act.approved_at = datetime.utcnow()
    db.commit()
    audit.record(db, user, "destruction.approve", "act", act.id,
                 f"{act.number}: {len(act.items)} документов")
    return get_act(act_id, db, user)


@router.get("/destruction-acts/{act_id}/pdf")
def act_pdf(act_id: str, db: Session = Depends(get_db),
            _: User = Depends(get_current_user)):
    import io

    from ..services import forms as forms_svc

    act = db.get(DestructionAct, act_id)
    if not act:
        raise HTTPException(status_code=404, detail="Акт не найден")
    docs = [db.get(Document, i.document_id) for i in act.items]
    data = forms_svc.destruction_act_pdf(act, [d for d in docs if d])
    # HTTP-заголовки — только latin-1: кириллицу из имени файла убираем.
    safe = "".join(c for c in act.number.replace("/", "-") if ord(c) < 128) or "act"
    return StreamingResponse(
        io.BytesIO(data), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="act_{safe}.pdf"'},
    )


# ---------- Сроки уничтожения: перечни по годам (ТЗ АГП п. 8) ----------
@router.get("/destruction-overview")
def destruction_overview(db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)) -> dict:
    """Три перечня, которых требует ТЗ: подлежащие уничтожению, не подлежащие
    и приближающиеся к сроку — с разбивкой по годам уничтожения.

    Год уничтожения — год, следующий за истечением срока хранения: документ
    хранится до конца своего срока, уничтожается в делопроизводстве следующего
    года (приказ № 235).
    """
    today = date.today()
    horizon = today + timedelta(days=365)
    # Только нужные колонки и только открытые роли категории: перечни строятся
    # по всему архиву, и поднимать ради них распознанный текст каждого
    # документа в память нельзя.
    docs = (access.apply(db.query(Document), db, user)
            .options(load_only(Document.id, Document.title, Document.doc_type,
                               Document.permanent, Document.retention_label,
                               Document.retention_until, Document.case_id))
            .filter(Document.destroyed_at.is_(None),
                    Document.status == DocStatus.ready)
            .all())

    def _row(d: Document) -> dict:
        return {"id": d.id, "title": d.title,
                "doc_type": d.doc_type.value if d.doc_type else "",
                "retention": "Постоянно" if d.permanent else (d.retention_label or "—"),
                "retention_until": d.retention_until.isoformat() if d.retention_until else "",
                "case_id": d.case_id or ""}

    to_destroy = [d for d in docs if not d.permanent and d.retention_until
                  and d.retention_until < today]
    approaching = [d for d in docs if not d.permanent and d.retention_until
                   and today <= d.retention_until <= horizon]
    keep = [d for d in docs if d.permanent]

    by_year: dict[int, int] = {}
    for d in to_destroy + approaching:
        year = d.retention_until.year + 1
        by_year[year] = by_year.get(year, 0) + 1

    # Уничтоженные только считаются — группировкой в базе, без загрузки строк.
    year_col = extract("year", Document.destroyed_at)
    destroyed_by_year: dict[int, int] = {
        int(y): n for y, n in
        access.apply(db.query(year_col, func.count(Document.id)), db, user)
        .filter(Document.destroyed_at.isnot(None))
        .group_by(year_col).all()
    }

    return {
        "as_of": today.isoformat(),
        "to_destroy": [_row(d) for d in sorted(to_destroy,
                                               key=lambda x: x.retention_until)],
        "approaching": [_row(d) for d in sorted(approaching,
                                                key=lambda x: x.retention_until)],
        "not_subject": [_row(d) for d in keep[:500]],
        "not_subject_total": len(keep),
        "by_destruction_year": [{"year": y, "documents": n}
                                for y, n in sorted(by_year.items())],
        "destroyed_by_year": [{"year": y, "documents": n}
                              for y, n in sorted(destroyed_by_year.items())],
    }


@router.get("/destruction-overview/xlsx")
def destruction_overview_xlsx(request: Request, db: Session = Depends(get_db),
                              user: User = Depends(get_current_user)):
    """Выгрузка перечней в Excel (п. 8)."""
    data = destruction_overview(db, user)
    rows = ([[r["title"], r["doc_type"], r["retention"], r["retention_until"],
              "подлежит уничтожению"] for r in data["to_destroy"]]
            + [[r["title"], r["doc_type"], r["retention"], r["retention_until"],
                "срок приближается"] for r in data["approaching"]]
            + [[r["title"], r["doc_type"], r["retention"], "—",
                "не подлежит уничтожению"] for r in data["not_subject"]])
    blob = xlsx.build(
        title="Документы по срокам уничтожения",
        subtitle=f"по состоянию на {data['as_of']}",
        headers=["Заголовок", "Вид документа", "Срок хранения",
                 "Хранить до", "Категория"],
        rows=rows, sheet="Сроки уничтожения",
    )
    audit.record(db, user, "destruction.export", "archive", "",
                 f"перечни по срокам: строк {len(rows)}", request=request)
    return StreamingResponse(
        io.BytesIO(blob), media_type=xlsx.MEDIA_TYPE,
        headers={"Content-Disposition":
                 f'attachment; filename="{xlsx.filename("destruction_overview")}"'},
    )


# ---------- Информационный пакет электронного дела (Фаза 5) ----------
@router.get("/cases/{case_id}/export")
def export_case(case_id: str, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.admin, Role.archivist))):
    """ZIP-пакет для передачи в госархив: файлы документов + метаданные с
    контрольными характеристиками + опись эл. дела (PDF) + контрольный лист."""
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Дело не найдено")
    docs = (db.query(Document)
            .filter(Document.case_id == case_id, Document.destroyed_at.is_(None))
            .order_by(Document.doc_date.asc().nullslast()).all())
    if not docs:
        raise HTTPException(status_code=400, detail="В деле нет документов")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        entry = packages.add_case(zf, case, docs)
        manifest = {
            "case": {"index": case.index, "title": case.title, "year": case.year,
                     "volume": case.volume, "retention": case.retention_label,
                     "exported_at": datetime.utcnow().isoformat(),
                     "exported_by": user.email},
            "documents": entry["documents"],
            "missing": entry["missing"],
        }
        zf.writestr("manifest.json",
                    json.dumps(manifest, ensure_ascii=False, indent=2))
    audit.record(db, user, "case.export", "case", case_id,
                 f"{case.index}: {len(manifest['documents'])} документов")
    safe = "".join(c for c in (case.index or "delo").replace("/", "-") if ord(c) < 128) or "delo"
    return StreamingResponse(
        io.BytesIO(buf.getvalue()), media_type="application/zip",
        headers={"Content-Disposition":
                 f'attachment; filename="case_{safe}_{case.year}.zip"'},
    )


# ---------- Печать дела (единый PDF на печать) ----------
@router.get("/cases/{case_id}/print")
def print_case(case_id: str, db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.admin, Role.archivist))):
    """Все документы дела одним PDF: титульный лист + разделитель и сам
    документ перед каждой позицией — готово к печати на принтере."""
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Дело не найдено")
    docs = (db.query(Document)
            .filter(Document.case_id == case_id, Document.destroyed_at.is_(None))
            .order_by(Document.doc_date.asc().nullslast()).all())
    if not docs:
        raise HTTPException(status_code=400, detail="В деле нет документов")

    pdf_bytes, skipped = printpack.build_print_pack(case, docs, storage.get_object)
    audit.record(db, user, "case.print", "case", case_id,
                 f"{case.index}: {len(docs)} документов"
                 + (f", пропущено: {len(skipped)}" if skipped else ""))
    safe = "".join(c for c in (case.index or "delo").replace("/", "-") if ord(c) < 128) or "delo"
    headers = {"Content-Disposition": f'attachment; filename="print_{safe}_{case.year}.pdf"'}
    if skipped:
        # Заголовок — только диагностика для фронтенда; не латиница/спецсимволы убраны.
        headers["X-Print-Skipped"] = str(len(skipped))
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)


# ---------- Акт миграции (прил. 1) ----------
@router.get("/migration-act/pdf")
def migration_act(db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    docs = (db.query(Document)
            .filter(Document.pdfa_key != "", Document.destroyed_at.is_(None)).all())
    if not docs:
        raise HTTPException(status_code=400,
                            detail="Мигрированных (PDF/A) документов нет")
    data = forms_svc.migration_act_pdf(docs)
    return StreamingResponse(
        io.BytesIO(data), media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="migration_act.pdf"'},
    )


# ---------- Проверка наличия и состояния (прил. 25/26) ----------
@router.post("/inventory-check")
def inventory_check(db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.admin, Role.archivist))):
    """Сверка SHA-256 каталога с объектами в WORM-хранилище."""
    docs = (db.query(Document)
            .filter(Document.status == DocStatus.ready,
                    Document.destroyed_at.is_(None)).all())
    results = []
    for d in docs:
        try:
            blob = storage.get_object(d.storage_key)
            actual = hashlib.sha256(blob).hexdigest()
            ok = actual == d.checksum_sha256
            note = "" if ok else "контрольная характеристика не совпадает"
        except Exception as exc:  # noqa: BLE001
            ok, note = False, f"объект недоступен: {exc}"
        results.append({"id": d.id, "number": d.doc_number, "title": d.title,
                        "ok": ok, "note": note})
    bad = sum(1 for r in results if not r["ok"])
    audit.record(db, user, "inventory.check", "archive", "",
                 f"проверено {len(results)}, расхождений {bad}")
    return {"checked": len(results), "ok": len(results) - bad, "mismatch": bad,
            "results": results}


@router.post("/inventory-check/pdf")
def inventory_check_pdf(db: Session = Depends(get_db),
                        user: User = Depends(require_roles(Role.admin, Role.archivist))):
    report = inventory_check(db, user)
    data = forms_svc.inventory_check_act_pdf(report["results"])
    return StreamingResponse(
        io.BytesIO(data), media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="inventory_check.pdf"'},
    )


# Журнал аудита переехал в routers/audit.py (GET /api/audit с фильтрами по
# пользователю, типу действия и результату — раздел 14 ТС). Прежний эндпоинт
# здесь объявлял тот же путь и, будучи подключённым раньше, перекрывал новый.


# ---------- Книга учёта поступления и выбытия ----------
@router.get("/ledger")
def ledger(year: int | None = None, db: Session = Depends(get_db),
           _: User = Depends(get_current_user)) -> dict:
    docs = db.query(Document).filter(Document.status == DocStatus.ready).all()
    months: dict[str, dict] = defaultdict(lambda: {"in": 0, "out": 0})
    for d in docs:
        if year and d.created_at.year != year:
            pass
        else:
            months[d.created_at.strftime("%Y-%m")]["in"] += 1
        if d.destroyed_at and (not year or d.destroyed_at.year == year):
            months[d.destroyed_at.strftime("%Y-%m")]["out"] += 1
    rows = [{"month": m, "received": v["in"], "removed": v["out"]}
            for m, v in sorted(months.items())]
    total_in = sum(r["received"] for r in rows)
    total_out = sum(r["removed"] for r in rows)
    return {"rows": rows, "total_received": total_in, "total_removed": total_out,
            "in_archive": total_in - total_out}
