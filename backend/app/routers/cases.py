from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..autonumber import next_case_index
from ..db import get_db
from ..models import (
    User, Role, Case, CaseStatus, Document, NomenclatureItem,
)
from ..retention import compute_until
from ..schemas import CaseCreate, CaseUpdate, CaseOut, CaseDetail
from ..security import get_current_user, require_roles

router = APIRouter(prefix="/api/cases", tags=["cases"])


def _with_count(db: Session, case: Case) -> CaseOut:
    n = db.query(func.count(Document.id)).filter(Document.case_id == case.id).scalar()
    out = CaseOut.model_validate(case)
    out.documents_count = int(n or 0)
    return out


def _refresh_dates(db: Session, case: Case) -> None:
    """Крайние даты дела = мин/макс дат документов; retention_until — от года
    закрытия (date_to) либо года дела."""
    lo, hi = db.query(
        func.min(Document.doc_date), func.max(Document.doc_date)
    ).filter(Document.case_id == case.id, Document.doc_date.isnot(None)).one()
    case.date_from, case.date_to = lo, hi
    base_year = (hi or date(case.year, 12, 31)).year
    case.retention_until = compute_until(base_year, case.retention_years)


@router.get("", response_model=list[CaseOut])
def list_cases(
    db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    cases = db.query(Case).order_by(Case.year.desc(), Case.index).all()
    return [_with_count(db, c) for c in cases]


@router.post("", response_model=CaseOut, status_code=201)
def create_case(
    payload: CaseCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.admin, Role.archivist)),
):
    nom = db.get(NomenclatureItem, payload.nomenclature_id) if payload.nomenclature_id else None
    year = payload.year or datetime.utcnow().year
    index = payload.index or (nom.index if nom else "") or next_case_index(db, year)
    case = Case(
        nomenclature_id=nom.id if nom else None,
        index=index,
        title=payload.title or (nom.title if nom else ""),
        volume=payload.volume,
        year=year,
        note=payload.note,
        retention_label=nom.retention_label if nom else "",
        retention_years=nom.retention_years if nom else None,
        permanent=nom.permanent if nom else False,
    )
    case.retention_until = compute_until(year, case.retention_years)
    db.add(case)
    db.commit()
    db.refresh(case)
    return _with_count(db, case)


@router.get("/{case_id}", response_model=CaseDetail)
def get_case(
    case_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Дело не найдено")
    docs = (
        db.query(Document)
        .filter(Document.case_id == case_id)
        .order_by(Document.doc_date.asc().nullslast(), Document.created_at)
        .all()
    )
    out = CaseDetail.model_validate(case)
    out.documents_count = len(docs)
    out.documents = docs
    return out


@router.patch("/{case_id}", response_model=CaseOut)
def update_case(
    case_id: str,
    payload: CaseUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.admin, Role.archivist)),
):
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Дело не найдено")
    if payload.status == CaseStatus.destroyed:
        raise HTTPException(
            status_code=400,
            detail="Статус «Уничтожено» присваивается только через утверждённый "
                   "акт о выделении к уничтожению",
        )
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(case, field, value)
    if payload.status == CaseStatus.closed:
        _refresh_dates(db, case)
    db.commit()
    db.refresh(case)
    return _with_count(db, case)


@router.post("/{case_id}/documents/{doc_id}", response_model=CaseDetail)
def add_document(
    case_id: str,
    doc_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.admin, Role.archivist)),
):
    case = db.get(Case, case_id)
    doc = db.get(Document, doc_id)
    if not case or not doc:
        raise HTTPException(status_code=404, detail="Дело или документ не найдены")
    doc.case_id = case.id
    # Срок дела распространяется на документ (номенклатура приоритетнее типа).
    if case.retention_years or case.permanent:
        doc.retention_label = case.retention_label
        doc.retention_years = case.retention_years
        doc.permanent = case.permanent
        base_year = (doc.doc_date or doc.created_at.date()).year
        doc.retention_until = compute_until(base_year, case.retention_years)
    _refresh_dates(db, case)
    db.commit()
    return get_case(case_id, db, _)


@router.delete("/{case_id}/documents/{doc_id}", response_model=CaseDetail)
def remove_document(
    case_id: str,
    doc_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.admin, Role.archivist)),
):
    doc = db.get(Document, doc_id)
    if not doc or doc.case_id != case_id:
        raise HTTPException(status_code=404, detail="Документ не найден в деле")
    doc.case_id = None
    case = db.get(Case, case_id)
    _refresh_dates(db, case)
    db.commit()
    return get_case(case_id, db, _)
