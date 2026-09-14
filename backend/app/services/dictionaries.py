"""Редактируемые справочники (ТС-176 п. 4.9, модуль «Администрирование»).

Перечни, которые заказчик ведёт сам, без выпуска новой версии системы.
Значения не удаляются, а выводятся из употребления: записи, заведённые с
прежним значением, должны оставаться понятными.

Виды документов, статусы и роли справочниками не являются: на них завязаны
правила системы — доступ по категориям, сроки хранения, жизненный цикл.
"""
from sqlalchemy.orm import Session

from ..models import DictionaryEntry

# strict — значение вне справочника отклоняется; иначе справочник только
# подсказывает при вводе.
KINDS: dict[str, dict] = {
    "request_types": {
        "label": "Виды архивных запросов",
        "hint": "Выбираются при регистрации запроса; другие значения не принимаются",
        "strict": True,
        "defaults": ("Тематический", "Социально-правовой", "Биографический", "Имущественный"),
    },
    "fonds": {
        "label": "Фонды",
        "hint": "Подсказки в поле «Фонд» при приёме документов",
        "strict": False,
        "defaults": (),
    },
    "issue_purposes": {
        "label": "Цели выдачи дел",
        "hint": "Подсказки в поле «Цель» при выдаче дела во временное пользование",
        "strict": False,
        "defaults": ("Служебное пользование", "Проверка, аудит",
                     "Судебное разбирательство", "Исполнение архивного запроса"),
    },
}


def check_kind(kind: str) -> None:
    if kind not in KINDS:
        raise ValueError("Справочник не найден. Доступны: " + ", ".join(KINDS))


def check_value(kind: str, value: str, allowed: list[str]) -> None:
    """Строгий справочник принимает только действующие значения.

    Пустой справочник ввод не блокирует: иначе, выведя из употребления все
    значения, администратор остановил бы регистрацию.
    """
    spec = KINDS[kind]
    if spec["strict"] and allowed and value not in allowed:
        raise ValueError(f"Значения «{value}» нет в справочнике «{spec['label']}»")


def active_values(db: Session, kind: str) -> list[str]:
    rows = (db.query(DictionaryEntry.value)
            .filter(DictionaryEntry.kind == kind, DictionaryEntry.is_active.is_(True))
            .order_by(DictionaryEntry.sort_order, DictionaryEntry.value)
            .all())
    return [r[0] for r in rows]


def seed(db: Session) -> None:
    """Начальные значения — только в справочник, где записей ещё не было:
    иначе при каждом старте возвращались бы значения, которые администратор
    переименовал."""
    for kind, spec in KINDS.items():
        if not spec["defaults"]:
            continue
        if db.query(DictionaryEntry.id).filter(DictionaryEntry.kind == kind).first():
            continue
        db.add_all([DictionaryEntry(kind=kind, value=v, sort_order=i)
                    for i, v in enumerate(spec["defaults"], start=1)])
    db.commit()
