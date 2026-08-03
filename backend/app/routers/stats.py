from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User, Document, DocStatus, DocType, Case, CaseStatus

router = APIRouter(prefix="/api/stats", tags=["stats"])

# Local import to avoid a cycle at module load; get_current_user is light.
from ..security import get_current_user  # noqa: E402


def _status(contracted: float, paid: float) -> str:
    if contracted > 0 and paid >= contracted:
        return "closed"
    if paid <= 0:
        return "unpaid"
    return "partial"


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> dict:
    # Уничтоженные по акту документы выбыли из архива — в сводках не участвуют
    # (согласовано с книгой учёта поступления/выбытия).
    docs = (db.query(Document)
            .filter(Document.status == DocStatus.ready,
                    Document.destroyed_at.is_(None)).all())

    by_type: dict[str, dict] = {}
    contracted: dict[str, float] = defaultdict(float)
    paid: dict[str, float] = defaultdict(float)
    cps: set[str] = set()
    by_year: dict[int, dict] = defaultdict(lambda: {"sum": 0.0, "count": 0})
    dates = []

    for d in docs:
        g = by_type.setdefault(d.doc_type.value, {"type": d.doc_type.value, "count": 0, "sum": 0.0})
        g["count"] += 1
        amt = float(d.amount) if d.amount is not None else None
        if amt is not None:
            g["sum"] += amt
        if d.doc_date:
            dates.append(d.doc_date)
        if d.counterparty:
            cps.add(d.counterparty)
            if amt is not None:
                if d.doc_type == DocType.contract:
                    contracted[d.counterparty] += amt
                elif d.doc_type == DocType.payment:
                    paid[d.counterparty] += amt
        if d.doc_type == DocType.payment and d.doc_date and amt is not None:
            y = d.doc_date.year
            by_year[y]["sum"] += amt
            by_year[y]["count"] += 1

    counterparties = []
    for c in cps:
        ob, pd = contracted.get(c, 0.0), paid.get(c, 0.0)
        if ob == 0 and pd == 0:
            continue
        counterparties.append({
            "name": c, "contracted": round(ob, 2), "paid": round(pd, 2),
            "remaining": round(max(ob - pd, 0.0), 2), "status": _status(ob, pd),
        })
    counterparties.sort(key=lambda x: x["contracted"], reverse=True)

    total_obligations = round(sum(contracted.values()), 2)
    total_paid = round(sum(paid.values()), 2)

    # Сроки хранения: истёкшие и истекающие в ближайшие 12 месяцев
    today = date.today()
    horizon = today + timedelta(days=365)
    expired, expiring = [], []
    for d in docs:
        if d.permanent or d.retention_until is None or d.destroyed_at is not None:
            continue
        row = {
            "id": d.id, "title": d.title, "doc_type": d.doc_type.value,
            "retention_label": d.retention_label,
            "retention_until": d.retention_until.isoformat(),
        }
        if d.retention_until < today:
            expired.append(row)
        elif d.retention_until <= horizon:
            expiring.append(row)
    expired.sort(key=lambda x: x["retention_until"])
    expiring.sort(key=lambda x: x["retention_until"])

    cases_total = db.query(Case).count()
    cases_forming = db.query(Case).filter(Case.status == CaseStatus.forming).count()

    return {
        "cases": {"total": cases_total, "forming": cases_forming},
        "retention": {
            "expired_count": len(expired),
            "expiring_count": len(expiring),
            "expired": expired[:10],
            "expiring": expiring[:10],
        },
        "total_documents": len(docs),
        "period": ({"from": min(dates).year, "to": max(dates).year} if dates else None),
        "total_obligations": total_obligations,
        "total_paid": total_paid,
        "total_remaining": round(max(total_obligations - total_paid, 0.0), 2),
        "by_type": sorted(by_type.values(), key=lambda x: x["count"], reverse=True),
        "counterparties": counterparties,
        "payments_by_year": [
            {"year": y, "sum": round(v["sum"], 2), "count": v["count"]}
            for y, v in sorted(by_year.items())
        ],
    }
