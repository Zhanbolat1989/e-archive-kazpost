# -*- coding: utf-8 -*-
"""SLA технической поддержки (ТС-176 разд. 13): сроки по уровням критичности,
показатели периода и формула оплаты."""
from datetime import datetime, timedelta

from app.config import settings
from app.services import sla


def _utc(year, month, day, hour, minute=0):
    """Момент по местному времени заказчика, выраженный в UTC."""
    return datetime(year, month, day, hour, minute) - timedelta(hours=settings.SLA_UTC_OFFSET_HOURS)


def test_critical_deadlines_run_around_the_clock():
    created = _utc(2026, 9, 12, 23, 30)                 # суббота, ночь
    reaction, resolution = sla.deadlines("critical", created)
    assert reaction - created == timedelta(minutes=40)
    assert resolution - created == timedelta(hours=1)


def test_business_hours_skip_evening_and_weekend():
    created = _utc(2026, 9, 11, 17, 0)                  # пятница, 17:00
    _, resolution = sla.deadlines("medium", created)    # 4 рабочих часа
    # час в пятницу и три часа с понедельника 9:00
    assert resolution == _utc(2026, 9, 14, 12, 0)


def test_ticket_before_workday_counts_from_nine():
    created = _utc(2026, 9, 14, 7, 0)                   # понедельник, 7:00
    reaction, _ = sla.deadlines("high", created)
    assert reaction == _utc(2026, 9, 14, 9, 40)


def test_on_time_share_ignores_tickets_not_yet_due():
    now = datetime(2026, 9, 14, 12)
    due = datetime(2026, 9, 14, 11)
    assert sla.resolved_on_time(due, datetime(2026, 9, 14, 10), now) is True
    assert sla.resolved_on_time(due, datetime(2026, 9, 14, 11, 30), now) is False
    assert sla.resolved_on_time(due, None, now) is False          # срок истёк без решения
    assert sla.resolved_on_time(datetime(2026, 9, 14, 13), None, now) is None
    assert sla.on_time_percent([True, False, None, True, True]) == 75.0
    assert sla.on_time_percent([None]) is None


def test_payment_formula_matches_spec():
    met = sla.payment(1_000_000, 99.95, 96.0)
    assert met["payment"] == 1_000_000 and met["availability_deduction"] == 0
    both = sla.payment(1_000_000, 99.0, 90.0)
    assert both["availability_deduction"] == 9_000.0     # (99,9 − 99,0) / 100 × сумма
    assert both["on_time_deduction"] == 50_000.0         # (95 − 90) / 100 × сумма
    assert both["payment"] == 941_000.0


def test_targets_themselves_are_met():
    assert sla.payment(100, 99.9, 95.0)["payment"] == 100


def test_availability_percent():
    assert sla.availability_percent(43_200, 43_200) == 100.0
    assert sla.availability_percent(43_157, 43_200) == 99.9
    assert sla.availability_percent(0, 0) is None
