"""SLA технической поддержки (ТС-176 разд. 13): уровни критичности со сроками
реакции и устранения, «процент доступности», «процент запросов/инцидентов,
устранённых в срок» и размер оплаты услуг за отчётный период.

Чистые функции без базы данных: формулы спецификации проверяются тестами.
"""
from datetime import datetime, time, timedelta

from ..config import settings

# ТС-176 п. 13.1.1.1.2, минуты. business_hours=False — «по отдельным
# обращениям», то есть круглосуточно; остальные сроки — в рабочее время.
LEVELS = {
    "critical": {"label": "Критичный", "reaction": 40, "resolution": 60, "business_hours": False},
    "high": {"label": "Высокий", "reaction": 40, "resolution": 120, "business_hours": True},
    "medium": {"label": "Средний", "reaction": 60, "resolution": 240, "business_hours": True},
    "low": {"label": "Низкий", "reaction": 60, "resolution": 480, "business_hours": True},
}

KINDS = {
    "question": "Вопрос или ошибка в работе",
    "incident": "Инцидент: неработоспособность системы",
    "security_incident": "Инцидент ИБ",
    "service_request": "Заявка на дополнительную услугу",
}
# Заявка на услугу — не инцидент: сроков SLA у неё нет, в «процент устранённых
# в срок» она не входит.
SLA_KINDS = ("question", "incident", "security_incident")

# ТС-176 разд. 14 п. 2.9, 2.10, 6.1 — услуги по заявке из Личного кабинета
SERVICES = {
    "siem_integration": "Интеграция с SIEM заказчика",
    "antivirus": "Антивирусная проверка загружаемых файлов",
    "audit_extract": "Информация о логировании действий пользователя за период",
    "other": "Прочее",
}

STATUS_NEW = "Новое"
STATUS_IN_WORK = "В работе"
STATUS_RESOLVED = "Решено"
STATUS_RETURNED = "Возвращено на доработку"
STATUS_CLOSED = "Закрыто"
STATUSES = (STATUS_NEW, STATUS_IN_WORK, STATUS_RESOLVED, STATUS_RETURNED, STATUS_CLOSED)

AVAILABILITY_TARGET = 99.9
ON_TIME_TARGET = 95.0


def _to_local(ts_utc: datetime) -> datetime:
    return ts_utc + timedelta(hours=settings.SLA_UTC_OFFSET_HOURS)


def _to_utc(ts_local: datetime) -> datetime:
    return ts_local - timedelta(hours=settings.SLA_UTC_OFFSET_HOURS)


def add_minutes(start_utc: datetime, minutes: int, business_hours: bool) -> datetime:
    """Момент истечения срока в minutes минут — календарных либо рабочих.

    Рабочее время — будни с SLA_WORKDAY_START до SLA_WORKDAY_END по местному
    времени. Праздничные дни не учитываются: их перечень меняется ежегодно и
    согласуется с заказчиком отдельно."""
    if not business_hours:
        return start_utc + timedelta(minutes=minutes)
    day_start = time(settings.SLA_WORKDAY_START)
    day_end = time(settings.SLA_WORKDAY_END)
    cur = _to_local(start_utc)
    left = minutes
    while True:
        if cur.weekday() >= 5 or cur.time() >= day_end:
            cur = datetime.combine(cur.date() + timedelta(days=1), day_start)
            continue
        if cur.time() < day_start:
            cur = datetime.combine(cur.date(), day_start)
        available = int((datetime.combine(cur.date(), day_end) - cur).total_seconds() // 60)
        if left <= available:
            return _to_utc(cur + timedelta(minutes=left))
        left -= available
        cur = datetime.combine(cur.date() + timedelta(days=1), day_start)


def deadlines(criticality: str, created_utc: datetime) -> tuple[datetime, datetime]:
    """(срок реакции, срок устранения) обращения данного уровня."""
    level = LEVELS[criticality]
    return (add_minutes(created_utc, level["reaction"], level["business_hours"]),
            add_minutes(created_utc, level["resolution"], level["business_hours"]))


def resolved_on_time(resolution_due: datetime, resolved_at: datetime | None,
                     now: datetime) -> bool | None:
    """True — устранено в срок; False — не в срок либо срок истёк без решения;
    None — срок ещё не наступил, и в расчёт периода обращение пока не входит.

    Время устранения заканчивается получением ответа инициатором (п. 13.1.1.1.4);
    возвращённое на доработку обращение снова считается нерешённым."""
    if resolved_at is not None:
        return resolved_at <= resolution_due
    return False if now > resolution_due else None


def on_time_percent(results: list[bool | None]) -> float | None:
    """«Процент запросов/инцидентов, устранённых в срок» = X / Y × 100 %."""
    counted = [r for r in results if r is not None]
    if not counted:
        return None
    return round(sum(1 for r in counted if r) / len(counted) * 100, 2)


def availability_percent(available_minutes: int, total_minutes: int) -> float | None:
    """«Процент доступности» = A / B × 100 % (п. 13.1.2.2)."""
    if total_minutes <= 0:
        return None
    return round(min(available_minutes, total_minutes) / total_minutes * 100, 3)


def payment(amount: float, availability: float | None, on_time: float | None) -> dict:
    """Размер оплаты услуг за отчётный период (п. 13.1.3.1–13.1.3.4).

    Каждый показатель ниже цели уменьшает оплату на свою разницу в процентах;
    на цели и выше неустойки нет. Показатель без данных неустойки не порождает."""
    availability_deduction = (
        (AVAILABILITY_TARGET - availability) / 100 * amount
        if availability is not None and availability < AVAILABILITY_TARGET else 0.0
    )
    on_time_deduction = (
        (ON_TIME_TARGET - on_time) / 100 * amount
        if on_time is not None and on_time < ON_TIME_TARGET else 0.0
    )
    return {
        "amount": round(amount, 2),
        "availability_deduction": round(availability_deduction, 2),
        "on_time_deduction": round(on_time_deduction, 2),
        "payment": round(amount - availability_deduction - on_time_deduction, 2),
    }
