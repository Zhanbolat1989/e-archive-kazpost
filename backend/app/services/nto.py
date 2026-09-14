"""Научно-техническая обработка, экспертные комиссии и передача дел
(ТС-176 п. 5.3, 8.2, 10.2–10.5).

Экспертная комиссия организации (ЭК), центральная экспертная комиссия (ЦЭК —
в организации с филиалами) и экспертно-проверочная комиссия уполномоченного
органа (ЭПК) рассматривают описи, акты о выделении к уничтожению, документы
НТО и акты передачи. Решение фиксируется в реестре протоколов и переносится на
карточку объекта: опись получает статус, акт — ссылку на протокол.

Здесь только правила, без обращений к БД.
"""
from datetime import date

from ..models import CaseStatus

COMMISSIONS: dict[str, str] = {
    "ЭК": "Экспертная комиссия организации",
    "ЦЭК": "Центральная экспертная комиссия",
    "ЭПК": "Экспертно-проверочная комиссия уполномоченного органа",
}

DECISIONS: dict[str, str] = {
    "approved": "Одобрено",
    "agreed": "Согласовано",
    "revision": "Возвращено на доработку",
    "rejected": "Отклонено",
}
POSITIVE = ("approved", "agreed")

PROTOCOL_OBJECTS: dict[str, str] = {
    "inventory": "Опись дел",
    "destruction_act": "Акт о выделении к уничтожению",
    "nto": "Документ НТО",
    "transfer": "Акт приёма-передачи",
}

DRAFT = "Проект"
APPROVED = "Утверждён"
TRANSFER_DONE = "Передано"

# fields — текстовые разделы, которые пишет архивариус; сведения, которые
# система ведёт сама (дела, описи, этапы работ, акты), форма берёт из базы.
NTO_KINDS: dict[str, dict] = {
    "history_note": {
        "label": "Историческая справка",
        "prefix": "ИС",
        "fields": [
            ("history", "История фондообразователя: создание, переименования, реорганизации"),
            ("functions", "Функции и структура"),
            ("fund", "История фонда: поступления, полнота, утраты"),
        ],
        "needs_inventory": False,
        "has_items": False,
    },
    "inventory_preface": {
        "label": "Предисловие к описи",
        "prefix": "ПР",
        "fields": [
            ("history", "Краткая история фондообразователя"),
            ("content", "Состав и содержание документов"),
            ("arrangement", "Систематизация дел в описи"),
            ("completeness", "Полнота и сохранность документов"),
        ],
        "needs_inventory": True,
        "has_items": False,
    },
    "arrangement_act": {
        "label": "Акт о завершении работ по упорядочению документов",
        "prefix": "АУ",
        "fields": [
            ("works", "Выполненные работы"),
            ("conclusion", "Заключение"),
        ],
        "needs_inventory": False,
        "has_items": False,
    },
    "missing_act": {
        "label": "Акт о недостающих делах",
        "prefix": "АН",
        "fields": [
            ("search", "Принятые меры по розыску"),
            ("reasons", "Предполагаемые причины отсутствия"),
        ],
        "needs_inventory": False,
        "has_items": True,
    },
}


def protocol_label(commission: str, number: str, protocol_date: date) -> str:
    return f"{commission} № {number} от {protocol_date:%d.%m.%Y}"


def decision_label(decision: str, commission: str, number: str, protocol_date: date) -> str:
    return (f"{DECISIONS.get(decision, decision)} {commission}: протокол № {number} "
            f"от {protocol_date:%d.%m.%Y}")


def inventory_status(commission: str, decision: str) -> str:
    """Статус описи после решения комиссии."""
    if decision in POSITIVE:
        return "Согласована ЭПК" if commission == "ЭПК" else f"Одобрена {commission}"
    return "На доработке"


def clean_fields(kind: str, fields: dict) -> dict[str, str]:
    """Только разделы своей формы: лишние ключи в печать не попадут и в базе не нужны."""
    known = {key for key, _ in NTO_KINDS[kind]["fields"]}
    return {k: str(v).strip() for k, v in (fields or {}).items() if k in known}


def check_years(year_from: int | None, year_to: int | None) -> None:
    if year_from and year_to and year_from > year_to:
        raise ValueError("Начальный год позже конечного")


def check_approvable(kind: str, items: list) -> None:
    if NTO_KINDS[kind]["has_items"] and not items:
        raise ValueError("В акте нет ни одного дела")


def default_title(kind: str, inventory_number: str | None, fond: str,
                  year_from: int | None, year_to: int | None) -> str:
    label = NTO_KINDS[kind]["label"]
    if inventory_number:
        return f"{label}: опись № {inventory_number}"
    years = (f"{year_from}–{year_to}" if year_from and year_to
             else str(year_from or year_to or ""))
    return label + (f", фонд {fond}" if fond else "") + (f", {years}" if years else "")


def transfer_problems(cases) -> list[str]:
    """Почему дела нельзя передать на государственное хранение.

    Передаётся только закрытое дело: в формируемое ещё поступают документы, а
    уничтоженное или уже переданное в архиве организации не хранится."""
    problems = []
    for c in cases:
        name = c.index or c.title
        if c.status == CaseStatus.transferred:
            problems.append(f"{name}: уже передано")
        elif c.status == CaseStatus.destroyed:
            problems.append(f"{name}: уничтожено")
        elif c.status != CaseStatus.closed:
            problems.append(f"{name}: дело не закрыто")
    return problems


def ascii_name(value: str, fallback: str) -> str:
    """Имя файла для заголовка HTTP: только латиница, цифры и «-_.»."""
    safe = "".join(ch if ch.isascii() and (ch.isalnum() or ch in "-_.") else "_"
                   for ch in (value or "").replace("/", "-"))
    return safe.strip("_-.") or fallback
