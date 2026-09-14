"""Установка обновлений и изменение параметров системы в аудиторском следе.

ТС-176 разд. 14 п. 6 требует фиксировать «события, отражающие установку
обновлений и (или) изменений в Системе», «изменения параметров аудита» и
«изменения системных параметров». Параметры задаются окружением, а не через
интерфейс, поэтому изменение видно только при перезапуске: на старте текущее
состояние сверяется с последним зафиксированным в журнале.

Секреты в снимок не попадают по построению — в нём только перечисленные ниже
параметры.
"""
import json
import logging

from ..config import settings
from ..db import SessionLocal
from ..models import AuditLog
from . import audit

log = logging.getLogger("system_state")

STATE_ACTION = "system.state"

AUDIT_PARAMS = ("AUDIT_OPERATIONAL_DAYS", "AUDIT_ARCHIVE_DAYS", "TRUST_PROXY_HEADERS")
SECURITY_PARAMS = (
    "ENVIRONMENT", "LOGIN_MAX_ATTEMPTS", "TWOFA_ENABLED", "TWOFA_CODE_TTL_MINUTES",
    "TWOFA_MAX_ATTEMPTS", "ACCESS_TOKEN_EXPIRE_MINUTES", "CORS_ORIGINS",
)
SYSTEM_PARAMS = (
    "EDITION", "EDITION_DISABLED_MODULES", "MINIO_RETENTION_DAYS", "OCR_ENGINE",
    "OCR_LANGUAGES", "OLLAMA_MODEL", "EMBEDDING_MODEL", "RERANK_ENABLED", "PDFA_FOR_ALL",
)

# Раздел снимка → событие аудита при его изменении
SECTIONS = {
    "version": "system.update",
    "audit": "audit.settings",
    "security": "security.settings",
    "system": "system.settings",
}


def snapshot() -> dict:
    return {
        "version": settings.APP_VERSION,
        "audit": {k: getattr(settings, k) for k in AUDIT_PARAMS},
        "security": {k: getattr(settings, k) for k in SECURITY_PARAMS},
        "system": {k: getattr(settings, k) for k in SYSTEM_PARAMS},
    }


def changes(previous: dict | None, current: dict) -> list[tuple[str, str]]:
    """(событие, описание) по разделам, отличающимся от прошлого снимка.

    Без прошлого снимка изменений нет: первый старт — точка отсчёта, а не
    «изменение всех параметров сразу»."""
    if not previous:
        return []
    found = []
    for section, action in SECTIONS.items():
        old, new = previous.get(section), current.get(section)
        if old == new:
            continue
        if isinstance(new, dict):
            old = old if isinstance(old, dict) else {}
            diff = [f"{k}: {old.get(k)!r} → {v!r}" for k, v in new.items() if old.get(k) != v]
            found.append((action, "; ".join(diff)))
        else:
            found.append((action, f"{old} → {new}"))
    return found


def record_startup() -> None:
    """Сверяет состояние с последним снимком и пишет события изменений.
    Сбой не должен мешать запуску: журнал — сопровождающая запись."""
    db = SessionLocal()
    try:
        current = snapshot()
        last = (db.query(AuditLog)
                .filter(AuditLog.action == STATE_ACTION)
                .order_by(AuditLog.ts.desc()).first())
        previous = None
        if last is not None:
            try:
                previous = json.loads(last.detail)
            except ValueError:
                previous = None
        found = changes(previous, current)
        for action, detail in found:
            audit.security(db, None, action, detail, user_email="system")
        if previous is None or found:
            audit.security(db, None, STATE_ACTION,
                           json.dumps(current, ensure_ascii=False, default=str),
                           user_email="system")
    except Exception:  # noqa: BLE001
        log.exception("Состояние системы не зафиксировано в аудиторском следе")
    finally:
        db.close()
