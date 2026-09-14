"""Модуль «Архивные запросы» (ТЗ АГП п. 8).

Обращение за сведениями или копиями документов: регистрация, исполнитель, срок
исполнения, статус, ответ заявителю и перечень документов/дел, по которым запрос
исполнен. От «Выдачи дел» отличается предметом: там дело физически выдаётся
пользователю, здесь готовится ответ на обращение.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    ArchiveRequest, ArchiveRequestItem, Case, Document, REQUEST_STATUSES,
    Role, User,
)
from ..schemas import ArchiveRequestCreate, ArchiveRequestOut, ArchiveRequestUpdate
from ..security import get_current_user, require_roles
from ..services import audit, dictionaries, history

router = APIRouter(prefix="/api/archive-requests", tags=["archive-requests"])

# Срок исполнения архивного запроса по умолчанию — 30 календарных дней
# (ст. 8 Закона РК «О порядке рассмотрения обращений»).
DEFAULT_DUE_DAYS = 30
CLOSED_STATUSES = ("Исполнен", "Отказано")


def _check_type(db: Session, value: str) -> None:
    """Вид запроса — из справочника «Виды архивных запросов» (ТС-176 п. 4.9)."""
    try:
        dictionaries.check_value("request_types", value,
                                 dictionaries.active_values(db, "request_types"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _next_number(db: Session, year: int) -> str:
    used = (db.query(ArchiveRequest)
            .filter(ArchiveRequest.number.like(f"ЗАП-{year}/%")).count())
    return f"ЗАП-{year}/{used + 1:03d}"


def _out(db: Session, req: ArchiveRequest) -> ArchiveRequestOut:
    out = ArchiveRequestOut.model_validate(req)
    out.documents_count = (db.query(ArchiveRequestItem)
                           .filter(ArchiveRequestItem.request_id == req.id).count())
    out.overdue = bool(req.due_date and req.status not in CLOSED_STATUSES
                       and req.due_date < date.today())
    return out


def _set_items(db: Session, req: ArchiveRequest,
               document_ids: list[str] | None, case_ids: list[str] | None) -> None:
    """Перечень документов и дел, использованных при исполнении запроса, —
    основа отчётности по обращениям к документам (п. 8, «Отчетность»)."""
    if document_ids is None and case_ids is None:
        return
    (db.query(ArchiveRequestItem)
     .filter(ArchiveRequestItem.request_id == req.id).delete(synchronize_session=False))
    for did in document_ids or []:
        if db.get(Document, did) is not None:
            db.add(ArchiveRequestItem(request_id=req.id, document_id=did))
    for cid in case_ids or []:
        if db.get(Case, cid) is not None:
            db.add(ArchiveRequestItem(request_id=req.id, case_id=cid))


@router.get("", response_model=list[ArchiveRequestOut])
def list_requests(
    status: str | None = None,
    year: int | None = None,
    executor_email: str | None = None,
    overdue: bool | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(ArchiveRequest)
    if status:
        q = q.filter(ArchiveRequest.status == status)
    if year:
        q = q.filter(ArchiveRequest.reg_date >= date(year, 1, 1),
                     ArchiveRequest.reg_date <= date(year, 12, 31))
    if executor_email:
        q = q.filter(ArchiveRequest.executor_email == executor_email)
    rows = q.order_by(ArchiveRequest.reg_date.desc(),
                      ArchiveRequest.created_at.desc()).limit(500).all()
    out = [_out(db, r) for r in rows]
    if overdue is not None:
        out = [r for r in out if r.overdue is overdue]
    return out


@router.get("/meta/statuses")
def statuses(_: User = Depends(get_current_user)) -> list[str]:
    return list(REQUEST_STATUSES)


@router.post("", response_model=ArchiveRequestOut, status_code=201)
def create_request(
    payload: ArchiveRequestCreate, request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.admin, Role.archivist)),
):
    _check_type(db, payload.request_type)
    reg = payload.reg_date or date.today()
    req = ArchiveRequest(
        number=payload.number.strip() or _next_number(db, reg.year),
        reg_date=reg,
        applicant=payload.applicant,
        applicant_contact=payload.applicant_contact,
        request_type=payload.request_type,
        subject=payload.subject,
        due_date=payload.due_date or (reg + timedelta(days=DEFAULT_DUE_DAYS)),
        executor_email=payload.executor_email,
        department_id=payload.department_id,
        created_by=user.email,
    )
    db.add(req)
    db.flush()
    _set_items(db, req, payload.document_ids, payload.case_ids)
    db.commit()
    db.refresh(req)
    audit.record(db, user, "archive_request.create", "archive_request", req.id,
                 f"{req.number}: {req.applicant}", request=request)
    return _out(db, req)


@router.get("/{req_id}", response_model=ArchiveRequestOut)
def get_request(req_id: str, db: Session = Depends(get_db),
                _: User = Depends(get_current_user)):
    req = db.get(ArchiveRequest, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Запрос не найден")
    return _out(db, req)


@router.get("/{req_id}/items")
def request_items(req_id: str, db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)) -> list[dict]:
    """Документы и дела, по которым исполнялся запрос."""
    rows = (db.query(ArchiveRequestItem)
            .filter(ArchiveRequestItem.request_id == req_id).all())
    out: list[dict] = []
    for r in rows:
        if r.document_id:
            doc = db.get(Document, r.document_id)
            if doc is not None:
                out.append({"kind": "document", "id": doc.id, "title": doc.title,
                            "number": doc.doc_number})
        elif r.case_id:
            case = db.get(Case, r.case_id)
            if case is not None:
                out.append({"kind": "case", "id": case.id, "title": case.title,
                            "number": case.index})
    return out


@router.patch("/{req_id}", response_model=ArchiveRequestOut)
def update_request(
    req_id: str, payload: ArchiveRequestUpdate, request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.admin, Role.archivist)),
):
    req = db.get(ArchiveRequest, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Запрос не найден")
    changes = payload.model_dump(exclude_none=True)
    client_version = changes.pop("version", None)
    if client_version is not None and int(client_version) != (req.version or 1):
        raise HTTPException(status_code=409,
                            detail="Запрос уже изменил другой пользователь — "
                                   "обновите карточку и повторите")
    if "status" in changes and changes["status"] not in REQUEST_STATUSES:
        raise HTTPException(status_code=400,
                            detail="Недопустимый статус запроса: " + changes["status"])
    # Вид, выведенный из употребления после регистрации, не мешает править
    # остальные поля; проверяется только новое значение.
    if "request_type" in changes and changes["request_type"] != req.request_type:
        _check_type(db, changes["request_type"])

    document_ids = changes.pop("document_ids", None)
    case_ids = changes.pop("case_ids", None)
    before = history.snapshot(req, list(changes))
    for field, value in changes.items():
        setattr(req, field, value)
    # Запрос закрыт — фиксируем дату исполнения: по ней считается соблюдение
    # срока в отчётности, и вычислить её задним числом уже нельзя.
    if changes.get("status") in CLOSED_STATUSES and req.completed_at is None:
        req.completed_at = date.today()
    if changes.get("status") not in CLOSED_STATUSES and "status" in changes:
        req.completed_at = None
    _set_items(db, req, document_ids, case_ids)
    req.version = (req.version or 1) + 1
    db.commit()
    history.record(db, user, "archive_request", req.id, before, changes)
    audit.record(db, user, "archive_request.update", "archive_request", req.id,
                 ", ".join(changes.keys()), request=request)
    db.refresh(req)
    return _out(db, req)


@router.delete("/{req_id}", status_code=204)
def delete_request(req_id: str, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.admin))):
    req = db.get(ArchiveRequest, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Запрос не найден")
    (db.query(ArchiveRequestItem)
     .filter(ArchiveRequestItem.request_id == req_id).delete(synchronize_session=False))
    db.delete(req)
    db.commit()
    audit.record(db, user, "archive_request.delete", "archive_request", req_id,
                 req.number, request=request)
