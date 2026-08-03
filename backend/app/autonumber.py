# -*- coding: utf-8 -*-
"""Автогенерация служебных номеров (индекс дела, статья номенклатуры, номер
внутреннего документа), когда пользователь оставляет поле пустым.

Схема — последовательный номер в рамках префикса и года, тем же способом,
которым уже нумеруются ЭРКК (документы) и акты уничтожения (лифецикл):
count(существующих с этим префиксом-годом) + 1. Best-effort, без блокировки
на уровне БД — при конкурентной записи возможен редкий дубль номера (как и в
остальной кодовой базе); для однопользовательского/малого архива это
приемлемый компромисс.
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Case, NomenclatureItem, Document, DocType

# Внутренние (издаваемые самой организацией) типы документов — для них номер
# логично присваивать самим архивом, а не переносить с внешнего оригинала.
# Внешние типы (Договор, Счёт-фактура, Акт и т.п.) сохраняют номер контрагента
# и никогда не нумеруются автоматически.
_INTERNAL_PREFIXES: dict[DocType, str] = {
    DocType.order: "П",
    DocType.personnel_order: "К",
    DocType.decree: "Р",
    DocType.protocol: "ПР",
    DocType.memo: "СЗ",
    DocType.statement: "ЗАЯВ",
    DocType.incoming: "ВХ",
    DocType.outgoing: "ИСХ",
    DocType.reference: "СПР",
}


def next_nomenclature_index(db: Session, year: int) -> str:
    """Следующий свободный индекс статьи номенклатуры за год: 01-01, 01-02, …"""
    count = db.query(func.count(NomenclatureItem.id)).filter(
        NomenclatureItem.year == year
    ).scalar() or 0
    return f"01-{count + 1:02d}"


def next_case_index(db: Session, year: int) -> str:
    """Следующий свободный индекс дела за год, когда номенклатура не выбрана."""
    count = db.query(func.count(Case.id)).filter(Case.year == year).scalar() or 0
    return f"Д-{year}-{count + 1:03d}"


def is_internal_type(doc_type: DocType) -> bool:
    return doc_type in _INTERNAL_PREFIXES


def next_document_number(db: Session, doc_type: DocType, year: int) -> str | None:
    """Следующий номер для внутреннего документа (напр. «П-2026/03»).
    None — если тип не относится к внутренним (номер должен прийти с оригинала)."""
    prefix = _INTERNAL_PREFIXES.get(doc_type)
    if prefix is None:
        return None
    count = db.query(func.count(Document.id)).filter(
        Document.doc_type == doc_type,
        Document.doc_number.like(f"{prefix}-{year}/%"),
    ).scalar() or 0
    return f"{prefix}-{year}/{count + 1:02d}"
