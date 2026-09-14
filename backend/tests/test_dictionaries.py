# -*- coding: utf-8 -*-
"""Редактируемые справочники (ТС-176 п. 4.9)."""
import pytest

from app.schemas import ArchiveRequestCreate
from app.services import dictionaries

ALLOWED = ["Тематический", "Биографический"]


def test_strict_dictionary_rejects_values_outside_it():
    dictionaries.check_value("request_types", "Тематический", ALLOWED)
    with pytest.raises(ValueError, match="Виды архивных запросов"):
        dictionaries.check_value("request_types", "Устный", ALLOWED)


def test_empty_strict_dictionary_does_not_block_input():
    dictionaries.check_value("request_types", "Любой", [])


def test_suggestion_dictionary_accepts_free_text():
    dictionaries.check_value("fonds", "Ф-99", ["Ф-1"])


def test_unknown_dictionary():
    with pytest.raises(ValueError, match="request_types"):
        dictionaries.check_kind("roles")


def test_default_request_type_is_seeded():
    """Значение по умолчанию в схеме должно пройти строгую проверку на чистой базе."""
    default = ArchiveRequestCreate.model_fields["request_type"].default
    assert default in dictionaries.KINDS["request_types"]["defaults"]
