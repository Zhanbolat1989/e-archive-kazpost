"""Маршруты согласования по оргструктуре (ТС-176 п. 4.10).

Шаблон маршрута описывает шаги не людьми, а позициями оргструктуры:
«руководитель подразделения», «руководитель вышестоящего подразделения»,
«руководитель выбранного подразделения» или конкретный сотрудник. Согласующие
подставляются в момент запуска — по подразделению объекта, а если оно не
указано, по подразделению инициатора. Смена руководителя не требует править
шаблоны, а уже запущенные маршруты остаются за теми, кому были направлены.

Здесь только правила подстановки, без обращений к БД: оргструктуру и учётные
записи собирает роутер.
"""
from dataclasses import dataclass

STEP_KINDS: dict[str, str] = {
    "head": "Руководитель подразделения",
    "parent_head": "Руководитель вышестоящего подразделения",
    "department_head": "Руководитель выбранного подразделения",
    "user": "Сотрудник",
}

OBJECT_TYPES: dict[str, str] = {
    "": "любой объект",
    "document": "документ",
    "case": "дело",
    "nomenclature": "статья номенклатуры",
}


@dataclass(frozen=True)
class Unit:
    """Подразделение в том объёме, что нужен подстановке."""
    name: str
    parent_id: str | None
    head_email: str = ""        # пусто — руководитель не назначен


@dataclass(frozen=True)
class PlannedStep:
    approver_email: str
    approver_name: str
    basis: str


def normalize_steps(steps: list[dict]) -> list[dict]:
    """Проверяет шаги шаблона и приводит их к виду {kind, value}."""
    if not steps:
        raise ValueError("Добавьте в шаблон хотя бы один шаг")
    out: list[dict] = []
    for no, step in enumerate(steps, start=1):
        kind = step.get("kind", "")
        if kind not in STEP_KINDS:
            raise ValueError(f"Шаг {no}: неизвестный вид шага «{kind}»")
        value = str(step.get("value") or "").strip()
        if kind == "department_head" and not value:
            raise ValueError(f"Шаг {no}: выберите подразделение")
        if kind == "user" and not value:
            raise ValueError(f"Шаг {no}: укажите сотрудника")
        if kind in ("head", "parent_head"):
            value = ""
        out.append({"kind": kind, "value": value})
    return out


def _approver(no: int, step: dict, department_id: str | None,
              units: dict[str, Unit], users: dict[str, str]) -> tuple[str, str]:
    kind, value = step["kind"], step["value"]
    if kind == "user":
        if value not in users:
            raise ValueError(f"Шаг {no}: сотрудник {value} не найден или отключён")
        return value, STEP_KINDS["user"]

    if kind == "department_head":
        unit_id = value
    elif department_id:
        unit_id = department_id
    else:
        raise ValueError(
            f"Шаг {no}: не определено подразделение — укажите его в карточке "
            "объекта или в профиле инициатора"
        )
    unit = units.get(unit_id)
    if unit is None:
        raise ValueError(f"Шаг {no}: подразделение не найдено в оргструктуре")
    if kind == "parent_head":
        if unit.parent_id not in units:
            raise ValueError(f"Шаг {no}: у подразделения «{unit.name}» нет вышестоящего")
        unit = units[unit.parent_id]
    # Отключённый руководитель решения не примет — маршрут встал бы на этом
    # шаге навсегда, поэтому это ошибка запуска, а не пропуск.
    if unit.head_email not in users:
        raise ValueError(f"Шаг {no}: у подразделения «{unit.name}» нет действующего руководителя")
    return unit.head_email, f"Руководитель: {unit.name}"


def resolve(steps: list[dict], department_id: str | None, units: dict[str, Unit],
            users: dict[str, str], initiator_email: str) -> list[PlannedStep]:
    """Согласующие по шаблону в порядке шагов.

    `users` — действующие учётные записи {email: ФИО}. Шаг, которому некого
    назначить, — ошибка: маршрут без обязательного согласующего выглядел бы
    согласованным, не будучи им. Инициатор сам себе не согласует, и один
    человек не согласует дважды — такие шаги опускаются.
    """
    planned: list[PlannedStep] = []
    seen = {initiator_email}
    for no, step in enumerate(normalize_steps(steps), start=1):
        email, basis = _approver(no, step, department_id, units, users)
        if email in seen:
            continue
        seen.add(email)
        planned.append(PlannedStep(email, users[email], basis))
    if not planned:
        raise ValueError("Все согласующие по шаблону совпадают с инициатором — "
                         "выберите другой шаблон")
    return planned


def creates_cycle(dep_id: str, parent_id: str | None,
                  parents: dict[str, str | None]) -> bool:
    """Замкнётся ли дерево оргструктуры, если подчинить `dep_id` подразделению `parent_id`."""
    seen: set[str] = set()
    node = parent_id
    while node and node not in seen:
        if node == dep_id:
            return True
        seen.add(node)
        node = parents.get(node)
    return False
