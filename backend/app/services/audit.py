"""Аудиторский след (ТС-176, раздел 14).

Каждая запись содержит требуемые ТЗ поля: логин пользователя, дату и время,
IP/рабочую станцию, объект, тип действия и результат. Записи не удаляются
никогда — по истечении оперативного срока они лишь помечаются `archived`.

Параллельно каждое событие пишется в лог одной JSON-строкой (канал `siem`) —
это готовый поток для внешней SIEM: docker logs / filebeat / syslog собирают
его без дополнительной интеграции (п. 2.6 и 5.2 раздела 14).
"""
import json
import logging

from sqlalchemy.orm import Session

from ..config import settings
from ..models import AuditLog, AuditActionType, User

log = logging.getLogger("audit")
siem = logging.getLogger("siem")

MAX_DETAIL = 2000
MAX_UA = 500


def client_meta(request) -> tuple[str, str]:
    """IP и user-agent из запроса.

    X-Forwarded-For берётся только при TRUST_PROXY_HEADERS: это обычный
    заголовок запроса, и клиент волен прислать любой. Без прокси перед backend
    (как в поставляемом docker compose) доверие к нему означало бы, что адрес
    в аудиторском следе — включая записи о неудачных входах — подделывается
    одной строкой в curl, то есть обязательное поле ТС-176 ничего не доказывает.
    """
    if request is None:
        return "", ""
    ip = ""
    if settings.TRUST_PROXY_HEADERS:
        ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    ip = ip or (request.client.host if request.client else "")
    return ip[:64], (request.headers.get("user-agent") or "")[:MAX_UA]


def record(
    db: Session,
    user: User | None,
    action: str,
    object_type: str = "",
    object_id: str = "",
    detail: str = "",
    *,
    request=None,
    action_type: AuditActionType | str = AuditActionType.update,
    result: bool = True,
    user_email: str | None = None,
) -> None:
    """Пишет запись аудита. Никогда не роняет основную операцию.

    `user_email` позволяет зафиксировать неудачный вход, когда объекта User ещё
    нет (неверный пароль, несуществующий логин) — иначе такие события, прямо
    требуемые ТЗ, были бы потеряны.
    """
    at = action_type.value if isinstance(action_type, AuditActionType) else str(action_type)
    ip, ua = client_meta(request)
    email = user_email or (user.email if user else "system")
    try:
        db.add(AuditLog(
            user_email=email,
            action=action,
            object_type=object_type,
            object_id=str(object_id or ""),
            detail=detail[:MAX_DETAIL],
            ip_address=ip,
            user_agent=ua,
            action_type=at,
            result=result,
        ))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.warning("audit record failed: %s %s", action, object_id)
    # Поток для SIEM пишем даже если запись в БД не удалась — событие ИБ не
    # должно исчезнуть из-за проблем с базой.
    try:
        siem.info(json.dumps({
            "user": email, "action": action, "action_type": at,
            "object_type": object_type, "object_id": str(object_id or ""),
            "ip": ip, "user_agent": ua, "result": "success" if result else "failure",
            "detail": detail[:MAX_DETAIL],
        }, ensure_ascii=False))
    except Exception:  # noqa: BLE001
        pass


def security(db: Session, user: User | None, action: str, detail: str = "",
             *, request=None, result: bool = True, user_email: str | None = None,
             object_type: str = "security", object_id: str = "") -> None:
    """События безопасности: вход/выход, блокировки, смена ролей и полномочий,
    изменение настроек (перечень событий — разд. 14, п. 1 требований к аудиту)."""
    record(db, user, action, object_type, object_id, detail, request=request,
           action_type=AuditActionType.security, result=result, user_email=user_email)
