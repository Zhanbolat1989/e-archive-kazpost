import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User, Role, Case, CaseStatus, IssueRecord, IssueStatus
from ..schemas import IssueCreate, IssueOut
from ..security import get_current_user, require_roles
from ..services import forms as forms_svc
from ..services import audit

router = APIRouter(prefix="/api/issues", tags=["issues"])


def _out(issue: IssueRecord, case: Case | None) -> IssueOut:
    out = IssueOut.model_validate(issue)
    if case:
        out.case_index = case.index
        out.case_title = case.title
    out.overdue = (
        issue.status == IssueStatus.issued
        and issue.due_date is not None
        and issue.due_date < date.today()
    )
    return out


@router.get("", response_model=list[IssueOut])
def list_issues(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Книга выдачи дел (прил. 22)."""
    issues = db.query(IssueRecord).order_by(IssueRecord.order_date.desc()).all()
    return [_out(i, db.get(Case, i.case_id)) for i in issues]


@router.post("", response_model=IssueOut, status_code=201)
def create_issue(payload: IssueCreate, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.admin, Role.archivist))):
    """Заказ на выдачу дела (прил. 20)."""
    case = db.get(Case, payload.case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Дело не найдено")
    if case.status == CaseStatus.destroyed:
        raise HTTPException(status_code=409, detail="Дело уничтожено — выдача невозможна")
    active = (db.query(IssueRecord)
              .filter(IssueRecord.case_id == case.id,
                      IssueRecord.status == IssueStatus.issued).first())
    if active:
        raise HTTPException(status_code=409,
                            detail=f"Дело уже на руках у: {active.requested_by}")
    issue = IssueRecord(
        case_id=case.id,
        requested_by=payload.requested_by,
        purpose=payload.purpose,
        due_date=payload.due_date,
        created_by=user.full_name or user.email,
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)
    audit.record(db, user, "issue.request", "case", case.id,
                 f"{case.index} → {payload.requested_by}")
    return _out(issue, case)


@router.post("/{issue_id}/issue", response_model=IssueOut)
def mark_issued(issue_id: str, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.admin, Role.archivist))):
    issue = db.get(IssueRecord, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    if issue.status != IssueStatus.requested:
        raise HTTPException(status_code=409, detail="Заказ уже обработан")
    issue.status = IssueStatus.issued
    issue.issue_date = date.today()
    db.commit()
    db.refresh(issue)
    audit.record(db, user, "issue.given", "case", issue.case_id, issue.requested_by)
    return _out(issue, db.get(Case, issue.case_id))


@router.post("/{issue_id}/return", response_model=IssueOut)
def mark_returned(issue_id: str, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.admin, Role.archivist))):
    issue = db.get(IssueRecord, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    if issue.status != IssueStatus.issued:
        raise HTTPException(status_code=409, detail="Дело не находится на руках")
    issue.status = IssueStatus.returned
    issue.returned_at = date.today()
    db.commit()
    db.refresh(issue)
    audit.record(db, user, "issue.returned", "case", issue.case_id, issue.requested_by)
    return _out(issue, db.get(Case, issue.case_id))


@router.get("/{issue_id}/act")
def issue_act(issue_id: str, db: Session = Depends(get_db),
              _: User = Depends(get_current_user)):
    """Акт о выдаче дел во временное пользование (прил. 21), PDF."""
    issue = db.get(IssueRecord, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    case = db.get(Case, issue.case_id)
    data = forms_svc.issue_act_pdf(issue, case)
    return StreamingResponse(
        io.BytesIO(data), media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="issue_act.pdf"'},
    )
