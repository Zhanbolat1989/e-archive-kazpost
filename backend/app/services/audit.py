"""Журнал аудита: кто, когда, что сделал (требование «цифрового архива»)."""
import logging

from sqlalchemy.orm import Session

from ..models import AuditLog, User

log = logging.getLogger("audit")


def record(db: Session, user: User | None, action: str,
           object_type: str = "", object_id: str = "", detail: str = "") -> None:
    """Пишет запись аудита. Никогда не роняет основную операцию."""
    try:
        db.add(AuditLog(
            user_email=(user.email if user else "system"),
            action=action,
            object_type=object_type,
            object_id=str(object_id or ""),
            detail=detail[:2000],
        ))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.warning("audit record failed: %s %s", action, object_id)
