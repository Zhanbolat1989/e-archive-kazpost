# -*- coding: utf-8 -*-
"""События «установка обновлений» и «изменение параметров» (ТС-176 разд. 14 п. 6)."""
import json

from app.services import system_state as st

BASE = {
    "version": "0.1.0",
    "audit": {"AUDIT_OPERATIONAL_DAYS": 90},
    "security": {"TWOFA_ENABLED": True},
    "system": {"EDITION": "kazpost"},
}


def test_first_start_is_a_baseline_not_a_change():
    assert st.changes(None, BASE) == []


def test_unchanged_state_records_nothing():
    assert st.changes(BASE, json.loads(json.dumps(BASE))) == []


def test_version_change_is_an_update_event():
    assert st.changes(BASE, {**BASE, "version": "0.2.0"}) == [("system.update", "0.1.0 → 0.2.0")]


def test_audit_parameter_change_names_parameter_and_values():
    (action, detail), = st.changes(BASE, {**BASE, "audit": {"AUDIT_OPERATIONAL_DAYS": 30}})
    assert action == "audit.settings"
    assert "AUDIT_OPERATIONAL_DAYS" in detail and "90" in detail and "30" in detail


def test_snapshot_contains_no_secrets():
    dumped = json.dumps(st.snapshot(), default=str)
    for secret in ("SECRET_KEY", "PASSWORD", "SMTP_USER"):
        assert secret not in dumped
