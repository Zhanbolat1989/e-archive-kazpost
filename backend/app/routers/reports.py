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
    Case, Document, DocStatus, IssueRecord, IssueStatus, DestructionAct,
    DestructionActItem, User,
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


_REPORTS = {
    "cases": _cases_report,
    "documents": _documents_report,
    "issues": _issues_report,
    "destruction": _destruction_report,
}


@router.get("")
def list_reports(_: User = Depends(get_current_user)) -> list[dict]:
    return [
        {"key": "cases", "title": "Сводный отчет по делам"},
        {"key": "documents", "title": "Сводный отчет по документам"},
        {"key": "issues", "title": "Сводный отчет по запросам"},
        {"key": "destruction", "title": "Сводный отчет по актам на уничтожение"},
    ]


@router.get("/{key}")
def get_report(key: str, db: Session = Depends(get_db),
               _: User = Depends(get_current_user)) -> dict:
    builder = _REPORTS.get(key)
    if builder is None:
        raise HTTPException(status_code=404, detail="Отчёт не найден")
    return builder(db)


@router.get("/{key}/csv")
def export_report_csv(key: str, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    builder = _REPORTS.get(key)
    if builder is None:
        raise HTTPException(status_code=404, detail="Отчёт не найден")
    data = builder(db)
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
