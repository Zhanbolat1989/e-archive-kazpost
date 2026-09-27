"""История изменений записей («Администрирование»: «просмотр
истории изменений записей»).

Отличается от аудиторского следа: аудит отвечает на вопрос «кто и что делал»,
история — «что именно стало другим»: поле, прежнее значение, новое. Поэтому
записи ведутся по полям, а не по операциям.
"""
import logging

from sqlalchemy.orm import Session

from ..models import ChangeHistory, User

log = logging.getLogger("history")

MAX_VALUE = 2000


def _fmt(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "value"):            # Enum карточки (тип документа, статус)
        value = value.value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)[:MAX_VALUE]


def record(db: Session, user: User | None, object_type: str, object_id: str,
           before: dict, after: dict) -> int:
    """Записывает отличия before → after по полям, встречающимся в after.

    Ошибка журналирования не должна ронять саму правку карточки: история —
    сопровождающая запись, а не часть бизнес-операции.
    """
    email = user.email if user is not None else "system"
    written = 0
    try:
        for field, new in after.items():
            old = before.get(field)
            if _fmt(old) == _fmt(new):
                continue
            db.add(ChangeHistory(
                user_email=email, object_type=object_type, object_id=str(object_id),
                field=field, old_value=_fmt(old), new_value=_fmt(new),
            ))
            written += 1
        if written:
            db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.warning("Не записана история изменений %s %s", object_type, object_id)
        return 0
    return written


def snapshot(obj, fields: list[str]) -> dict:
    """Значения полей объекта до правки — сравнивать нужно именно с ними."""
    return {f: getattr(obj, f, None) for f in fields}
