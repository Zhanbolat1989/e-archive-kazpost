"""Маршруты согласования карточек дел, документов и статей номенклатуры
(п. 4.10 ТС-176).

Согласование последовательное: решение принимает согласующий текущего шага,
следующий шаг открывается только после положительного решения предыдущего.
Отказ на любом шаге закрывает весь маршрут.

Согласующих подставляет шаблон маршрута по оргструктуре (services/routes.py).
Перечень согласующих вручную оставлен для разовых маршрутов и интеграций.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    ApprovalRequest, ApprovalRouteTemplate, ApprovalStep, ApprovalStatus, Case,
    Department, Document, NomenclatureItem, User, Role,
)
from ..schemas import (
    ApprovalCreate, ApprovalDecision, ApprovalOut, ApprovalPlanStep,
    RouteTemplateIn, RouteTemplateOut,
)
from ..security import get_current_user, require_roles
from ..services import audit, routes

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


def _target(db: Session, object_type: str, object_id: str) -> tuple[str, str | None]:
    """Заголовок объекта и его подразделение — от него считаются руководители."""
    if object_type == "document":
        doc = db.get(Document, object_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Документ не найден")
        return doc.title, doc.department_id
    if object_type == "case":
        case = db.get(Case, object_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Дело не найдено")
        return (f"{case.index} · {case.title}" if case.index else case.title), case.department_id
    if object_type == "nomenclature":
        item = db.get(NomenclatureItem, object_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Статья номенклатуры не найдена")
        return f"Номенклатура {item.year}: {item.index} · {item.title}", item.department_id
    raise HTTPException(status_code=400,
                        detail="Тип объекта: document, case или nomenclature")


def _org(db: Session) -> tuple[dict[str, routes.Unit], dict[str, str]]:
    """Оргструктура и действующие учётные записи {email: ФИО} для подстановки."""
    active = db.query(User.id, User.email, User.full_name).filter(User.is_active.is_(True)).all()
    email_by_id = {u.id: u.email for u in active}
    units = {
        d.id: routes.Unit(d.name, d.parent_id, email_by_id.get(d.head_user_id, ""))
        for d in db.query(Department).all()
    }
    return units, {u.email: u.full_name for u in active}


def _plan(db: Session, payload: ApprovalCreate,
          user: User) -> tuple[list[routes.PlannedStep], str, str]:
    """Согласующие маршрута, заголовок объекта и имя шаблона."""
    title, department_id = _target(db, payload.object_type, payload.object_id)
    if payload.template_id:
        tpl = db.get(ApprovalRouteTemplate, payload.template_id)
        if tpl is None or not tpl.is_active:
            raise HTTPException(status_code=404, detail="Шаблон маршрута не найден или отключён")
        if tpl.object_type and tpl.object_type != payload.object_type:
            raise HTTPException(
                status_code=400,
                detail=f"Шаблон «{tpl.name}» предназначен для другого вида объектов: "
                       f"{routes.OBJECT_TYPES.get(tpl.object_type, tpl.object_type)}",
            )
        units, users = _org(db)
        try:
            steps = routes.resolve(tpl.steps, department_id or user.department_id,
                                   units, users, user.email)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return steps, title, tpl.name

    if not payload.steps:
        raise HTTPException(status_code=400,
                            detail="Выберите шаблон маршрута или укажите согласующих")
    ordered = sorted(payload.steps, key=lambda s: s.order_no)
    names = dict(db.query(User.email, User.full_name)
                 .filter(User.email.in_([s.approver_email for s in ordered])).all())
    return ([routes.PlannedStep(s.approver_email, names.get(s.approver_email, ""), "")
             for s in ordered], title, "")


def _current_step(req: ApprovalRequest) -> ApprovalStep | None:
    """Первый несогласованный шаг — именно он ожидает решения."""
    for s in sorted(req.steps, key=lambda x: x.order_no):
        if s.status == ApprovalStatus.pending:
            return s
    return None


@router.get("/meta")
def approvals_meta(_: User = Depends(get_current_user)) -> dict:
    return {
        "step_kinds": [{"key": k, "label": v} for k, v in routes.STEP_KINDS.items()],
        "object_types": [{"key": k, "label": v} for k, v in routes.OBJECT_TYPES.items()],
    }


# ---- Шаблоны маршрутов ----

def _template_fields(db: Session, payload: RouteTemplateIn) -> dict:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Укажите название шаблона")
    if payload.object_type not in routes.OBJECT_TYPES:
        raise HTTPException(status_code=400,
                            detail="Вид объекта: document, case, nomenclature или пусто")
    try:
        steps = routes.normalize_steps([s.model_dump() for s in payload.steps])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Ссылки шаблона проверяются при сохранении: иначе ошибка всплыла бы только
    # при запуске маршрута — у архивариуса, который её не исправит.
    dep_ids = {s["value"] for s in steps if s["kind"] == "department_head"}
    if dep_ids and db.query(Department).filter(Department.id.in_(dep_ids)).count() != len(dep_ids):
        raise HTTPException(status_code=400, detail="Подразделение шаблона не найдено")
    emails = {s["value"] for s in steps if s["kind"] == "user"}
    if emails and (db.query(User).filter(User.email.in_(emails), User.is_active.is_(True))
                   .count() != len(emails)):
        raise HTTPException(status_code=400,
                            detail="Сотрудник шаблона не найден или отключён")
    return {"name": name, "object_type": payload.object_type, "steps": steps,
            "is_active": payload.is_active}


@router.get("/templates", response_model=list[RouteTemplateOut])
def list_templates(object_type: str | None = None, include_inactive: bool = False,
                   db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """Шаблоны для запуска маршрута; с `object_type` — подходящие этому виду
    объектов, включая универсальные."""
    q = db.query(ApprovalRouteTemplate)
    if not (include_inactive and user.role == Role.admin):
        q = q.filter(ApprovalRouteTemplate.is_active.is_(True))
    if object_type:
        q = q.filter(ApprovalRouteTemplate.object_type.in_([object_type, ""]))
    return q.order_by(ApprovalRouteTemplate.name).all()


@router.post("/templates", response_model=RouteTemplateOut, status_code=201)
def create_template(request: Request, payload: RouteTemplateIn,
                    db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.admin))):
    tpl = ApprovalRouteTemplate(**_template_fields(db, payload))
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    audit.record(db, user, "approval_template.create", "approval_template", tpl.id,
                 f"{tpl.name}: {len(tpl.steps)} шаг(ов)", request=request)
    return tpl


@router.put("/templates/{template_id}", response_model=RouteTemplateOut)
def update_template(request: Request, template_id: str, payload: RouteTemplateIn,
                    db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.admin))):
    """Правка шаблона не меняет уже запущенные маршруты: их шаги сохранены."""
    tpl = db.get(ApprovalRouteTemplate, template_id)
    if tpl is None:
        raise HTTPException(status_code=404, detail="Шаблон маршрута не найден")
    for field, value in _template_fields(db, payload).items():
        setattr(tpl, field, value)
    db.commit()
    db.refresh(tpl)
    audit.record(db, user, "approval_template.update", "approval_template", tpl.id,
                 f"{tpl.name}: {len(tpl.steps)} шаг(ов)"
                 f"{'' if tpl.is_active else ', отключён'}", request=request)
    return tpl


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(request: Request, template_id: str,
                    db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.admin))):
    tpl = db.get(ApprovalRouteTemplate, template_id)
    if tpl is None:
        raise HTTPException(status_code=404, detail="Шаблон маршрута не найден")
    name = tpl.name
    db.delete(tpl)
    db.commit()
    audit.record(db, user, "approval_template.delete", "approval_template", template_id,
                 name, request=request)


# ---- Маршруты ----

@router.post("/preview", response_model=list[ApprovalPlanStep])
def preview_approval(payload: ApprovalCreate, db: Session = Depends(get_db),
                     user: User = Depends(require_roles(Role.admin, Role.archivist))):
    """Кому уйдёт маршрут — до запуска: подставленные руководители видны заранее."""
    steps, _, _ = _plan(db, payload, user)
    return [ApprovalPlanStep(order_no=i, approver_email=s.approver_email,
                             approver_name=s.approver_name, basis=s.basis)
            for i, s in enumerate(steps, start=1)]


@router.post("", response_model=ApprovalOut, status_code=201)
def create_approval(request: Request, payload: ApprovalCreate,
                    db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.admin, Role.archivist))):
    steps, title, template_name = _plan(db, payload, user)

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
        title=title, template_name=template_name, created_by=user.email,
    )
    db.add(req)
    db.flush()
    for i, st in enumerate(steps, start=1):
        db.add(ApprovalStep(
            request_id=req.id, order_no=i,
            approver_email=st.approver_email,
            approver_name=st.approver_name,
            basis=st.basis,
        ))
    # Статья номенклатуры, отправленная на маршрут, сразу получает статус
    # «На согласовании»: иначе в реестре она выглядела бы проектом, пока
    # согласующие уже принимают по ней решение.
    if payload.object_type == "nomenclature":
        item = db.get(NomenclatureItem, payload.object_id)
        if item is not None and item.status == "Проект":
            item.status = "На согласовании"
    db.commit()
    db.refresh(req)
    via = f" по шаблону «{template_name}»" if template_name else ""
    audit.record(db, user, "approval.create", payload.object_type, payload.object_id,
                 f"маршрут согласования{via}: {len(steps)} шаг(ов)", request=request)
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
