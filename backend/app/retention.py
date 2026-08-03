# -*- coding: utf-8 -*-
"""Сроки хранения по типам документов.

Базируется на Перечне типовых документов с указанием срока хранения
(приказ Министра культуры и информации РК от 17.06.2025 № 279-НҚ).
Номера конкретных статей перечня не фиксируются здесь программно — они
задаются архивариусом в номенклатуре дел; ниже — типовые сроки по категориям.

PERMANENT = постоянное хранение; None в years при need_review=True — «до
минования надобности» (срок определяется организацией).
"""
from dataclasses import dataclass

from .models import DocType

PERMANENT = "Постоянно"
LONG_75 = "75 лет"


@dataclass(frozen=True)
class RetentionRule:
    label: str          # человекочитаемый срок: «5 лет», «75 лет», «Постоянно»
    years: int | None   # None => постоянно или «до минования надобности»
    permanent: bool = False
    note: str = ""


_R5 = RetentionRule("5 лет", 5)
_R75 = RetentionRule(LONG_75, 75)
_RP = RetentionRule(PERMANENT, None, permanent=True)
_RDMN = RetentionRule("До минования надобности", None,
                      note="Срок определяется организацией")

# Типовые сроки по категориям перечня 279-НҚ.
RETENTION_DEFAULTS: dict[DocType, RetentionRule] = {
    # Финансово-договорные (первичные учётные документы — 5 лет после
    # завершения операций/истечения срока действия)
    DocType.contract: RetentionRule("5 лет", 5, note="после истечения срока действия договора"),
    DocType.invoice: _R5,
    DocType.act: _R5,
    DocType.payment: _R5,
    DocType.waybill: _R5,
    DocType.expense_report: _R5,
    DocType.accounting_note: _R5,
    DocType.tax_report: _R5,
    DocType.bank_statement: _R5,
    DocType.estimate: _R5,
    # Кадровые (документы по личному составу — 75 лет)
    DocType.employment_contract: _R75,
    DocType.personnel_order: _R75,
    DocType.statement: RetentionRule(LONG_75, 75, note="в составе личного дела"),
    DocType.personal_file: _R75,
    DocType.staffing: _RP,
    DocType.timesheet: RetentionRule("5 лет", 5, note="75 лет при вредных условиях труда"),
    DocType.reference: _R5,
    # Канцелярия / организационно-распорядительные (по основной деятельности —
    # постоянно; переписка — 5 лет)
    DocType.order: _RP,
    DocType.decree: _RP,
    DocType.protocol: _RP,
    DocType.memo: _R5,
    DocType.incoming: _R5,
    DocType.outgoing: _R5,
    DocType.regulation: _RP,
    DocType.letter: _R5,
    # Недвижимое имущество: правоустанавливающие/правоудостоверяющие документы
    # хранятся постоянно (право на объект переживает организацию-владельца).
    # Технический паспорт актуализируется со временем — «до минования
    # надобности» (заменяется при обновлении характеристик объекта).
    DocType.title_deed: RetentionRule(PERMANENT, None, permanent=True,
                                       note="ст. 6-7 Закона № 310-III: правоустанавливающий документ"),
    DocType.rights_certificate: _RP,
    DocType.land_act: _RP,
    DocType.registry_extract: _RP,
    DocType.cadastral_passport: RetentionRule("До минования надобности", None,
                                              note="актуализируется при изменении характеристик объекта"),
    DocType.mortgage_contract: RetentionRule("5 лет", 5,
                                             note="после полного погашения обязательства / снятия обременения"),
    DocType.other: _RDMN,
}


def rule_for(doc_type: DocType) -> RetentionRule:
    return RETENTION_DEFAULTS.get(doc_type, _RDMN)


def compute_until(base_year: int, years: int | None):
    """Срок хранения исчисляется с 1 января года, следующего за годом
    завершения — т.е. хранение до 31 декабря (base_year + years)."""
    from datetime import date as _date

    if years is None:
        return None
    return _date(base_year + years, 12, 31)
