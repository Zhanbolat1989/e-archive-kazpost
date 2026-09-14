"""Электронные копии документов (ТС-176 п. 11.6–11.7): сверка с подлинником,
удостоверение ЭЦП работника архива, отдельная опись и акт уничтожения копий.
Правила переходов — в services/ecopies.py."""
import base64
import io
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    ActStatus, Case, DestructionAct, DestructionActItem, Document, Role, User,
)
from ..schemas import (
    CopyCertify, CopyMark, CopyReconcile, DestructionActDetail, DocumentOut, EcopyActCreate,
)
from ..security import get_current_user, require_roles
from ..services import access, audit, history, signature, storage, xlsx
from ..services import ecopies as rules
from .lifecycle import get_act

router = APIRouter(prefix="/api/ecopies", tags=["ecopies"])

_HISTORY_FIELDS = ["copy_status", "copy_checked_by", "copy_note", "copy_signer"]


def _copy(db: Session, user: User, doc_id: str) -> Document:
    doc = db.get(Document, doc_id)
    if not doc or not access.can_see(db, user, doc):
        raise HTTPException(status_code=404, detail="Документ не найден")
    if doc.destroyed_at is not None:
        raise HTTPException(status_code=409, detail=f"Документ уничтожен {doc.destroyed_at}")
    return doc


@router.get("")
def list_copies(status: str | None = None, case_id: str | None = None,
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> dict:
    """Реестр электронных копий со сводкой по результатам сверки."""
    q = access.apply(db.query(Document), db, user).filter(
        Document.copy_status != "", Document.destroyed_at.is_(None)
    )
    counts = dict(q.with_entities(Document.copy_status, func.count(Document.id))
                  .group_by(Document.copy_status).all())
    if status:
        if status not in rules.STATUSES:
            raise HTTPException(status_code=400,
                                detail="Статус: " + ", ".join(rules.STATUSES))
        q = q.filter(Document.copy_status == status)
    if case_id:
        q = q.filter(Document.case_id == case_id)
    rows = q.order_by(Document.case_id, Document.created_at).limit(500).all()
    return {
        "statuses": [{"key": k, "label": v, "count": int(counts.get(k, 0))}
                     for k, v in rules.STATUSES.items()],
        "documents": [DocumentOut.model_validate(d) for d in rows],
    }


@router.post("/{doc_id}/mark", response_model=DocumentOut)
def mark_copy(doc_id: str, payload: CopyMark, request: Request,
              db: Session = Depends(get_db),
              user: User = Depends(require_roles(Role.admin, Role.archivist))):
    """Отметка «электронная копия бумажного документа» либо её снятие."""
    doc = _copy(db, user, doc_id)
    before = history.snapshot(doc, ["copy_status"])
    if payload.is_copy:
        doc.copy_status = doc.copy_status or rules.PENDING
    else:
        try:
            rules.check_unmark(doc.copy_status)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        doc.copy_status = ""
    db.commit()
    history.record(db, user, "document", doc.id, before, {"copy_status": doc.copy_status})
    audit.record(db, user, "ecopy.mark", "document", doc.id,
                 "электронная копия" if payload.is_copy else "электронный документ",
                 request=request)
    db.refresh(doc)
    return doc


@router.post("/{doc_id}/certify", response_model=DocumentOut)
def certify_copy(doc_id: str, payload: CopyCertify, request: Request,
                 db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.admin, Role.archivist))):
    """Удостоверение копии ЭЦП работника архива после положительной сверки
    с подлинником (п. 11.6).

    Подписывается контрольная характеристика файла копии: подпись привязана
    именно к этому файлу, и подменить его после удостоверения незаметно
    нельзя. Сама подпись сохраняется под WORM рядом с оригиналом."""
    doc = _copy(db, user, doc_id)
    try:
        rules.check_certify(doc.copy_status)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    result = signature.verify(payload.cms_base64)
    if not signature.is_confirmed(result):
        raise HTTPException(status_code=400, detail=f"ЭЦП не подтверждена: {result.detail}")
    matches, why = signature.content_matches(payload.cms_base64,
                                             doc.checksum_sha256.encode())
    if not matches:
        raise HTTPException(status_code=400,
                            detail=f"Подпись не относится к этой копии: {why}")

    key = f"{doc.storage_key}.copy-certification.p7s"
    try:
        storage.put_original(key, base64.b64decode(payload.cms_base64),
                             "application/pkcs7-signature")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502,
                            detail="Подпись не сохранена в хранилище — повторите") from exc

    before = history.snapshot(doc, _HISTORY_FIELDS)
    doc.copy_status = rules.CERTIFIED
    doc.copy_signer = result.signer_info
    doc.copy_checked_by = user.email
    doc.copy_checked_at = datetime.utcnow()
    doc.copy_note = payload.note
    doc.copy_cms_key = key
    db.commit()
    history.record(db, user, "document", doc.id, before,
                   {f: getattr(doc, f) for f in _HISTORY_FIELDS})
    audit.record(db, user, "ecopy.certify", "document", doc.id,
                 f"{result.status.value}: {result.signer_info}", request=request)
    db.refresh(doc)
    return doc


@router.post("/{doc_id}/reconcile", response_model=DocumentOut)
def reconcile_copy(doc_id: str, payload: CopyReconcile, request: Request,
                   db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.admin, Role.archivist))):
    """Отрицательный результат сверки или отсутствие подлинника (п. 11.7):
    копия становится кандидатом в акт об уничтожении электронных копий."""
    doc = _copy(db, user, doc_id)
    try:
        rules.check_reconcile(doc.copy_status, payload.result)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    before = history.snapshot(doc, _HISTORY_FIELDS)
    doc.copy_status = payload.result
    doc.copy_checked_by = user.email
    doc.copy_checked_at = datetime.utcnow()
    doc.copy_note = payload.note
    db.commit()
    history.record(db, user, "document", doc.id, before,
                   {f: getattr(doc, f) for f in _HISTORY_FIELDS})
    audit.record(db, user, "ecopy.reconcile", "document", doc.id,
                 f"{rules.STATUSES[payload.result]}: {payload.note}", request=request)
    db.refresh(doc)
    return doc


@router.post("/destruction-acts", response_model=DestructionActDetail, status_code=201)
def create_copy_act(payload: EcopyActCreate, request: Request,
                    db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.admin, Role.archivist))):
    """Акт об уничтожении электронных копий (п. 11.7). Утверждается в разделе
    «Уничтожение» и только с указанием протокола ЦЭК (ЭК)."""
    ids = list(dict.fromkeys(payload.document_ids))
    docs = access.apply(db.query(Document), db, user).filter(Document.id.in_(ids)).all()
    if len(docs) != len(ids):
        raise HTTPException(status_code=400, detail="Часть документов не найдена")
    bad = []
    for d in docs:
        try:
            rules.check_destroyable(d.copy_status)
        except ValueError:
            bad.append(d.title)
            continue
        if d.destroyed_at is not None:
            bad.append(d.title)
    if bad:
        raise HTTPException(
            status_code=400,
            detail="Не подлежат уничтожению как копии: " + "; ".join(bad[:3]),
        )
    # Копия не может ждать утверждения в двух актах сразу: утверждение одного
    # оставило бы в другом уже уничтоженный документ.
    in_draft = (db.query(DestructionAct.number)
                .join(DestructionActItem, DestructionActItem.act_id == DestructionAct.id)
                .filter(DestructionActItem.document_id.in_(ids),
                        DestructionAct.status == ActStatus.draft)
                .first())
    if in_draft is not None:
        raise HTTPException(status_code=409,
                            detail=f"Часть копий уже включена в проект акта {in_draft[0]}")

    today = date.today()
    seq = db.query(DestructionAct).filter(
        DestructionAct.number.like(f"{rules.ACT_PREFIX}-{today.year}/%")).count() + 1
    act = DestructionAct(
        number=f"{rules.ACT_PREFIX}-{today.year}/{seq:02d}",
        is_electronic=True,
        kind=rules.ACT_KIND,
        commission_protocol=payload.commission_protocol.strip(),
        note=payload.note,
        created_by=user.full_name or user.email,
    )
    act.items = [DestructionActItem(document_id=d.id) for d in docs]
    db.add(act)
    db.commit()
    db.refresh(act)
    audit.record(db, user, "ecopy.act_create", "act", act.id,
                 f"{act.number}: копий {len(docs)}", request=request)
    return get_act(act.id, db, user)


@router.get("/inventory/xlsx")
def copies_inventory(request: Request, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """Опись электронных копий документов (п. 11.6): копии учитываются отдельно
    от электронных документов, с результатом сверки по каждой."""
    docs = (access.apply(db.query(Document), db, user)
            .filter(Document.copy_status != "", Document.destroyed_at.is_(None))
            .order_by(Document.case_id, Document.doc_date.asc().nullslast(),
                      Document.created_at)
            .all())
    case_ids = {d.case_id for d in docs if d.case_id}
    cases = ({c.id: c for c in db.query(Case).filter(Case.id.in_(case_ids)).all()}
             if case_ids else {})
    rows = []
    for i, d in enumerate(docs, start=1):
        case = cases.get(d.case_id)
        rows.append([
            i,
            f"{case.index} · том {case.volume} ({case.year})" if case else "—",
            d.title,
            d.doc_type.value if d.doc_type else "",
            d.doc_date.strftime("%d.%m.%Y") if d.doc_date else "",
            d.page_count or "",
            rules.STATUSES.get(d.copy_status, d.copy_status),
            d.copy_signer,
            d.copy_checked_at.strftime("%d.%m.%Y") if d.copy_checked_at else "",
        ])
    blob = xlsx.build(
        title="Опись электронных копий документов",
        subtitle=f"Сформирована {datetime.utcnow():%d.%m.%Y}; копий: {len(rows)}",
        headers=["№ п/п", "Дело", "Заголовок документа", "Вид документа", "Дата",
                 "Листов", "Результат сверки", "Удостоверил (ЭЦП)", "Дата сверки"],
        rows=rows, sheet="Электронные копии",
    )
    audit.record(db, user, "ecopy.inventory_export", "archive", "",
                 f"опись электронных копий: {len(rows)}", request=request)
    return StreamingResponse(
        io.BytesIO(blob), media_type=xlsx.MEDIA_TYPE,
        headers={"Content-Disposition":
                 f'attachment; filename="{xlsx.filename("ecopies_inventory")}"'},
    )
