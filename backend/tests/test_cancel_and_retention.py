# -*- coding: utf-8 -*-
"""Отмена генерации и расчёт сроков хранения."""
import time
import uuid

import pytest

from app.services import cancel


def _rid() -> str:
    return uuid.uuid4().hex


def test_unknown_request_is_not_cancelled():
    assert cancel.is_cancelled(_rid()) is False
    assert cancel.is_cancelled(None) is False
    assert cancel.is_cancelled("") is False


def test_cancel_marks_only_its_own_request():
    """Отмена привязана к идентификатору: остановить чужую генерацию нельзя."""
    mine, other = _rid(), _rid()
    cancel.cancel(mine)
    assert cancel.is_cancelled(mine) is True
    assert cancel.is_cancelled(other) is False
    cancel.release(mine)


def test_release_clears_the_mark():
    rid = _rid()
    cancel.cancel(rid)
    cancel.release(rid)
    assert cancel.is_cancelled(rid) is False


def test_check_raises_only_when_cancelled():
    rid = _rid()
    cancel.check(rid)          # не должно бросать
    cancel.cancel(rid)
    with pytest.raises(cancel.Cancelled):
        cancel.check(rid)
    cancel.release(rid)


def test_checker_closure_reflects_current_state():
    rid = _rid()
    is_cancelled = cancel.checker(rid)
    assert is_cancelled() is False
    cancel.cancel(rid)
    assert is_cancelled() is True
    cancel.release(rid)


def test_stale_marks_expire(monkeypatch):
    """Отметка не должна отменять запрос, стартовавший много позже с тем же
    идентификатором, и не должна копиться в памяти."""
    rid = _rid()
    cancel.cancel(rid)
    # Оригинальную функцию сохраняем заранее: подменённая time.time не должна
    # вызывать саму себя.
    real_time = time.time
    monkeypatch.setattr(cancel.time, "time",
                        lambda: real_time() + cancel.TTL_SECONDS + 10)
    assert cancel.is_cancelled(rid) is False


# ---------------------------------------------------------------- сроки хранения
def test_retention_rules_cover_every_document_type():
    """Для каждого типа документа должен быть определён срок хранения:
    документ без срока невозможно ни списать, ни сохранить обоснованно."""
    from app.models import DocType
    from app.retention import rule_for

    for dt in DocType:
        rule = rule_for(dt)
        assert rule is not None, dt
        assert rule.permanent or rule.label, dt


def test_permanent_documents_have_no_expiry():
    from app.retention import compute_until

    assert compute_until(2020, None) is None


def test_expiry_is_counted_from_end_of_year():
    """Срок считается от конца года закрытия — так устроен архивный учёт."""
    from app.retention import compute_until

    until = compute_until(2020, 5)
    assert until is not None
    assert until.year == 2025
    assert (until.month, until.day) == (12, 31)
