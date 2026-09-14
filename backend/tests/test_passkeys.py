# -*- coding: utf-8 -*-
"""Вход по ключам доступа WebAuthn (ТС-176 разд. 14 п. 4.2).

Криптографическую проверку выполняет py_webauthn; здесь — правила вокруг неё.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.config import settings
from app.services import passkeys

NOW = datetime(2026, 9, 14, 12, 0)


def _challenge(**kw):
    base = dict(purpose="login", used_at=None, expires_at=NOW + timedelta(minutes=1))
    base.update(kw)
    return SimpleNamespace(**base)


def test_challenge_is_single_use_short_lived_and_purpose_bound():
    assert passkeys.challenge_problem(_challenge(), "login", NOW) is None
    assert "не найден" in passkeys.challenge_problem(None, "login", NOW)
    assert "не найден" in passkeys.challenge_problem(_challenge(purpose="register"), "login", NOW)
    assert "использован" in passkeys.challenge_problem(_challenge(used_at=NOW), "login", NOW)
    assert "истекло" in passkeys.challenge_problem(_challenge(expires_at=NOW), "login", NOW)


def test_base64url_round_trip_without_padding():
    raw = bytes(range(50))
    encoded = passkeys.b64url(raw)
    assert not set("=+/") & set(encoded)
    assert passkeys.from_b64url(encoded) == raw


def test_credential_fields_from_browser_json():
    credential = {"id": "abc", "rawId": "abc", "response": {"transports": ["internal", "hybrid", 5]}}
    assert passkeys.credential_id(credential) == "abc"
    assert passkeys.transports(credential) == ["internal", "hybrid"]
    assert passkeys.credential_id({}) == ""
    assert passkeys.transports({}) == []


def test_device_name_from_user_agent():
    assert passkeys.device_name("Mozilla/5.0 (Linux; Android 14; Pixel 8)") == "Android"
    assert passkeys.device_name("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X)") == "iPhone"
    assert passkeys.device_name("") == "Устройство"


def test_origins_list(monkeypatch):
    monkeypatch.setattr(settings, "WEBAUTHN_ORIGINS",
                        "https://archive.kazpost.kz, https://m.archive.kazpost.kz,")
    assert passkeys.origins() == ["https://archive.kazpost.kz", "https://m.archive.kazpost.kz"]


def test_production_requires_real_rp_id(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "WEBAUTHN_ENABLED", True)
    monkeypatch.setattr(settings, "WEBAUTHN_RP_ID", "localhost")
    assert any("WEBAUTHN_RP_ID" in p for p in settings.unsafe_defaults())
    monkeypatch.setattr(settings, "WEBAUTHN_RP_ID", "archive.kazpost.kz")
    assert not any("WEBAUTHN_RP_ID" in p for p in settings.unsafe_defaults())
    monkeypatch.setattr(settings, "WEBAUTHN_ENABLED", False)
    monkeypatch.setattr(settings, "WEBAUTHN_RP_ID", "localhost")
    assert not any("WEBAUTHN_RP_ID" in p for p in settings.unsafe_defaults())
