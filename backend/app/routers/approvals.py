"""Маршруты согласования карточек дел и документов (п. 4.10 ТС-176).

Согласование последовательное: решение принимает согласующий текущего шага,
следующий шаг открывается только после положительного решения предыдущего.
Отказ на любом шаге закрывает весь маршрут.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    ApprovalRequest, ApprovalStep, ApprovalStatus, Case, Document, User, Role,
)
from ..schemas import ApprovalCreate, ApprovalDecision, ApprovalOut
from ..security import get_current_user, require_roles
from ..services import audit

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


def _title_for(db: Session, object_type: str, object_id: str) -> str:
    if object_type == "document":
        doc = db.get(Document, object_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Документ не найден")
        return doc.title
    if object_type == "case":
        case = db.get(Case, object_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Дело не найдено")
        return f"{case.index} · {case.title}" if case.index else case.title
    raise HTTPException(status_code=400, detail="Тип объекта: document или case")


def _current_step(req: ApprovalRequest) -> ApprovalStep | None:
    """Первый несогласованный шаг — именно он ожидает решения."""
    for s in sorted(req.steps, key=lambda x: x.order_no):
        if s.status == ApprovalStatus.pending:
            return s
    return None


@router.post("", response_model=ApprovalOut, status_code=201)
def create_approval(request: Request, payload: ApprovalCreate,
                    db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.admin, Role.archivist))):
    if not payload.steps:
        raise HTTPException(status_code=400, detail="Укажите хотя бы одного согласующего")
    title = _title_for(db, payload.object_type, payload.object_id)

    # Открытый маршрут по объекту должен быть один — иначе непонятно, чьё
    # решение считать итоговым.
    existing = (
        db.query(ApprovalRequest)
        .filter(ApprovalRequest.object_type == payload.object_type,
                ApprovalRequest.object_id == payload.object_id,
                ApprovalRequest.status == ApprovalStatus.pending)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409,
                            detail="По этому объекту уже идёт согласование")

    req = ApprovalRequest(
        object_type=payload.object_type, object_id=payload.object_id,
        title=title, created_by=user.email,
    )
    db.add(req)
    db.flush()
    for i, st in enumerate(sorted(payload.steps, key=lambda s: s.order_no), start=1):
        approver = db.query(User).filter(User.email == st.approver_email).first()
        db.add(ApprovalStep(
            request_id=req.id, order_no=i,
            approver_email=st.approver_email,
            approver_name=(approver.full_name if approver else ""),
        ))
    db.commit()
    db.refresh(req)
    audit.record(db, user, "approval.create", payload.object_type, payload.object_id,
                 f"маршрут согласования: {len(payload.steps)} шаг(ов)", request=request)
    return req


@router.get("", response_model=list[ApprovalOut])
def list_approvals(object_type: str | None = None, object_id: str | None = None,
                   db: Session = Depends(get_db),
                   _: User = Depends(get_current_user)):
    q = db.query(ApprovalRequest)
    if object_type:
        q = q.filter(ApprovalRequest.object_type == object_type)
    if object_id:
        q = q.filter(ApprovalRequest.object_id == object_id)
    return q.order_by(ApprovalRequest.created_at.desc()).limit(200).all()


@router.get("/my", response_model=list[ApprovalOut])
def my_approvals(db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """Маршруты, где решение ожидается от текущего пользователя."""
    reqs = (
        db.query(ApprovalRequest)
        .join(ApprovalStep, ApprovalStep.request_id == ApprovalRequest.id)
        .filter(ApprovalRequest.status == ApprovalStatus.pending,
                ApprovalStep.approver_email == user.email,
                ApprovalStep.status == ApprovalStatus.pending)
        .order_by(ApprovalRequest.created_at.desc())
        .all()
    )
    # Показываем только те, где ход действительно за этим пользователем.
    # Дубликаты снимаем вручную: set() потерял бы порядок, заданный order_by.
    seen: set[str] = set()
    out: list[ApprovalRequest] = []
    for r in reqs:
        if r.id in seen:
            continue
        seen.add(r.id)
        cs = _current_step(r)
        if cs and cs.approver_email == user.email:
            out.append(r)
    return out


@router.post("/{req_id}/decide", response_model=ApprovalOut)
def decide(request: Request, req_id: str, payload: ApprovalDecision,
           db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    req = db.get(ApprovalRequest, req_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Маршрут не найден")
    if req.status != ApprovalStatus.pending:
        raise HTTPException(status_code=409, detail="Маршрут уже закрыт")

    step = _current_step(req)
    if step is None:
        raise HTTPException(status_code=409, detail="Нет шагов, ожидающих решения")
    if step.approver_email != user.email:
        raise HTTPException(status_code=403,
                            detail="Сейчас решение принимает другой согласующий")

    step.status = ApprovalStatus.approved if payload.approve else ApprovalStatus.rejected
    step.comment = payload.comment
    step.decided_at = datetime.utcnow()

    if not payload.approve:
        req.status = ApprovalStatus.rejected
        req.closed_at = datetime.utcnow()
    elif _current_step(req) is None:
        req.status = ApprovalStatus.approved
        req.closed_at = datetime.utcnow()
    db.commit()
    db.refresh(req)
    audit.record(db, user, "approval.decide", req.object_type, req.object_id,
                 f"{'согласовано' if payload.approve else 'отклонено'}: {req.title}",
                 request=request)
    return req
