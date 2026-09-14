# -*- coding: utf-8 -*-
"""Роль «аудитор ИБ» (ТС-176 разд. 14 п. 5.1): журналы — да, документы — нет."""
from types import SimpleNamespace

from app.models import DocType, Role
from app.services import access


def test_auditor_sees_no_document_categories():
    auditor = SimpleNamespace(role=Role.auditor)
    assert access.allowed_types(None, auditor) == set()
    # Пустой список, а не None: поиск трактует None как «без ограничений».
    assert access.allowed_type_values(None, auditor) == []


def test_auditor_cannot_open_any_document():
    doc = SimpleNamespace(id="d1", doc_type=DocType.contract)
    assert access.can_see(None, SimpleNamespace(role=Role.auditor), doc) is False


def test_admin_is_never_restricted():
    assert access.allowed_types(None, SimpleNamespace(role=Role.admin)) is None
