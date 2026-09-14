# -*- coding: utf-8 -*-
"""Проверки конфигурации безопасности: значения по умолчанию не должны
незаметно доехать до промышленного контура."""
from app.config import Settings


def _settings(**over) -> Settings:
    base = dict(
        SECRET_KEY="x" * 48, FIRST_ADMIN_PASSWORD="Sufficiently-Long-Pass1",
        POSTGRES_PASSWORD="strong-db-pass", MINIO_ROOT_PASSWORD="strong-minio-pass",
        ENVIRONMENT="production", CORS_ORIGINS="https://archive.example.kz",
    )
    base.update(over)
    return Settings(**base)


def test_well_configured_production_has_no_complaints():
    assert _settings().unsafe_defaults() == []


def test_default_secret_key_is_reported():
    problems = _settings(SECRET_KEY="change-me").unsafe_defaults()
    assert any("SECRET_KEY" in p for p in problems)


def test_short_secret_key_is_reported():
    problems = _settings(SECRET_KEY="short").unsafe_defaults()
    assert any("SECRET_KEY" in p for p in problems)


def test_demo_admin_password_is_reported():
    problems = _settings(FIRST_ADMIN_PASSWORD="admin12345").unsafe_defaults()
    assert any("FIRST_ADMIN_PASSWORD" in p for p in problems)


def test_demo_infrastructure_passwords_are_reported():
    problems = _settings(POSTGRES_PASSWORD="earchive",
                         MINIO_ROOT_PASSWORD="minioadmin123").unsafe_defaults()
    assert any("POSTGRES_PASSWORD" in p for p in problems)
    assert any("MINIO_ROOT_PASSWORD" in p for p in problems)


def test_explicit_wildcard_cors_is_rejected_in_production():
    problems = _settings(CORS_ORIGINS="*").unsafe_defaults()
    assert any("CORS" in p for p in problems)


def test_empty_cors_in_production_is_not_flagged():
    """Пустая настройка в production безопасна: она не разрешает ничего.
    Фронтенд ходит через тот же origin (nginx проксирует /api), CORS не нужен."""
    assert _settings(CORS_ORIGINS="").unsafe_defaults() == []


def test_dev_allows_open_cors_by_default():
    s = Settings(ENVIRONMENT="dev", CORS_ORIGINS="")
    assert s.cors_origins == ["*"]


def test_production_without_origins_allows_nothing():
    """Пустой список безопаснее «любого»: браузер просто не получит доступ,
    вместо того чтобы получить его откуда угодно."""
    s = _settings(CORS_ORIGINS="")
    assert s.cors_origins == []


def test_cors_origins_are_parsed_as_list():
    s = _settings(CORS_ORIGINS="https://a.kz, https://b.kz")
    assert s.cors_origins == ["https://a.kz", "https://b.kz"]
