"""Модуль «Предприятие» (п. 4.8 ТС-176): сведения об организации,
её оргструктура и подписанты. Оргструктура используется маршрутами
согласования (п. 4.10) и подстановкой реквизитов в нормативные формы.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Organization, Department, User, Role
from ..schemas import (
    OrganizationIn, OrganizationOut, DepartmentIn, DepartmentOut, UserOut,
)
from ..security import get_current_user, require_roles
from ..services import audit

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
    return [
        DepartmentOut(
            id=d.id, name=d.name, index=d.index, parent_id=d.parent_id,
            head_name=d.head_name, head_position=d.head_position,
            users_count=counts.get(d.id, 0),
        )
        for d in deps
    ]


@router.post("/departments", response_model=DepartmentOut, status_code=201)
def create_department(request: Request, payload: DepartmentIn,
                      db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.admin))):
    data = payload.model_dump()
    data["parent_id"] = data.get("parent_id") or None
    dep = Department(**data)
    db.add(dep)
    db.commit()
    db.refresh(dep)
    audit.record(db, user, "department.create", "department", dep.id, dep.name,
                 request=request)
    return DepartmentOut(
        id=dep.id, name=dep.name, index=dep.index, parent_id=dep.parent_id,
        head_name=dep.head_name, head_position=dep.head_position, users_count=0,
    )


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
