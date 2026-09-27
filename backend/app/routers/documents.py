import hashlib
import io
import uuid
from datetime import datetime

from fastapi import (
    APIRouter, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks,
    Query, Request,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from datetime import date as _date, timedelta

from ..autonumber import is_internal_type, next_document_number
from ..db import get_db
from ..models import (
    User, Role, Document, DocStatus, DocType, DOC_TYPE_GROUPS, Case, RegCard,
    DestructionActItem, AuditLog, AuditActionType, ExtractedEntity, ChangeHistory,
    ArchiveRequestItem,
)
from ..retention import rule_for, compute_until
from ..schemas import (
    DocumentOut, DocumentDetail, DocumentUpdate, DocumentHistory, DocumentHistoryItem,
)
from ..security import get_current_user, require_roles
from ..services import storage, search, audit, access, history
from ..services import ecopies as ecopy_rules
from ..services import forms as forms_svc
from ..ingest import process_document, _index_payload

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


def create_document_record(
    db: Session, user: User, *,
    data: bytes, filename: str, content_type: str,
    title: str, description: str = "", fond: str = "", opis: str = "", delo: str = "",
    doc_type: str = "", doc_number: str = "", counterparty: str = "", doc_date: str = "",
    amount: str = "", currency: str = "KZT", case_id: str = "",
    cadastral_number: str = "", real_estate_address: str = "",
    real_estate_area: str = "", department_id: str = "",
    replaces: Document | None = None, copy_status: str = "",
) -> Document:
    """Общая логика создания записи документа — используется приёмом файла,
    заменой документа новой версией (supersede) и модулем импорта.

    Принимает именно байты, а не UploadFile: импорт читает файлы из ZIP-пакета,
    и заворачивать их в объект загрузки только ради этой функции не нужно."""
    if not data:
        raise HTTPException(status_code=400, detail="Пустой файл")

    checksum = hashlib.sha256(data).hexdigest()
    doc_id = str(uuid.uuid4())
    storage_key = f"{datetime.utcnow():%Y/%m}/{doc_id}/{filename}"

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
        title=title or filename,
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
        department_id=(department_id.strip() or None
                       if isinstance(department_id, str) else department_id)
        or (replaces.department_id if replaces else None),
        original_filename=filename,
        content_type=content_type or "application/octet-stream",
        size=len(data),
        storage_key=storage_key,
        checksum_sha256=checksum,
        status=DocStatus.uploaded,
        owner_id=user.id,
        copy_status=copy_status,
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
    return doc


def _create_document(db: Session, user: User, file: UploadFile, **kwargs
                     ) -> tuple[Document, bytes]:
    """Приём загруженного файла: читает содержимое и создаёт карточку."""
    data = file.file.read()
    doc = create_document_record(
        db, user, data=data, filename=file.filename,
        content_type=file.content_type or "application/octet-stream", **kwargs,
    )
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
    department_id: str = Form(""),
    # ТС-176 п. 11.6: скан бумажного документа — электронная копия
    is_copy: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.admin, Role.archivist)),
):
    doc, data = _create_document(
        db, user, file, title=title, description=description, fond=fond,
        opis=opis, delo=delo, doc_type=doc_type, doc_number=doc_number,
        counterparty=counterparty, doc_date=doc_date, amount=amount,
        currency=currency, case_id=case_id, cadastral_number=cadastral_number,
        real_estate_address=real_estate_address, real_estate_area=real_estate_area,
        department_id=department_id,
        copy_status=ecopy_rules.PENDING if is_copy else "",
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
    if not old or not access.can_see(db, user, old):
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
    doc_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """Полная цепочка версий документа (кто кого заменил), от первой к текущей."""
    doc = db.get(Document, doc_id)
    if not doc or not access.can_see(db, user, doc):
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
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    department_id: str | None = None,
    doc_type: str | None = None,
    doc_group: str | None = None,
    case_id: str | None = None,
    year: int | None = None,
    retention: str | None = Query(None, pattern="^(permanent|expired|expiring|active)$"),
    needs_review: bool | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Перечень документов с фильтрами модуля «Документы»:
    подразделение, вид документа, срок хранения и срок уничтожения.

    retention: permanent — постоянного хранения; expired — срок истёк, документ
    подлежит уничтожению; expiring — срок истекает в ближайший год; active —
    срок ещё не подходит.
    """
    q = access.apply(db.query(Document), db, user)
    if department_id:
        q = q.filter(Document.department_id == department_id)
    if doc_type:
        q = q.filter(Document.doc_type == _parse_doc_type(doc_type))
    if doc_group:
        types = DOC_TYPE_GROUPS.get(doc_group)
        if types is None:
            raise HTTPException(status_code=400, detail="Неизвестная категория документов")
        q = q.filter(Document.doc_type.in_(types))
    if case_id:
        q = q.filter(Document.case_id == case_id)
    if year:
        q = q.filter(Document.doc_date >= _date(year, 1, 1),
                     Document.doc_date <= _date(year, 12, 31))
    if retention:
        today = _date.today()
        horizon = today + timedelta(days=365)
        if retention == "permanent":
            q = q.filter(Document.permanent.is_(True))
        elif retention == "expired":
            q = q.filter(Document.permanent.is_(False), Document.destroyed_at.is_(None),
                         Document.retention_until < today)
        elif retention == "expiring":
            q = q.filter(Document.permanent.is_(False), Document.retention_until >= today,
                         Document.retention_until <= horizon)
        else:
            q = q.filter(Document.permanent.is_(False),
                         or_(Document.retention_until.is_(None),
                             Document.retention_until > horizon))
    if needs_review is not None:
        q = q.filter(Document.needs_review.is_(needs_review))
    return q.order_by(Document.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/meta/types")
def document_types(_: User = Depends(get_current_user)) -> list[dict]:
    """Grouped document types for the upload form dropdown."""
    return [{"group": g, "types": [t.value for t in items]}
            for g, items in DOC_TYPE_GROUPS.items()]


@router.get("/meta/review")
def review_queue(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.admin, Role.archivist)),
) -> dict:
    """Перечень документов, требующих ручной проверки после распознавания:
    низкая уверенность OCR, пустые страницы, дубли.

    Отдаём вместе со сводкой качества: архивариусу нужно понимать не только
    что проверять, но и насколько в целом удалась партия оцифровки."""
    q = access.apply(db.query(Document), db, user).filter(
        Document.destroyed_at.is_(None)
    )
    flagged_q = q.filter(Document.needs_review.is_(True))
    flagged = (flagged_q
               .order_by(Document.ocr_confidence.asc().nullsfirst(),
                         Document.created_at.desc())
               .limit(500).all())
    # Сводка считается в базе: поднимать ради среднего и суммы весь архив
    # вместе с распознанным текстом нельзя.
    recognized, avg, pages = q.with_entities(
        func.count(Document.ocr_confidence), func.avg(Document.ocr_confidence),
        func.coalesce(func.sum(Document.page_count), 0),
    ).one()
    return {
        # Полное число, а не длина выдачи: перечень ограничен 500 строками.
        "total_flagged": flagged_q.count(),
        "recognized_documents": int(recognized),
        "average_confidence": round(float(avg), 2) if avg is not None else None,
        "total_pages": int(pages),
        "documents": [
            {
                "id": d.id, "title": d.title,
                "doc_type": d.doc_type.value if d.doc_type else "",
                "page_count": d.page_count,
                "ocr_confidence": float(d.ocr_confidence) if d.ocr_confidence is not None else None,
                "review_reason": d.review_reason,
                "duplicate_of_id": d.duplicate_of_id,
                "created_at": d.created_at.isoformat(),
            }
            for d in flagged
        ],
    }


@router.post("/{doc_id}/review/accept", response_model=DocumentOut)
def accept_review(
    doc_id: str, request: Request, db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.admin, Role.archivist)),
):
    """Ручная проверка пройдена: отметка снимается, причина сохраняется в
    истории изменений — почему документ попадал в очередь, видно и потом."""
    doc = db.get(Document, doc_id)
    if not doc or not access.can_see(db, user, doc):
        raise HTTPException(status_code=404, detail="Документ не найден")
    before = history.snapshot(doc, ["needs_review", "review_reason"])
    doc.needs_review = False
    doc.review_reason = ""
    db.commit()
    history.record(db, user, "document", doc.id, before,
                   {"needs_review": False, "review_reason": ""})
    audit.record(db, user, "document.review_accept", "document", doc.id,
                 before.get("review_reason") or "", request=request)
    db.refresh(doc)
    return doc


@router.get("/{doc_id}/entities")
def document_entities(
    doc_id: str, db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """Реквизиты, извлечённые из текста, с привязкой к странице и фрагменту."""
    doc = db.get(Document, doc_id)
    if not doc or not access.can_see(db, user, doc):
        raise HTTPException(status_code=404, detail="Документ не найден")
    rows = (db.query(ExtractedEntity)
            .filter(ExtractedEntity.document_id == doc_id)
            .order_by(ExtractedEntity.page_no, ExtractedEntity.kind)
            .all())
    return [
        {"kind": r.kind, "value": r.value, "normalized": r.normalized,
         "page_no": r.page_no, "fragment": r.fragment, "source": r.source}
        for r in rows
    ]


@router.get("/{doc_id}/changes")
def document_changes(
    doc_id: str, db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """История изменений карточки: поле, прежнее и новое значение (п. 8)."""
    doc = db.get(Document, doc_id)
    # Прежние значения полей — те же реквизиты документа: закрытая для роли
    # категория не должна раскрываться через историю изменений.
    if not doc or not access.can_see(db, user, doc):
        raise HTTPException(status_code=404, detail="Документ не найден")
    rows = (db.query(ChangeHistory)
            .filter(ChangeHistory.object_type == "document",
                    ChangeHistory.object_id == doc_id)
            .order_by(ChangeHistory.ts.desc()).limit(200).all())
    return [{"ts": r.ts.isoformat(), "user_email": r.user_email, "field": r.field,
             "old_value": r.old_value, "new_value": r.new_value} for r in rows]


@router.get("/{doc_id}", response_model=DocumentDetail)
def get_document(
    doc_id: str, request: Request, db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.get(Document, doc_id)
    # Документ закрытой для роли категории отвечает так же, как отсутствующий:
    # 403 подтвердил бы сам факт существования документа. Отказ при этом
    # пишется в аудиторский след (попытки НСД, ТС-176 разд. 14 п. 8).
    if not doc or not access.can_see(db, user, doc, request):
        raise HTTPException(status_code=404, detail="Документ не найден")
    # История использования документа (п. 6.3 ТС «отслеживание истории
    # использования дел/документов»): просмотр карточки — тоже использование.
    audit.record(db, user, "document.view", "document", doc.id, doc.title,
                 request=request, action_type=AuditActionType.read)
    return doc


@router.get("/{doc_id}/usage")
def document_usage(doc_id: str, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> list[dict]:
    """Лист использования документа: кто и когда обращался (п. 6.3 ТС)."""
    doc = db.get(Document, doc_id)
    if not doc or not access.can_see(db, user, doc):
        raise HTTPException(status_code=404, detail="Документ не найден")
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.object_type == "document", AuditLog.object_id == doc_id)
        .order_by(AuditLog.ts.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "ts": r.ts.isoformat(), "user_email": r.user_email, "action": r.action,
            "action_type": r.action_type, "ip_address": r.ip_address,
            "detail": r.detail, "result": r.result,
        }
        for r in rows
    ]


@router.get("/{doc_id}/certified-copy")
def certified_copy(
    doc_id: str, db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Заверенная бумажная копия ЭД (п. 38/44 приказа № 236, ред. 2026):
    содержимое + штамп «Копия электронного документа верна» с результатом
    проверки ЭЦП и контрольной характеристикой."""
    doc = db.get(Document, doc_id)
    if not doc or doc.status == DocStatus.infected or not access.can_see(db, user, doc):
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
    doc_id: str, request: Request, db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.get(Document, doc_id)
    # Закрытая для роли категория отвечает как отсутствующий документ — иначе
    # ограничение доступа обходилось бы скачиванием оригинала по id. Попытка
    # пишется в аудиторский след (ТС-176 разд. 14 п. 8).
    if not doc or doc.status == DocStatus.infected or not access.can_see(db, user, doc, request):
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
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.admin, Role.archivist)),
):
    doc = db.get(Document, doc_id)
    if not doc or not access.can_see(db, user, doc):
        raise HTTPException(status_code=404, detail="Документ не найден")
    changes = payload.model_dump(exclude_none=True)
    before = history.snapshot(doc, [k for k in changes if k != "version"])
    # Оптимистичная блокировка (п. 6.4 ТС): с карточкой могут работать
    # несколько пользователей, но правка поверх чужой версии отклоняется,
    # иначе более позднее сохранение молча затирало бы чужие изменения.
    client_version = changes.pop("version", None)
    if client_version is not None and int(client_version) != (doc.version or 1):
        raise HTTPException(
            status_code=409,
            detail="Карточку уже изменил другой пользователь — обновите её и повторите",
        )
    for field, value in changes.items():
        setattr(doc, field, value)
    doc.version = (doc.version or 1) + 1
    db.commit()
    # История изменений по полям (п. 8) — отдельно от аудита: он фиксирует
    # факт правки, она — что именно стало другим.
    history.record(db, user, "document", doc.id, before, changes)
    audit.record(db, user, "document.update", "document", doc.id,
                 ", ".join(changes.keys()), request=request,
                 action_type=AuditActionType.update)
    db.refresh(doc)
    # Re-index metadata (does not touch the WORM-locked original).
    if doc.status == DocStatus.ready:
        search.index_document(_index_payload(doc))
    return doc


@router.get("/{doc_id}/pdfa")
def download_pdfa(
    doc_id: str, db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """PDF/A с текстовым слоем — результат оцифровки."""
    doc = db.get(Document, doc_id)
    if not doc or not access.can_see(db, user, doc):
        raise HTTPException(status_code=404, detail="Документ не найден")
    if not doc.pdfa_key:
        raise HTTPException(status_code=404,
                            detail="PDF/A для документа не сформирован")
    data = storage.get_object(doc.pdfa_key)
    return StreamingResponse(
        io.BytesIO(data), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc_id}.pdfa.pdf"'},
    )


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

    # Снимаем ссылки, удерживаемые внешними ключами. Отметка «дубль этого
    # документа» у других карточек теряет смысл вместе с оригиналом; позиции
    # архивных запросов сохраняются, но без ссылки на снятый документ —
    # иначе удаление падало бы на уровне БД.
    db.query(Document).filter(Document.duplicate_of_id == doc_id).update(
        {Document.duplicate_of_id: None}, synchronize_session=False
    )
    db.query(ExtractedEntity).filter(ExtractedEntity.document_id == doc_id).delete(
        synchronize_session=False
    )
    db.query(ArchiveRequestItem).filter(ArchiveRequestItem.document_id == doc_id).update(
        {ArchiveRequestItem.document_id: None}, synchronize_session=False
    )

    db.delete(doc)  # ЭРКК снимается каскадом (Document.reg_card)
    db.commit()
    # Из индекса убираем только после успешного commit: иначе сбой транзакции
    # оставил бы живой документ ненаходимым в поиске.
    search.delete_document(doc_id)
