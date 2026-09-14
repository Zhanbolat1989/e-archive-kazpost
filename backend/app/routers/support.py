"""Обращения в поддержку и SLA (ТС-176 разд. 13; разд. 14 п. 2.9, 2.10, 6.1, 9).

Помимо вопросов и ошибок принимает инциденты со сроками реакции и устранения по
уровню критичности, инциденты ИБ (с немедленным уведомлением ответственных) и
заявки на дополнительные услуги из Личного кабинета. Обращение видно автору,
администратору и аудитору ИБ; отвечает и берёт в работу администратор.
"""
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Role, SupportTicket, User
from ..schemas import (
    SupportTicketAnswer, SupportTicketCreate, SupportTicketOut, SupportTicketReopen,
)
from ..security import get_current_user, require_roles
from ..services import audit, availability, mailer, sla

router = APIRouter(prefix="/api/support", tags=["support"])

STAFF = (Role.admin, Role.auditor)


def _out(ticket: SupportTicket, now: datetime | None = None) -> SupportTicketOut:
    now = now or datetime.utcnow()
    out = SupportTicketOut.model_validate(ticket)
    out.overdue = bool(ticket.resolution_due and ticket.resolved_at is None
                       and ticket.status != sla.STATUS_CLOSED
                       and now > ticket.resolution_due)
    return out


def _ticket(db: Session, ticket_id: str, user: User) -> SupportTicket:
    ticket = db.get(SupportTicket, ticket_id)
    if ticket is None or (user.role not in STAFF and ticket.user_email != user.email):
        raise HTTPException(status_code=404, detail="Обращение не найдено")
    return ticket


@router.get("/meta")
def meta(_: User = Depends(get_current_user)) -> dict:
    return {
        "kinds": [{"key": k, "label": v} for k, v in sla.KINDS.items()],
        "services": [{"key": k, "label": v} for k, v in sla.SERVICES.items()],
        "levels": [{"key": k, **v} for k, v in sla.LEVELS.items()],
        "statuses": list(sla.STATUSES),
    }


@router.get("", response_model=list[SupportTicketOut])
def list_tickets(mine: bool = False, status: str | None = None, kind: str | None = None,
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    q = db.query(SupportTicket)
    # Не администратору и не аудитору доступны только собственные обращения —
    # независимо от того, что запросил клиент.
    if mine or user.role not in STAFF:
        q = q.filter(SupportTicket.user_email == user.email)
    if status:
        q = q.filter(SupportTicket.status == status)
    if kind:
        q = q.filter(SupportTicket.kind == kind)
    now = datetime.utcnow()
    return [_out(t, now) for t in q.order_by(SupportTicket.created_at.desc()).limit(500).all()]


@router.post("", response_model=SupportTicketOut, status_code=201)
def create_ticket(payload: SupportTicketCreate, request: Request,
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    subject = payload.subject.strip()
    if not subject:
        raise HTTPException(status_code=400, detail="Укажите тему обращения")
    if payload.kind not in sla.KINDS:
        raise HTTPException(status_code=400, detail="Вид обращения: " + ", ".join(sla.KINDS))
    if payload.criticality not in sla.LEVELS:
        raise HTTPException(status_code=400, detail="Критичность: " + ", ".join(sla.LEVELS))
    service = payload.service if payload.kind == "service_request" else ""
    if payload.kind == "service_request" and service not in sla.SERVICES:
        raise HTTPException(status_code=400, detail="Укажите услугу, на которую подаётся заявка")

    now = datetime.utcnow()
    ticket = SupportTicket(
        user_email=user.email, subject=subject, body=payload.body,
        kind=payload.kind, service=service, criticality=payload.criticality,
        created_at=now,
    )
    if payload.kind in sla.SLA_KINDS:
        # Сроки фиксируются при регистрации: изменение рабочего времени в
        # настройках не должно задним числом сдвигать сроки поданных обращений.
        ticket.reaction_due, ticket.resolution_due = sla.deadlines(payload.criticality, now)
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    if payload.kind == "security_incident":
        _notify_security_incident(db, ticket, user, request)
    else:
        audit.record(db, user, "support.create", "support", ticket.id,
                     f"{sla.KINDS[ticket.kind]}: {ticket.subject}", request=request)
    return _out(ticket)


def _notify_security_incident(db: Session, ticket: SupportTicket, user: User,
                              request: Request) -> None:
    """ТС-176 разд. 14 п. 9: об инциденте ИБ сообщается ответственным по
    электронной почте с пометкой «инцидент ИБ»."""
    recipients = [e.strip() for e in settings.SECURITY_INCIDENT_EMAILS.split(",") if e.strip()]
    if not recipients:
        recipients = [u.email for u in db.query(User)
                      .filter(User.role == Role.admin, User.is_active.is_(True)).all()]
    body = (
        "Зарегистрирован инцидент ИБ.\n\n"
        f"Тема: {ticket.subject}\n"
        f"Сообщил: {user.email}\n"
        f"Критичность: {sla.LEVELS[ticket.criticality]['label']}\n"
        f"Срок реакции (UTC): {ticket.reaction_due:%d.%m.%Y %H:%M}\n\n"
        f"{ticket.body}"
    )
    sent = sum(1 for to in recipients
               if mailer.send(to, f"[инцидент ИБ] {ticket.subject}", body))
    audit.security(db, user, "incident.reported",
                   f"{ticket.subject}; уведомлено: {sent} из {len(recipients)}",
                   request=request, object_type="support", object_id=ticket.id)


@router.post("/{ticket_id}/take", response_model=SupportTicketOut)
def take_ticket(ticket_id: str, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.admin))):
    """Принятие в работу — время первой реакции (п. 13.1.1.1.2)."""
    ticket = _ticket(db, ticket_id, user)
    if ticket.status not in (sla.STATUS_NEW, sla.STATUS_RETURNED):
        raise HTTPException(status_code=409,
                            detail=f"Обращение в статусе «{ticket.status}» уже в работе или решено")
    ticket.status = sla.STATUS_IN_WORK
    ticket.assignee = user.email
    if ticket.reacted_at is None:
        ticket.reacted_at = datetime.utcnow()
    db.commit()
    audit.record(db, user, "support.take", "support", ticket.id, ticket.subject,
                 request=request)
    db.refresh(ticket)
    return _out(ticket)


@router.post("/{ticket_id}/answer", response_model=SupportTicketOut)
def answer_ticket(ticket_id: str, payload: SupportTicketAnswer, request: Request,
                  db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.admin))):
    ticket = _ticket(db, ticket_id, user)
    if ticket.status == sla.STATUS_CLOSED:
        raise HTTPException(status_code=409, detail="Обращение закрыто")
    now = datetime.utcnow()
    ticket.answer = payload.answer
    ticket.answered_at = now
    ticket.assignee = ticket.assignee or user.email
    if ticket.reacted_at is None:
        ticket.reacted_at = now
    if payload.resolve:
        # Время устранения заканчивается получением ответа инициатором
        # (п. 13.1.1.1.4); если ответ его не устроит, он вернёт обращение.
        ticket.status = sla.STATUS_RESOLVED
        ticket.resolved_at = now
    else:
        ticket.status = sla.STATUS_IN_WORK
    db.commit()
    audit.record(db, user, "support.answer", "support", ticket.id,
                 f"{ticket.subject} · {ticket.status}", request=request)
    db.refresh(ticket)
    return _out(ticket)


@router.post("/{ticket_id}/close", response_model=SupportTicketOut)
def close_ticket(ticket_id: str, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """Инициатор принимает решение; администратор может закрыть обращение и без
    ответа автора (например, исполненную заявку на услугу)."""
    ticket = _ticket(db, ticket_id, user)
    if user.role != Role.admin and ticket.user_email != user.email:
        raise HTTPException(status_code=404, detail="Обращение не найдено")
    if user.role != Role.admin and ticket.status != sla.STATUS_RESOLVED:
        raise HTTPException(status_code=409, detail="Принять можно только решённое обращение")
    now = datetime.utcnow()
    ticket.status = sla.STATUS_CLOSED
    ticket.closed_at = now
    if ticket.resolved_at is None:
        ticket.resolved_at = now
    db.commit()
    audit.record(db, user, "support.close", "support", ticket.id, ticket.subject,
                 request=request)
    db.refresh(ticket)
    return _out(ticket)


@router.post("/{ticket_id}/reopen", response_model=SupportTicketOut)
def reopen_ticket(ticket_id: str, payload: SupportTicketReopen, request: Request,
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """Ответ не устроил инициатора — повторное исполнение (п. 13.1.1.1.4).
    Срок устранения не продлевается: время считается до окончательного ответа."""
    ticket = _ticket(db, ticket_id, user)
    if ticket.user_email != user.email:
        raise HTTPException(status_code=404, detail="Обращение не найдено")
    if ticket.status != sla.STATUS_RESOLVED:
        raise HTTPException(status_code=409, detail="Вернуть можно только решённое обращение")
    now = datetime.utcnow()
    ticket.status = sla.STATUS_RETURNED
    ticket.resolved_at = None
    ticket.reopen_count = (ticket.reopen_count or 0) + 1
    if payload.reason.strip():
        ticket.body = (f"{ticket.body}\n\n— Возвращено на доработку "
                       f"{now:%d.%m.%Y %H:%M} UTC: {payload.reason.strip()}")
    db.commit()
    audit.record(db, user, "support.reopen", "support", ticket.id,
                 f"{ticket.subject}: {payload.reason}", request=request)
    db.refresh(ticket)
    return _out(ticket)


@router.get("/sla")
def sla_report(date_from: date, date_to: date, amount: float = 0.0,
               db: Session = Depends(get_db),
               _: User = Depends(require_roles(*STAFF))) -> dict:
    """Уровень выполнения SLA за отчётный период и размер оплаты услуг
    (ТС-176 п. 13.1.2–13.1.3). Даты периода — по местному времени."""
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="Начало периода позже его конца")
    offset = timedelta(hours=settings.SLA_UTC_OFFSET_HOURS)
    start = datetime.combine(date_from, time.min) - offset
    end = datetime.combine(date_to + timedelta(days=1), time.min) - offset
    now = datetime.utcnow()

    tickets = (db.query(SupportTicket)
               .filter(SupportTicket.kind.in_(sla.SLA_KINDS),
                       SupportTicket.resolution_due.isnot(None),
                       SupportTicket.created_at >= start,
                       SupportTicket.created_at < end)
               .order_by(SupportTicket.created_at).all())
    results = [sla.resolved_on_time(t.resolution_due, t.resolved_at, now) for t in tickets]
    on_time = sla.on_time_percent(results)

    by_level = []
    for key, level in sla.LEVELS.items():
        level_results = [r for t, r in zip(tickets, results) if t.criticality == key]
        by_level.append({
            "key": key, "label": level["label"], "total": len(level_results),
            "on_time": sum(1 for r in level_results if r is True),
            "late": sum(1 for r in level_results if r is False),
            "pending": sum(1 for r in level_results if r is None),
        })

    avail = availability.summary(db, start, end)
    avail_percent = sla.availability_percent(avail["available_minutes"], avail["total_minutes"])
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "availability": {**avail, "percent": avail_percent, "target": sla.AVAILABILITY_TARGET},
        "on_time": {
            "percent": on_time, "target": sla.ON_TIME_TARGET,
            "counted": sum(1 for r in results if r is not None),
            "resolved_on_time": sum(1 for r in results if r is True),
            "pending": sum(1 for r in results if r is None),
        },
        "by_level": by_level,
        "payment": sla.payment(amount, avail_percent, on_time) if amount > 0 else None,
        "late": [
            {"id": t.id, "subject": t.subject, "criticality": t.criticality,
             "resolution_due": t.resolution_due.isoformat(),
             "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None}
            for t, r in zip(tickets, results) if r is False
        ][:200],
    }
