# -*- coding: utf-8 -*-
"""Редакции интерфейса.

Главный инвариант редакции «Казпочта» — каждый модуль ТС-176 (п. 4.2)
находится в меню: по этому списку заказчик принимает систему.
"""
import pytest

from app import edition
from app.config import settings


@pytest.fixture
def kazpost(monkeypatch):
    monkeypatch.setattr(settings, "EDITION", "kazpost")
    monkeypatch.setattr(settings, "EDITION_DISABLED_MODULES", "")
    return edition.profile()


def test_every_section_item_is_a_known_module():
    for key, prof in edition.EDITIONS.items():
        for section in prof["sections"]:
            unknown = set(section["items"]) - set(edition.MODULES)
            assert not unknown, f"{key}: неизвестные разделы {unknown}"


def test_kazpost_menu_covers_ts176_modules(kazpost):
    enabled = set(kazpost["modules"])
    # «Управление документами»: документы, дела, опись, номенклатура, запросы
    # на выдачу, инвентаризация и уничтожение (одна страница).
    assert {"documents", "cases", "inventories", "nomenclature", "issues",
            "lifecycle"} <= enabled
    assert "reports" in enabled          # «Управление отчетами»
    assert "scanning" in enabled         # «Сканирование»
    assert "nto" in enabled              # НТО, протоколы ЭК/ЦЭК, передача (п. 5.3, 8.2, 10)
    assert "help" in enabled             # «Помощь»
    assert "account" in enabled          # «Личный кабинет»
    assert "enterprise" in enabled       # «Предприятие»
    assert "security" in enabled         # «Администрирование»


def test_kazpost_hides_other_customers_modules(kazpost):
    assert "archive_requests" not in kazpost["modules"]


def test_kazpost_never_shows_demo_credentials(kazpost, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "dev")
    assert edition.profile()["demo"] is False


def test_disabled_modules_are_removed_with_empty_sections(monkeypatch):
    monkeypatch.setattr(settings, "EDITION", "kazpost")
    monkeypatch.setattr(settings, "EDITION_DISABLED_MODULES", "reports, enterprise")
    prof = edition.profile()
    assert "reports" not in prof["modules"]
    # Секция из двух отключённых разделов не должна оставаться пустым заголовком.
    assert all(s["items"] for s in prof["sections"])
