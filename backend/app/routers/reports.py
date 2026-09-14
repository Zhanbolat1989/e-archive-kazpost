"""Модуль «Управление отчетами» (п. 4.4 ТС-176).

Минимальный состав по ТЗ: сводные отчёты по делам, по документам, по запросам
на выдачу и по актам на уничтожение. Каждый отчёт доступен как JSON (для
интерфейса) и как CSV-выгрузка (для передачи заказчику в электронном виде).
"""
import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    ArchiveRequest, ArchiveRequestItem, AuditActionType, AuditLog, Case, Document,
    DocStatus, IssueRecord, IssueStatus, DestructionAct, DestructionActItem, Role, User,
)
from ..security import get_current_user
from ..services import audit

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _alive(db: Session):
    """Уничтоженные по акту документы в сводных отчётах не учитываются."""
    return db.query(Document).filter(Document.destroyed_at.is_(None))


# ------------------------------------------------------------------ сводные отчёты
def _cases_report(db: Session) -> dict:
    rows = []
    # Число документов по всем делам — одним запросом: отдельный COUNT на дело
    # давал бы по запросу на строку отчёта.
    doc_counts = dict(
        db.query(Document.case_id, func.count(Document.id))
        .filter(Document.case_id.isnot(None), Document.destroyed_at.is_(None))
        .group_by(Document.case_id)
        .all()
    )
    for c in db.query(Case).order_by(Case.year.desc(), Case.index).all():
        docs = doc_counts.get(c.id, 0)
        rows.append({
            "index": c.index, "title": c.title, "year": c.year,
            "status": c.status.value, "documents": docs,
            "retention": "Постоянно" if c.permanent else (c.retention_label or "—"),
            "retention_until": c.retention_until.isoformat() if c.retention_until else "",
            "date_from": c.date_from.isoformat() if c.date_from else "",
            "date_to": c.date_to.isoformat() if c.date_to else "",
        })
    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    return {
        "title": "Сводный отчет по делам",
        "generated_at": datetime.utcnow().isoformat(),
        "total": len(rows),
        "summary": by_status,
        "rows": rows,
    }


def _documents_report(db: Session) -> dict:
    rows = []
    for d in _alive(db).order_by(Document.created_at.desc()).limit(5000).all():
        rows.append({
            "title": d.title, "doc_type": d.doc_type.value if d.doc_type else "",
            "doc_number": d.doc_number, "counterparty": d.counterparty,
            "doc_date": d.doc_date.isoformat() if d.doc_date else "",
            "status": d.status.value,
            "signature": d.signature_status.value if d.signature_status else "",
            "retention": "Постоянно" if d.permanent else (d.retention_label or "—"),
            "case_id": d.case_id or "",
            "created_at": d.created_at.isoformat(),
        })
    by_type = dict(
        db.query(Document.doc_type, func.count(Document.id))
        .filter(Document.destroyed_at.is_(None))
        .group_by(Document.doc_type).all()
    )
    return {
        "title": "Сводный отчет по документам",
        "generated_at": datetime.utcnow().isoformat(),
        "total": _alive(db).count(),
        "summary": {(k.value if k else "—"): v for k, v in by_type.items()},
        "ready": _alive(db).filter(Document.status == DocStatus.ready).count(),
        "rows": rows,
    }


def _issues_report(db: Session) -> dict:
    rows = []
    today = datetime.utcnow().date()
    issues = db.query(IssueRecord).order_by(IssueRecord.order_date.desc()).all()
    # Дела подтягиваем одним запросом, а не по одному на строку.
    case_ids = {i.case_id for i in issues if i.case_id}
    cases = {
        c.id: c for c in
        (db.query(Case).filter(Case.id.in_(case_ids)).all() if case_ids else [])
    }
    for i in issues:
        case = cases.get(i.case_id)
        overdue = bool(
            i.status == IssueStatus.issued and i.due_date and i.due_date < today
        )
        rows.append({
            "case_index": case.index if case else "",
            "case_title": case.title if case else "",
            "requested_by": i.requested_by,
            "purpose": i.purpose,
            "status": i.status.value,
            "order_date": i.order_date.isoformat() if i.order_date else "",
            "issue_date": i.issue_date.isoformat() if i.issue_date else "",
            "due_date": i.due_date.isoformat() if i.due_date else "",
            "returned_at": i.returned_at.isoformat() if i.returned_at else "",
            "overdue": overdue,
        })
    return {
        "title": "Сводный отчет по запросам",
        "generated_at": datetime.utcnow().isoformat(),
        "total": len(rows),
        "summary": {
            "на руках": sum(1 for r in rows if r["status"] == IssueStatus.issued.value),
            "просрочено": sum(1 for r in rows if r["overdue"]),
            "возвращено": sum(1 for r in rows if r["status"] == IssueStatus.returned.value),
        },
        "rows": rows,
    }


def _destruction_report(db: Session) -> dict:
    rows = []
    # Позиции всех актов — одним группирующим запросом вместо COUNT на акт.
    item_counts = dict(
        db.query(DestructionActItem.act_id, func.count(DestructionActItem.id))
        .group_by(DestructionActItem.act_id)
        .all()
    )
    for a in db.query(DestructionAct).order_by(DestructionAct.act_date.desc()).all():
        items = item_counts.get(a.id, 0)
        rows.append({
            "number": a.number,
            "act_date": a.act_date.isoformat() if a.act_date else "",
            "status": a.status.value,
            "kind": "электронные (прил. 15)" if a.is_electronic else "бумажные (прил. 14)",
            "documents": items,
            "created_by": a.created_by,
            "approved_by": a.approved_by,
            "approved_at": a.approved_at.isoformat() if a.approved_at else "",
        })
    return {
        "title": "Сводный отчет по актам на уничтожение",
        "generated_at": datetime.utcnow().isoformat(),
        "total": len(rows),
        "summary": {
            "утверждено": sum(1 for r in rows if r["status"] == "Утверждён"),
            "проектов": sum(1 for r in rows if r["status"] != "Утверждён"),
            "документов в актах": sum(r["documents"] for r in rows),
        },
        "rows": rows,
    }


def _views_report(db: Session) -> dict:
    """Отчёт по просмотрам и обращениям к документам (ТЗ АГП п. 8).

    Источник — аудиторский след: он и так фиксирует каждое открытие карточки,
    и отдельный счётчик просмотров расходился бы с ним при любом сбое.
    """
    rows_q = (
        db.query(AuditLog.object_id, func.count(AuditLog.id),
                 func.max(AuditLog.ts), func.count(func.distinct(AuditLog.user_email)))
        .filter(AuditLog.object_type == "document",
                AuditLog.action_type == AuditActionType.read.value)
        .group_by(AuditLog.object_id)
        .order_by(func.count(AuditLog.id).desc())
        .limit(500)
        .all()
    )
    ids = [r[0] for r in rows_q]
    docs = {d.id: d for d in (db.query(Document)
                              .filter(Document.id.in_(ids)).all() if ids else [])}
    rows = []
    for doc_id, views, last_ts, readers in rows_q:
        doc = docs.get(doc_id)
        rows.append({
            "document_id": doc_id,
            "title": doc.title if doc else "(документ снят с учёта)",
            "doc_type": doc.doc_type.value if doc and doc.doc_type else "",
            "views": int(views),
            "readers": int(readers),
            "last_view": last_ts.isoformat() if last_ts else "",
        })
    # Обращения к документам через архивные запросы — второй канал
    # использования: документ может ни разу не открываться в интерфейсе, но
    # выдаваться по запросам.
    request_uses = dict(
        db.query(ArchiveRequestItem.document_id, func.count(ArchiveRequestItem.id))
        .filter(ArchiveRequestItem.document_id.isnot(None))
        .group_by(ArchiveRequestItem.document_id).all()
    )
    for r in rows:
        r["archive_requests"] = int(request_uses.get(r["document_id"], 0))
    return {
        "title": "Отчет по просмотрам и обращениям к документам",
        "generated_at": datetime.utcnow().isoformat(),
        "total": len(rows),
        "summary": {
            "всего просмотров": sum(r["views"] for r in rows),
            "документов просмотрено": len(rows),
            "обращений по запросам": sum(request_uses.values()),
        },
        "rows": rows,
    }


def _archive_requests_report(db: Session) -> dict:
    """Отчёт по архивным запросам: исполнение и соблюдение сроков (п. 8)."""
    today = datetime.utcnow().date()
    counts = dict(
        db.query(ArchiveRequestItem.request_id, func.count(ArchiveRequestItem.id))
        .group_by(ArchiveRequestItem.request_id).all()
    )
    rows = []
    for r in (db.query(ArchiveRequest)
              .order_by(ArchiveRequest.reg_date.desc()).all()):
        closed = r.status in ("Исполнен", "Отказано")
        overdue = bool(r.due_date and not closed and r.due_date < today)
        late = bool(r.due_date and r.completed_at and r.completed_at > r.due_date)
        rows.append({
            "number": r.number,
            "reg_date": r.reg_date.isoformat() if r.reg_date else "",
            "applicant": r.applicant,
            "request_type": r.request_type,
            "subject": r.subject,
            "status": r.status,
            "executor": r.executor_email,
            "due_date": r.due_date.isoformat() if r.due_date else "",
            "completed_at": r.completed_at.isoformat() if r.completed_at else "",
            "documents": int(counts.get(r.id, 0)),
            "overdue": overdue,
            "completed_late": late,
        })
    return {
        "title": "Сводный отчет по архивным запросам",
        "generated_at": datetime.utcnow().isoformat(),
        "total": len(rows),
        "summary": {
            "в работе": sum(1 for r in rows
                            if r["status"] not in ("Исполнен", "Отказано")),
            "исполнено": sum(1 for r in rows if r["status"] == "Исполнен"),
            "просрочено": sum(1 for r in rows if r["overdue"]),
            "исполнено с нарушением срока": sum(1 for r in rows if r["completed_late"]),
        },
        "rows": rows,
    }


# Попытки несанкционированного доступа (события с отказом) и принятые меры —
# по аудиторскому следу (ТС-176 разд. 14 п. 8).
_PD_ATTEMPTS = {
    "auth.login": "Неуспешный вход",
    "auth.2fa": "Неверный код второго фактора",
    "access.denied": "Обращение к закрытой категории документов",
}
_PD_MEASURES = {
    "user.unlock": "Разблокирование учётной записи после проверки",
    "session.revoke": "Принудительное завершение сессии",
    "user.update": "Отключение учётной записи",
}
_QUARTERS = ("I", "II", "III", "IV")


def _pd_category(r: AuditLog) -> tuple[str, str] | None:
    """(вид события, категория) либо None, если событие к НСД не относится."""
    if r.action in _PD_ATTEMPTS:
        return ("попытка", _PD_ATTEMPTS[r.action]) if not r.result else None
    if r.action == "user.update":
        # Правка учётной записи — мера, только если запись отключена.
        return ("мера", _PD_MEASURES[r.action]) if "is_active=False" in (r.detail or "") else None
    if r.action in _PD_MEASURES and r.result:
        return "мера", _PD_MEASURES[r.action]
    return None


def _quarter(ts: datetime) -> str:
    return f"{_QUARTERS[(ts.month - 1) // 3]} кв. {ts.year}"


def _pd_protection_report(db: Session) -> dict:
    """Информация о попытках несанкционированного доступа к персональным данным
    и принятых мерах — заказчику ежеквартально (ТС-176 разд. 14 п. 8).
    Источник — аудиторский след за текущий год с разбивкой по кварталам."""
    now = datetime.utcnow()
    events = (db.query(AuditLog)
              .filter(AuditLog.ts >= datetime(now.year, 1, 1),
                      AuditLog.action.in_(sorted({*_PD_ATTEMPTS, *_PD_MEASURES})))
              .order_by(AuditLog.ts.desc()).limit(20000).all())
    rows = []
    counts: dict[str, dict[str, int]] = {}
    for r in events:
        found = _pd_category(r)
        if found is None:
            continue
        kind, category = found
        quarter = _quarter(r.ts)
        counts.setdefault(quarter, {"попытка": 0, "мера": 0})[kind] += 1
        rows.append({
            "ts": r.ts.isoformat(), "quarter": quarter, "kind": kind,
            "category": category, "user": r.user_email, "ip": r.ip_address,
            "detail": r.detail,
        })
    summary: dict[str, int] = {}
    for q in range((now.month - 1) // 3 + 1):
        label = f"{_QUARTERS[q]} кв. {now.year}"
        summary[f"попыток НСД — {label}"] = counts.get(label, {}).get("попытка", 0)
        summary[f"принятых мер — {label}"] = counts.get(label, {}).get("мера", 0)
    return {
        "title": "Попытки несанкционированного доступа к персональным данным и принятые меры",
        "generated_at": now.isoformat(),
        "total": len(rows),
        "summary": summary,
        "rows": rows,
    }


_REPORTS = {
    "cases": _cases_report,
    "documents": _documents_report,
    "issues": _issues_report,
    "destruction": _destruction_report,
    "views": _views_report,
    "archive_requests": _archive_requests_report,
    "pd_protection": _pd_protection_report,
}

# Отчёты с данными журнала безопасности (логины, IP) — только администратору
# и аудитору ИБ. Остальным такой отчёт «не существует».
_RESTRICTED = {"pd_protection": (Role.admin, Role.auditor)}


def _report_builder(key: str, user: User):
    builder = _REPORTS.get(key)
    roles = _RESTRICTED.get(key)
    if builder is None or (roles and user.role not in roles):
        raise HTTPException(status_code=404, detail="Отчёт не найден")
    return builder


@router.get("")
def list_reports(user: User = Depends(get_current_user)) -> list[dict]:
    reports = [
        {"key": "cases", "title": "Сводный отчет по делам"},
        {"key": "documents", "title": "Сводный отчет по документам"},
        {"key": "issues", "title": "Сводный отчет по запросам"},
        {"key": "destruction", "title": "Сводный отчет по актам на уничтожение"},
        {"key": "views", "title": "Отчет по просмотрам и обращениям к документам"},
        {"key": "archive_requests", "title": "Сводный отчет по архивным запросам"},
        {"key": "pd_protection",
         "title": "Попытки несанкционированного доступа к персональным данным (ежеквартально)"},
    ]
    return [r for r in reports
            if user.role in _RESTRICTED.get(r["key"], (user.role,))]


@router.get("/{key}")
def get_report(key: str, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> dict:
    return _report_builder(key, user)(db)


@router.get("/{key}/csv")
def export_report_csv(key: str, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    data = _report_builder(key, user)(db)
    rows = data["rows"]
    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    else:
        buf.write("нет данных\n")
    audit.record(db, user, "report.export", "report", key, data["title"],
                 request=request)
    # BOM — чтобы Excel открыл кириллицу в CSV без дополнительных настроек.
    payload = ("﻿" + buf.getvalue()).encode("utf-8")
    return StreamingResponse(
        io.BytesIO(payload), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="report_{key}.csv"'},
    )
