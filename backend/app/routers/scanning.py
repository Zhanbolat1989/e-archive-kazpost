"""Модуль «Сканирование» (ТС-176 п. 4.5) и учёт работ по делам (п. 5.5, разд. 8–12).

ТС требует вводить сканы «согласно типам документов, определённых номенклатурой
дел»: архивариус выбирает статью номенклатуры и том дела, а виды документов,
которые можно принять в это дело, задаёт сама статья. Так опись дела не
засоряется документами чужого вида, а срок хранения скана берётся из той
номенклатуры, по которой дело формировалось.

Второе назначение — учёт работ оцифровки. ТС называет пять этапов (НТО,
экспертиза ценности, сканирование, прошивка, оцифровка) и принимает услугу по
акту с объёмом оказанных услуг: отметки этапов по делам и дают этот объём.
"""
import io
from datetime import date, datetime, time, timedelta

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..ingest import process_document
from ..models import (
    Case, CaseStatus, CaseWorkStage, Document, NOMENCLATURE_STATUSES, NomenclatureItem,
    Role, User, WORK_STAGES,
)
from ..retention import compute_until
from ..schemas import CaseOut, ScanCaseCreate, WorkStageOut, WorkStageUpdate
from ..security import get_current_user, require_roles
from ..services import audit, xlsx
from ..services import ecopies as copy_rules
from ..services import scanning as rules
from .cases import _with_count
from .documents import create_document_record

router = APIRouter(prefix="/api/scanning", tags=["scanning"])

DRAFT = NOMENCLATURE_STATUSES[0]
# Файлов за один запрос. Партия больше отправляется несколькими запросами:
# обрыв соединения не должен терять весь ввод, а память сервера — держать
# сотни сканов разом до постановки в очередь распознавания.
MAX_FILES_PER_REQUEST = 20


@router.get("/articles")
def articles(year: int, db: Session = Depends(get_db),
             _: User = Depends(get_current_user)) -> list[dict]:
    """Статьи номенклатуры года с томами дел — отправная точка ввода сканов.

    Проекты номенклатуры не выдаются: дело по несогласованной статье не
    формируется. Архивные статьи выдаются — старый архив оцифровывается именно
    по номенклатуре своего года."""
    items = (db.query(NomenclatureItem)
             .filter(NomenclatureItem.year == year, NomenclatureItem.status != DRAFT)
             .order_by(NomenclatureItem.index).all())
    ids = [i.id for i in items]
    cases = (db.query(Case).filter(Case.nomenclature_id.in_(ids))
             .order_by(Case.volume).all()) if ids else []
    case_ids = [c.id for c in cases]
    counts = dict(
        db.query(Document.case_id, func.count(Document.id))
        .filter(Document.case_id.in_(case_ids)).group_by(Document.case_id).all()
    ) if case_ids else {}
    stages = dict(
        db.query(CaseWorkStage.case_id, func.count(CaseWorkStage.id))
        .filter(CaseWorkStage.case_id.in_(case_ids)).group_by(CaseWorkStage.case_id).all()
    ) if case_ids else {}

    by_item: dict[str, list[dict]] = {}
    for c in cases:
        by_item.setdefault(c.nomenclature_id, []).append({
            "id": c.id, "index": c.index, "title": c.title, "volume": c.volume,
            "status": c.status.value, "documents_count": int(counts.get(c.id, 0)),
            "stages_done": int(stages.get(c.id, 0)),
        })
    return [
        {"id": i.id, "index": i.index, "title": i.title, "year": i.year,
         "status": i.status,
         "retention": "Постоянно" if i.permanent else (i.retention_label or ""),
         "doc_types": i.doc_types or [], "cases": by_item.get(i.id, [])}
        for i in items
    ]


@router.post("/cases", response_model=CaseOut, status_code=201)
def open_case(payload: ScanCaseCreate, request: Request, db: Session = Depends(get_db),
              user: User = Depends(require_roles(Role.admin, Role.archivist))):
    """Открывает очередной том дела по статье номенклатуры: индекс, заголовок
    и срок хранения берутся из статьи."""
    nom = db.get(NomenclatureItem, payload.nomenclature_id)
    if nom is None:
        raise HTTPException(status_code=404, detail="Статья номенклатуры не найдена")
    if nom.status == DRAFT:
        raise HTTPException(status_code=409,
                            detail="Статья номенклатуры не согласована — дело по ней не открывается")
    last = (db.query(func.max(Case.volume))
            .filter(Case.nomenclature_id == nom.id, Case.year == nom.year).scalar())
    volume = payload.volume or int(last or 0) + 1
    taken = (db.query(Case.id)
             .filter(Case.nomenclature_id == nom.id, Case.year == nom.year,
                     Case.volume == volume).first())
    if taken is not None:
        raise HTTPException(status_code=409, detail=f"Том {volume} этого дела уже заведён")

    case = Case(
        nomenclature_id=nom.id, index=nom.index,
        title=payload.title.strip() or nom.title, volume=volume, year=nom.year,
        retention_label=nom.retention_label, retention_years=nom.retention_years,
        permanent=nom.permanent,
        department_id=payload.department_id or nom.department_id,
    )
    case.retention_until = compute_until(nom.year, case.retention_years)
    db.add(case)
    db.commit()
    db.refresh(case)
    audit.record(db, user, "scanning.case_open", "case", case.id,
                 f"{case.index} · том {case.volume}", request=request)
    return _with_count(db, case)


@router.post("/cases/{case_id}/documents", status_code=201)
def upload_scans(
    case_id: str, request: Request, background: BackgroundTasks,
    files: list[UploadFile] = File(...),
    doc_type: str = Form(...),
    department_id: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.admin, Role.archivist)),
) -> dict:
    """Пакетный ввод сканов в дело: каждый файл — отдельный документ, который
    проходит обычный приём (антивирус → WORM → распознавание → индекс).

    Вид документа сверяется со статьёй номенклатуры до приёма первого файла:
    партия не должна приниматься наполовину из-за неверно выбранного вида.
    Сбой отдельного файла не останавливает остальные — он возвращается в
    перечне ошибок, и архивариус повторяет только его."""
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Дело не найдено")
    if case.status != CaseStatus.forming:
        raise HTTPException(status_code=409,
                            detail=f"Дело в статусе «{case.status.value}» — ввод документов закрыт")
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(status_code=400,
                            detail=f"Не более {MAX_FILES_PER_REQUEST} файлов за один запрос")
    nom = db.get(NomenclatureItem, case.nomenclature_id) if case.nomenclature_id else None
    try:
        rules.check_doc_type(nom.doc_types if nom is not None else None, doc_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    created: list[dict] = []
    errors: list[dict] = []
    for upload in files:
        data = upload.file.read()
        try:
            doc = create_document_record(
                db, user, data=data, filename=upload.filename,
                content_type=upload.content_type or "application/octet-stream",
                title=rules.title_from_filename(upload.filename),
                doc_type=doc_type, case_id=case.id,
                department_id=department_id or case.department_id or "",
                # Скан бумажного документа — электронная копия (ТС-176 п. 11.6):
                # до сверки с подлинником и удостоверения ЭЦП.
                copy_status=copy_rules.PENDING,
            )
        except HTTPException as exc:
            db.rollback()
            errors.append({"filename": upload.filename, "error": str(exc.detail)})
            continue
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            errors.append({"filename": upload.filename, "error": f"карточка не создана: {exc}"})
            continue
        audit.record(db, user, "document.upload", "document", doc.id,
                     f"{doc.title} ({doc.doc_type.value}) · сканирование в дело {case.index}",
                     request=request)
        background.add_task(process_document, doc.id, data)
        created.append({"id": doc.id, "title": doc.title, "filename": upload.filename})
    return {"created": created, "errors": errors}


def _stage_rows(db: Session, case_id: str) -> list[WorkStageOut]:
    marks = {m.stage: m for m in
             db.query(CaseWorkStage).filter(CaseWorkStage.case_id == case_id).all()}
    rows = []
    for stage, label in WORK_STAGES.items():
        m = marks.get(stage)
        rows.append(WorkStageOut(
            stage=stage, label=label, done=m is not None,
            pages=m.pages if m else 0,
            completed_at=m.completed_at if m else None,
            performed_by=m.performed_by if m else "",
            note=m.note if m else "",
        ))
    return rows


@router.get("/cases/{case_id}/stages", response_model=list[WorkStageOut])
def case_stages(case_id: str, db: Session = Depends(get_db),
                _: User = Depends(get_current_user)):
    if db.get(Case, case_id) is None:
        raise HTTPException(status_code=404, detail="Дело не найдено")
    return _stage_rows(db, case_id)


@router.put("/cases/{case_id}/stages/{stage}", response_model=list[WorkStageOut])
def set_stage(case_id: str, stage: str, payload: WorkStageUpdate, request: Request,
              db: Session = Depends(get_db),
              user: User = Depends(require_roles(Role.admin, Role.archivist))):
    """Отметка этапа работ по делу. Снятие отметки удаляет её: этап, который
    переделывается, не должен попасть в объём оказанных услуг."""
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Дело не найдено")
    if stage not in WORK_STAGES:
        raise HTTPException(status_code=400,
                            detail="Этап: " + ", ".join(WORK_STAGES))
    mark = (db.query(CaseWorkStage)
            .filter(CaseWorkStage.case_id == case_id, CaseWorkStage.stage == stage)
            .first())

    if not payload.done:
        if mark is not None:
            db.delete(mark)
            db.commit()
            audit.record(db, user, "scanning.stage_reset", "case", case_id,
                         WORK_STAGES[stage], request=request)
        return _stage_rows(db, case_id)

    pages = payload.pages
    if pages is None:
        # Объём по умолчанию — страницы уже принятых документов дела: для
        # сканирования и оцифровки это и есть выполненная работа.
        pages = int(db.query(func.coalesce(func.sum(Document.page_count), 0))
                    .filter(Document.case_id == case_id,
                            Document.destroyed_at.is_(None)).scalar() or 0)
    if mark is None:
        mark = CaseWorkStage(case_id=case_id, stage=stage)
        db.add(mark)
    mark.pages = max(0, int(pages))
    mark.completed_at = payload.completed_at or date.today()
    mark.performed_by = user.email
    mark.note = payload.note
    db.commit()
    audit.record(db, user, "scanning.stage", "case", case_id,
                 f"{case.index} · {WORK_STAGES[stage]}: {mark.pages} стр.", request=request)
    return _stage_rows(db, case_id)


def _period(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    date_to = date_to or date.today()
    date_from = date_from or date_to.replace(day=1)
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="Начало периода позже его конца")
    return date_from, date_to


@router.get("/volume")
def volume(date_from: date | None = None, date_to: date | None = None,
           db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> dict:
    """Объём оказанных услуг за период — приложение к акту (ТС-176 п. 5.5, 12).
    По умолчанию — с начала текущего месяца по сегодня."""
    date_from, date_to = _period(date_from, date_to)
    marks = (db.query(CaseWorkStage, Case)
             .join(Case, Case.id == CaseWorkStage.case_id)
             .filter(CaseWorkStage.completed_at >= date_from,
                     CaseWorkStage.completed_at <= date_to)
             .order_by(CaseWorkStage.completed_at, Case.index, Case.volume).all())
    docs, pages = (
        db.query(func.count(Document.id), func.coalesce(func.sum(Document.page_count), 0))
        .filter(Document.case_id.isnot(None),
                Document.created_at >= datetime.combine(date_from, time.min),
                Document.created_at < datetime.combine(date_to + timedelta(days=1), time.min))
        .one()
    )
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "summary": rules.summarize([(m.stage, m.pages) for m, _ in marks]),
        "documents": int(docs),
        "document_pages": int(pages),
        "rows": [
            {"stage": m.stage, "label": WORK_STAGES.get(m.stage, m.stage),
             "case_id": c.id, "case": f"{c.index} · {c.title}", "volume": c.volume,
             "year": c.year, "pages": m.pages,
             "completed_at": m.completed_at.isoformat() if m.completed_at else "",
             "performed_by": m.performed_by}
            for m, c in marks
        ],
    }


@router.get("/volume/xlsx")
def volume_xlsx(request: Request, date_from: date | None = None,
                date_to: date | None = None, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    data = volume(date_from, date_to, db, user)
    rows: list[list] = [
        [f"Итого: {s['label']}", f"дел: {s['cases']}", "", "", s["pages"], "", ""]
        for s in data["summary"]
    ]
    rows.append([])
    rows += [[r["label"], r["case"], r["volume"], r["year"], r["pages"],
              r["completed_at"], r["performed_by"]] for r in data["rows"]]
    blob = xlsx.build(
        title="Объём оказанных услуг по оцифровке архива",
        subtitle=(f"за период {data['date_from']} — {data['date_to']}; принято документов "
                  f"в дела: {data['documents']}, страниц: {data['document_pages']}"),
        headers=["Этап работ", "Дело", "Том", "Год", "Страниц", "Дата", "Исполнитель"],
        rows=rows, sheet="Объём услуг",
    )
    audit.record(db, user, "scanning.volume_export", "archive", "",
                 f"{data['date_from']} — {data['date_to']}", request=request)
    return StreamingResponse(
        io.BytesIO(blob), media_type=xlsx.MEDIA_TYPE,
        headers={"Content-Disposition":
                 f'attachment; filename="{xlsx.filename("services_volume_" + data["date_from"] + "_" + data["date_to"])}"'},
    )
