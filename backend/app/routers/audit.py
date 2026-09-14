"""Аудиторский след: просмотр, выгрузка и перенос в архив (ТС-176, разд. 14).

Удаления записей нет и не может быть: по требованию ТЗ администратору доступен
только перенос журнала в архив. Соответствующего эндпоинта DELETE здесь
намеренно не существует, а в СУБД удаление и правку записей блокирует триггер
(см. migrate.py).

Просмотр и выгрузка доступны также аудитору ИБ (разд. 14 п. 5.1): он работает
с журналами, не имея доступа к содержимому документов. Перенос в архив —
только администратору.
"""
import io
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import AuditLog, User, Role
from ..schemas import AuditOut
from ..security import require_roles
from ..services import audit as audit_svc

router = APIRouter(prefix="/api/audit", tags=["audit"])

READERS = (Role.admin, Role.auditor)


def _filtered(db: Session, user_email: str | None, action_type: str | None,
              result: bool | None, archived: bool | None, days: int | None):
    q = db.query(AuditLog)
    if user_email:
        q = q.filter(AuditLog.user_email.ilike(f"%{user_email}%"))
    if action_type:
        q = q.filter(AuditLog.action_type == action_type)
    if result is not None:
        q = q.filter(AuditLog.result == result)
    if archived is not None:
        q = q.filter(AuditLog.archived == archived)
    if days:
        q = q.filter(AuditLog.ts >= datetime.utcnow() - timedelta(days=days))
    return q.order_by(AuditLog.ts.desc())


@router.get("", response_model=list[AuditOut])
def list_audit(
    user_email: str | None = None,
    action_type: str | None = None,
    result: bool | None = None,
    archived: bool | None = None,
    days: int | None = None,
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(*READERS)),
):
    return _filtered(db, user_email, action_type, result, archived, days) \
        .offset(offset).limit(limit).all()


@router.get("/stats")
def audit_stats(db: Session = Depends(get_db),
                _: User = Depends(require_roles(*READERS))) -> dict:
    total = db.query(AuditLog).count()
    archived = db.query(AuditLog).filter(AuditLog.archived.is_(True)).count()
    failures = db.query(AuditLog).filter(AuditLog.result.is_(False)).count()
    cutoff = datetime.utcnow() - timedelta(days=settings.AUDIT_OPERATIONAL_DAYS)
    to_archive = (
        db.query(AuditLog)
        .filter(AuditLog.archived.is_(False), AuditLog.ts < cutoff)
        .count()
    )
    return {
        "total": total,
        "operational": total - archived,
        "archived": archived,
        "failures": failures,
        "pending_archive": to_archive,
        "operational_days": settings.AUDIT_OPERATIONAL_DAYS,
        "archive_days": settings.AUDIT_ARCHIVE_DAYS,
    }


@router.get("/export")
def export_audit(
    user_email: str | None = None,
    action_type: str | None = None,
    result: bool | None = None,
    days: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*READERS)),
    request: Request = None,
):
    """Выгрузка журнала (п. 6.1 разд. 14: предоставление информации о
    логировании по официальному запросу; формат — JSON Lines для SIEM)."""
    rows = _filtered(db, user_email, action_type, result, None, days).limit(50000).all()
    buf = io.StringIO()
    for r in rows:
        buf.write(json.dumps({
            "ts": r.ts.isoformat(), "user": r.user_email, "action": r.action,
            "action_type": r.action_type, "object_type": r.object_type,
            "object_id": r.object_id, "ip": r.ip_address, "user_agent": r.user_agent,
            "result": "success" if r.result else "failure", "detail": r.detail,
        }, ensure_ascii=False) + "\n")
    audit_svc.record(db, user, "audit.export", "audit", "",
                     f"выгружено записей: {len(rows)}", request=request)
    data = buf.getvalue().encode("utf-8")
    return StreamingResponse(
        io.BytesIO(data), media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="audit_trail.ndjson"'},
    )


@router.post("/archive")
def archive_old(db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.admin)),
                request: Request = None) -> dict:
    """Переносит записи старше срока оперативного доступа в архивный.
    Это единственная операция администратора над журналом — удаление запрещено
    (п. 3 требований к аудиторскому следу)."""
    cutoff = datetime.utcnow() - timedelta(days=settings.AUDIT_OPERATIONAL_DAYS)
    moved = (
        db.query(AuditLog)
        .filter(AuditLog.archived.is_(False), AuditLog.ts < cutoff)
        .update({AuditLog.archived: True}, synchronize_session=False)
    )
    db.commit()
    audit_svc.security(db, user, "audit.archive",
                       f"перенесено в архив записей: {moved}", request=request)
    return {"archived": moved, "cutoff": cutoff.isoformat()}
