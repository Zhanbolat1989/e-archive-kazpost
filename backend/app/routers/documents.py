import hashlib
import io
import uuid
from datetime import datetime

from fastapi import (
    APIRouter, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from datetime import date as _date

from ..autonumber import is_internal_type, next_document_number
from ..db import get_db
from ..models import (
    User, Role, Document, DocStatus, DocType, DOC_TYPE_GROUPS, Case, RegCard,
    DestructionActItem,
)
from ..retention import rule_for, compute_until
from ..schemas import (
    DocumentOut, DocumentDetail, DocumentUpdate, DocumentHistory, DocumentHistoryItem,
)
from ..security import get_current_user, require_roles
from ..services import storage, search, audit
from ..services import forms as forms_svc
from ..ingest import process_document

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _parse_doc_type(value: str) -> DocType:
    value = (value or "").strip()
    for dt in DocType:
        if value == dt.value or value == dt.name:
            return dt
    return DocType.other


def _parse_date(value: str):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return _date.fromisoformat(value)
    except ValueError:
        return None


def _create_document(
    db: Session, user: User, file: UploadFile, *,
    title: str, description: str, fond: str, opis: str, delo: str,
    doc_type: str, doc_number: str, counterparty: str, doc_date: str,
    amount: str, currency: str, case_id: str,
    cadastral_number: str = "", real_estate_address: str = "",
    real_estate_area: str = "", replaces: Document | None = None,
) -> tuple[Document, bytes]:
    """Общая логика создания записи документа — используется и приёмом нового
    файла, и заменой существующего документа новой версией (supersede)."""
    data = file.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Пустой файл")

    checksum = hashlib.sha256(data).hexdigest()
    doc_id = str(uuid.uuid4())
    storage_key = f"{datetime.utcnow():%Y/%m}/{doc_id}/{file.filename}"

    try:
        amount_val = float(amount) if amount.strip() else None
    except ValueError:
        amount_val = None
    try:
        area_val = float(real_estate_area) if real_estate_area.strip() else None
    except ValueError:
        area_val = None

    parsed_type = _parse_doc_type(doc_type)
    parsed_date = _parse_date(doc_date)
    case = db.get(Case, case_id) if case_id.strip() else None
    base_year = (parsed_date or datetime.utcnow().date()).year

    # При замене документа (напр. смена собственника) объект наследует
    # идентификацию от предыдущей версии, если не указана заново.
    cad_number = cadastral_number.strip() or (replaces.cadastral_number if replaces else "")
    re_address = real_estate_address.strip() or (replaces.real_estate_address if replaces else "")
    if area_val is None and replaces is not None:
        area_val = replaces.real_estate_area
    if case is None and replaces is not None and replaces.case_id:
        case = db.get(Case, replaces.case_id)

    # Номер внутреннего документа (приказ, распоряжение, протокол…) присваивает
    # сам архив, если поле оставлено пустым — в отличие от внешних документов
    # (договор, счёт-фактура), чей номер всегда приходит с оригинала.
    doc_number_final = doc_number.strip()
    if not doc_number_final and is_internal_type(parsed_type):
        doc_number_final = next_document_number(db, parsed_type, base_year) or ""
    if case is not None and (case.retention_years or case.permanent):
        ret_label, ret_years, ret_perm = (
            case.retention_label, case.retention_years, case.permanent
        )
    else:
        rule = rule_for(parsed_type)
        ret_label, ret_years, ret_perm = rule.label, rule.years, rule.permanent

    doc = Document(
        id=doc_id,
        title=title or file.filename,
        description=description,
        fond=fond,
        opis=opis,
        delo=delo,
        doc_type=parsed_type,
        doc_number=doc_number_final,
        counterparty=counterparty,
        doc_date=parsed_date,
        amount=amount_val,
        currency=currency or "KZT",
        cadastral_number=cad_number,
        real_estate_address=re_address,
        real_estate_area=area_val,
        case_id=case.id if case else None,
        retention_label=ret_label,
        retention_years=ret_years,
        permanent=ret_perm,
        retention_until=compute_until(base_year, ret_years),
        replaces_id=replaces.id if replaces else None,
        original_filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        size=len(data),
        storage_key=storage_key,
        checksum_sha256=checksum,
        status=DocStatus.uploaded,
        owner_id=user.id,
    )
    db.add(doc)
    # ЭРКК: рег. номер = индекс дела по номенклатуре + порядковый номер (№ 236).
    prefix = (case.index if case else "") or "б/н"
    year = datetime.utcnow().year
    serial = (
        db.query(RegCard)
        .filter(RegCard.reg_number.like(f"{prefix}-{year}-%"))
        .count() + 1
    )
    db.add(RegCard(
        document_id=doc_id,
        reg_number=f"{prefix}-{year}-{serial:03d}",
        executor=user.full_name or user.email,
    ))
    if replaces is not None:
        replaces.superseded_at = datetime.utcnow().date()
    db.commit()
    db.refresh(doc)
    return doc, data


@router.post("", response_model=DocumentOut, status_code=201)
def upload_document(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(""),
    description: str = Form(""),
    fond: str = Form(""),
    opis: str = Form(""),
    delo: str = Form(""),
    doc_type: str = Form(""),
    doc_number: str = Form(""),
    counterparty: str = Form(""),
    doc_date: str = Form(""),
    amount: str = Form(""),
    currency: str = Form("KZT"),
    case_id: str = Form(""),
    cadastral_number: str = Form(""),
    real_estate_address: str = Form(""),
    real_estate_area: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.admin, Role.archivist)),
):
    doc, data = _create_document(
        db, user, file, title=title, description=description, fond=fond,
        opis=opis, delo=delo, doc_type=doc_type, doc_number=doc_number,
        counterparty=counterparty, doc_date=doc_date, amount=amount,
        currency=currency, case_id=case_id, cadastral_number=cadastral_number,
        real_estate_address=real_estate_address, real_estate_area=real_estate_area,
    )
    audit.record(db, user, "document.upload", "document", doc.id,
                 f"{doc.title} ({doc.doc_type.value})")

    # Pipeline runs async so the UI gets instant feedback + live status.
    background.add_task(process_document, doc.id, data)
    return doc


@router.post("/{doc_id}/supersede", response_model=DocumentOut, status_code=201)
def supersede_document(
    doc_id: str,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(""),
    description: str = Form(""),
    doc_type: str = Form(""),
    doc_number: str = Form(""),
    counterparty: str = Form(""),
    doc_date: str = Form(""),
    amount: str = Form(""),
    currency: str = Form("KZT"),
    cadastral_number: str = Form(""),
    real_estate_address: str = Form(""),
    real_estate_area: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.admin, Role.archivist)),
):
    """Регистрирует новую версию документа взамен текущей — оригинал в WORM
    не редактируется. Типовой сценарий: смена собственника недвижимости
    (ст. 6–7 Закона № 310-III — при регистрации нового права предыдущее
    прекращается). Кадастровые данные и дело наследуются от предыдущей версии,
    если не заданы явно."""
    old = db.get(Document, doc_id)
    if not old:
        raise HTTPException(status_code=404, detail="Документ не найден")
    if old.superseded_at is not None:
        raise HTTPException(status_code=409, detail="Документ уже заменён более новой версией")
    if old.destroyed_at is not None:
        raise HTTPException(status_code=409, detail="Документ уничтожен по акту")

    doc, data = _create_document(
        db, user, file,
        title=title or old.title, description=description or old.description,
        fond=old.fond, opis=old.opis, delo=old.delo,
        doc_type=doc_type or old.doc_type.value, doc_number=doc_number,
        counterparty=counterparty or old.counterparty, doc_date=doc_date,
        amount=amount, currency=currency or old.currency,
        case_id=old.case_id or "", cadastral_number=cadastral_number,
        real_estate_address=real_estate_address, real_estate_area=real_estate_area,
        replaces=old,
    )
    audit.record(db, user, "document.supersede", "document", doc.id,
                 f"заменяет {old.title} ({old.id})")
    background.add_task(process_document, doc.id, data)
    return doc


@router.get("/{doc_id}/history", response_model=DocumentHistory)
def document_history(
    doc_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    """Полная цепочка версий документа (кто кого заменил), от первой к текущей."""
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")

    # К началу цепочки
    head = doc
    seen = {head.id}
    while head.replaces_id and head.replaces_id not in seen:
        parent = db.get(Document, head.replaces_id)
        if parent is None:
            break
        head, seen = parent, seen | {parent.id}

    # От начала к текущей версии
    chain = [head]
    seen = {head.id}
    current = head
    while True:
        nxt = db.query(Document).filter(Document.replaces_id == current.id).first()
        if nxt is None or nxt.id in seen:
            break
        chain.append(nxt)
        seen.add(nxt.id)
        current = nxt

    items = [
        DocumentHistoryItem(
            id=d.id, title=d.title, doc_number=d.doc_number, doc_date=d.doc_date,
            created_at=d.created_at, superseded_at=d.superseded_at,
            is_current=d.superseded_at is None,
        )
        for d in chain
    ]
    return DocumentHistory(cadastral_number=doc.cadastral_number, chain=items)


@router.get("", response_model=list[DocumentOut])
def list_documents(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return (
        db.query(Document)
        .order_by(Document.created_at.desc())
        .offset(skip)
        .limit(min(limit, 200))
        .all()
    )


@router.get("/meta/types")
def document_types(_: User = Depends(get_current_user)) -> list[dict]:
    """Grouped document types for the upload form dropdown."""
    return [{"group": g, "types": [t.value for t in items]}
            for g, items in DOC_TYPE_GROUPS.items()]


@router.get("/{doc_id}", response_model=DocumentDetail)
def get_document(
    doc_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")
    return doc


@router.get("/{doc_id}/certified-copy")
def certified_copy(
    doc_id: str, db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Заверенная бумажная копия ЭД (п. 38/44 приказа № 236, ред. 2026):
    содержимое + штамп «Копия электронного документа верна» с результатом
    проверки ЭЦП и контрольной характеристикой."""
    doc = db.get(Document, doc_id)
    if not doc or doc.status == DocStatus.infected:
        raise HTTPException(status_code=404, detail="Документ недоступен")
    if doc.destroyed_at is not None:
        raise HTTPException(status_code=410,
                            detail=f"Документ уничтожен {doc.destroyed_at}")
    sig_map = {
        "valid": "ЭЦП действительна (проверено)",
        "invalid": "ЭЦП НЕдействительна",
        "unsupported": "ЭЦП: алгоритм не поддержан",
        "none": "ЭЦП не применялась",
    }
    sig_note = sig_map.get(doc.signature_status.value, "—")
    data = forms_svc.certified_copy_pdf(doc, sig_note)
    audit.record(db, user, "document.certified_copy", "document", doc_id, doc.title)
    return StreamingResponse(
        io.BytesIO(data), media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="certified_copy.pdf"'},
    )


@router.get("/{doc_id}/download")
def download_document(
    doc_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    doc = db.get(Document, doc_id)
    if not doc or doc.status == DocStatus.infected:
        raise HTTPException(status_code=404, detail="Документ недоступен")
    if doc.destroyed_at is not None:
        raise HTTPException(status_code=410,
                            detail=f"Документ уничтожен по акту {doc.destroyed_at}")
    # Stream through the backend so the browser never needs to reach MinIO
    # directly (internal host) and the JWT is enforced on the request.
    data = storage.get_object(doc.storage_key)
    return StreamingResponse(
        io.BytesIO(data),
        media_type=doc.content_type,
        headers={
            "Content-Disposition": f'inline; filename="{doc.original_filename}"'
        },
    )


@router.patch("/{doc_id}", response_model=DocumentOut)
def update_document(
    doc_id: str,
    payload: DocumentUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.admin, Role.archivist)),
):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(doc, field, value)
    db.commit()
    db.refresh(doc)
    # Re-index metadata (does not touch the WORM-locked original).
    if doc.status == DocStatus.ready:
        search.index_document(
            {
                "id": doc.id, "title": doc.title, "description": doc.description,
                "ocr_text": doc.ocr_text, "fond": doc.fond, "opis": doc.opis,
                "delo": doc.delo, "doc_type": doc.doc_type.value if doc.doc_type else "",
                "doc_number": doc.doc_number, "counterparty": doc.counterparty,
                "doc_date": doc.doc_date.isoformat() if doc.doc_date else None,
                "amount": float(doc.amount) if doc.amount is not None else None,
                "cadastral_number": doc.cadastral_number,
                "real_estate_address": doc.real_estate_address,
                "status": doc.status.value,
                "created_at": doc.created_at.isoformat(),
            }
        )
    return doc


@router.delete("/{doc_id}", status_code=204)
def delete_document(
    doc_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.admin)),
):
    """Removes the catalogue record and search index entry. The original stays
    under WORM retention in object storage (compliance)."""
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")

    # Документ, включённый в акт о выделении к уничтожению, снять с учёта нельзя:
    # акт — юридический документ (прил. 14/15 приказа № 235), его позиции должны
    # оставаться проверяемыми.
    in_act = (
        db.query(DestructionActItem).filter(DestructionActItem.document_id == doc_id).first()
    )
    if in_act:
        raise HTTPException(
            status_code=409,
            detail="Документ включён в акт о выделении к уничтожению — снятие с учёта запрещено",
        )

    # Удаляем узел из цепочки версий, не разрывая её (как из связного списка):
    # преемников перецепляем на предшественника удаляемого документа, а не
    # обнуляем — иначе A←B←C при удалении B распалось бы на две цепочки.
    db.query(Document).filter(Document.replaces_id == doc_id).update(
        {Document.replaces_id: doc.replaces_id}, synchronize_session=False
    )
    # Если снимается текущая версия (тип цепочки) — у предшественника убираем
    # пометку «заменён»: его замена удаляется, он снова становится актуальным.
    if doc.superseded_at is None and doc.replaces_id:
        pred = db.get(Document, doc.replaces_id)
        if pred is not None:
            pred.superseded_at = None

    db.delete(doc)  # ЭРКК снимается каскадом (Document.reg_card)
    db.commit()
    # Из индекса убираем только после успешного commit: иначе сбой транзакции
    # оставил бы живой документ ненаходимым в поиске.
    search.delete_document(doc_id)
