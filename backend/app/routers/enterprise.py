"""Модуль «Предприятие» (п. 4.8 ТС-176): сведения об организации,
её оргструктура и подписанты. Оргструктура используется маршрутами
согласования (п. 4.10) — руководителя подразделения подставляют шаблоны
маршрутов — и подстановкой реквизитов в нормативные формы.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ApprovalRouteTemplate, Organization, Department, User, Role
from ..schemas import (
    OrganizationIn, OrganizationOut, DepartmentIn, DepartmentOut, UserOut,
)
from ..security import get_current_user, require_roles
from ..services import audit, routes

router = APIRouter(prefix="/api/enterprise", tags=["enterprise"])


def _single(db: Session) -> Organization | None:
    """Организация в системе одна — это архив конкретного заказчика."""
    return db.query(Organization).order_by(Organization.updated_at.desc()).first()


@router.get("/organization", response_model=OrganizationOut | None)
def get_organization(db: Session = Depends(get_db),
                     _: User = Depends(get_current_user)):
    return _single(db)


@router.put("/organization", response_model=OrganizationOut)
def save_organization(request: Request, payload: OrganizationIn,
                      db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.admin))):
    org = _single(db)
    if org is None:
        org = Organization(**payload.model_dump())
        db.add(org)
    else:
        for field, value in payload.model_dump().items():
            setattr(org, field, value)
    db.commit()
    db.refresh(org)
    audit.record(db, user, "organization.save", "organization", org.id,
                 org.name, request=request)
    return org


def _dep_out(d: Department, users_count: int, head_email: str) -> DepartmentOut:
    return DepartmentOut(
        id=d.id, name=d.name, index=d.index, parent_id=d.parent_id,
        head_name=d.head_name, head_position=d.head_position,
        head_user_id=d.head_user_id, head_user_email=head_email,
        users_count=users_count,
    )


def _head_email(db: Session, user_id: str | None) -> str:
    head = db.get(User, user_id) if user_id else None
    return head.email if head else ""


def _apply(db: Session, dep: Department, payload: DepartmentIn) -> None:
    """Общие правила создания и правки подразделения."""
    data = payload.model_dump()
    data["parent_id"] = data.get("parent_id") or None
    data["head_user_id"] = data.get("head_user_id") or None
    if data["parent_id"]:
        if db.get(Department, data["parent_id"]) is None:
            raise HTTPException(status_code=400, detail="Вышестоящее подразделение не найдено")
        parents = dict(db.query(Department.id, Department.parent_id).all())
        if dep.id and routes.creates_cycle(dep.id, data["parent_id"], parents):
            raise HTTPException(
                status_code=400,
                detail="Подразделение не может подчиняться самому себе или своему дочернему",
            )
    if data["head_user_id"]:
        head = db.get(User, data["head_user_id"])
        if head is None or not head.is_active:
            raise HTTPException(status_code=400,
                                detail="Руководитель: учётная запись не найдена или отключена")
        # Реквизиты печатных форм, не заданные явно, — из учётной записи.
        data["head_name"] = data["head_name"] or head.full_name
        data["head_position"] = data["head_position"] or head.position
    for field, value in data.items():
        setattr(dep, field, value)


@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(db: Session = Depends(get_db),
                     _: User = Depends(get_current_user)):
    deps = db.query(Department).order_by(Department.index, Department.name).all()
    counts = dict(
        db.query(User.department_id, func.count(User.id))
        .filter(User.department_id.isnot(None))
        .group_by(User.department_id)
        .all()
    )
    head_ids = {d.head_user_id for d in deps if d.head_user_id}
    emails = (dict(db.query(User.id, User.email).filter(User.id.in_(head_ids)).all())
              if head_ids else {})
    return [_dep_out(d, counts.get(d.id, 0), emails.get(d.head_user_id, "")) for d in deps]


@router.post("/departments", response_model=DepartmentOut, status_code=201)
def create_department(request: Request, payload: DepartmentIn,
                      db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.admin))):
    dep = Department(name=payload.name)
    _apply(db, dep, payload)
    db.add(dep)
    db.commit()
    db.refresh(dep)
    audit.record(db, user, "department.create", "department", dep.id, dep.name,
                 request=request)
    return _dep_out(dep, 0, _head_email(db, dep.head_user_id))


@router.put("/departments/{dep_id}", response_model=DepartmentOut)
def update_department(request: Request, dep_id: str, payload: DepartmentIn,
                      db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.admin))):
    """Правка подразделения, в том числе смена руководителя: уже запущенные
    маршруты остаются за прежним согласующим, новые пойдут новому."""
    dep = db.get(Department, dep_id)
    if dep is None:
        raise HTTPException(status_code=404, detail="Подразделение не найдено")
    _apply(db, dep, payload)
    db.commit()
    db.refresh(dep)
    audit.record(db, user, "department.update", "department", dep.id, dep.name,
                 request=request)
    users_count = db.query(User).filter(User.department_id == dep.id).count()
    return _dep_out(dep, users_count, _head_email(db, dep.head_user_id))


@router.delete("/departments/{dep_id}", status_code=204)
def delete_department(request: Request, dep_id: str, db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.admin))):
    dep = db.get(Department, dep_id)
    if dep is None:
        raise HTTPException(status_code=404, detail="Подразделение не найдено")
    # Подразделение с сотрудниками или дочерними узлами удалять нельзя: иначе
    # сотрудники потеряли бы принадлежность, а дерево — целостность.
    if db.query(User).filter(User.department_id == dep_id).count():
        raise HTTPException(status_code=409,
                            detail="В подразделении есть сотрудники — перенесите их сначала")
    if db.query(Department).filter(Department.parent_id == dep_id).count():
        raise HTTPException(status_code=409,
                            detail="У подразделения есть дочерние — удалите их сначала")
    # Шаблон, ссылающийся на подразделение, перестал бы запускаться.
    used_by = [t.name for t in db.query(ApprovalRouteTemplate).all()
               if any(s.get("kind") == "department_head" and s.get("value") == dep_id
                      for s in t.steps or [])]
    if used_by:
        raise HTTPException(status_code=409,
                            detail="Подразделение указано в шаблонах маршрутов: "
                                   + ", ".join(used_by[:3]))
    db.delete(dep)
    db.commit()
    audit.record(db, user, "department.delete", "department", dep_id, dep.name,
                 request=request)


@router.get("/signers", response_model=list[UserOut])
def list_signers(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Подписанты организации — сотрудники с правом подписи (п. 4.8 ТС)."""
    users = (
        db.query(User)
        .filter(User.can_sign.is_(True), User.is_active.is_(True))
        .order_by(User.full_name)
        .all()
    )
    out = []
    for u in users:
        dep = db.get(Department, u.department_id) if u.department_id else None
        out.append(UserOut(
            id=u.id, email=u.email, full_name=u.full_name, role=u.role,
            position=u.position, department_id=u.department_id,
            department_name=(dep.name if dep else None), can_sign=u.can_sign,
            is_active=u.is_active, locked=u.locked_at is not None,
        ))
    return out
