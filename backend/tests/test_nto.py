# -*- coding: utf-8 -*-
"""НТО, решения экспертных комиссий и передача дел (ТС-176 п. 5.3, 8.2, 10.2–10.5)."""
from datetime import date
from types import SimpleNamespace

import pytest

from app.models import CaseStatus
from app.services import nto, nto_forms

ORG = "АО «Казпочта»"


def test_inventory_status_follows_commission_decision():
    assert nto.inventory_status("ЭК", "approved") == "Одобрена ЭК"
    assert nto.inventory_status("ЦЭК", "agreed") == "Одобрена ЦЭК"
    assert nto.inventory_status("ЭПК", "agreed") == "Согласована ЭПК"
    assert nto.inventory_status("ЭК", "revision") == "На доработке"
    assert nto.inventory_status("ЭПК", "rejected") == "На доработке"


def test_only_closed_cases_are_transferred():
    cases = [
        SimpleNamespace(index="01-01", title="А", status=CaseStatus.closed),
        SimpleNamespace(index="01-02", title="Б", status=CaseStatus.forming),
        SimpleNamespace(index="", title="В", status=CaseStatus.transferred),
        SimpleNamespace(index="01-04", title="Г", status=CaseStatus.destroyed),
    ]
    assert nto.transfer_problems(cases) == [
        "01-02: дело не закрыто", "В: уже передано", "01-04: уничтожено",
    ]


def test_fields_outside_the_form_are_dropped():
    assert nto.clean_fields("inventory_preface", {"history": " текст ", "hack": "x"}) == {
        "history": "текст",
    }


def test_years_and_approval_checks():
    with pytest.raises(ValueError, match="позже"):
        nto.check_years(2024, 2020)
    nto.check_years(2020, None)
    with pytest.raises(ValueError, match="ни одного дела"):
        nto.check_approvable("missing_act", [])
    nto.check_approvable("missing_act", [{"title": "Приказы"}])
    nto.check_approvable("history_note", [])


def test_default_titles():
    assert nto.default_title("inventory_preface", "1-2026/01", "", None, None) == (
        "Предисловие к описи: опись № 1-2026/01")
    assert nto.default_title("history_note", None, "Ф-1", 2001, 2025) == (
        "Историческая справка, фонд Ф-1, 2001–2025")


def test_ascii_file_names():
    assert nto.ascii_name("АУ-2026/01", "nto") == "2026-01"
    assert nto.ascii_name("Опись", "nto") == "nto"


def _record(**kw):
    base = dict(kind="missing_act", number="АН-2026/01", record_date=date(2026, 9, 14),
                status=nto.DRAFT, created_by="Архивариус", approved_by="", fields={},
                items=[], fond="Ф-1", year_from=2019, year_to=2024, title="")
    base.update(kw)
    return SimpleNamespace(**base)


def test_missing_act_lists_cases_and_escapes_text():
    rec = _record(items=[{"case_index": "01-02", "title": "Приказы <по личному составу>",
                          "years": "2019", "note": ""}],
                  fields={"search": "Проверены описи и акты выдачи"})
    html = nto_forms.missing_act_html(rec, ORG, ["Одобрено ЭК: протокол № 3 от 12.09.2026"])
    assert "01-02" in html and "&lt;по личному составу&gt;" in html
    assert "ПРОЕКТ" in html and "протокол № 3" in html
    assert "Проверены описи и акты выдачи" in html


def test_approved_record_has_no_draft_mark():
    rec = _record(kind="history_note", status=nto.APPROVED, approved_by="Директор")
    html = nto_forms.history_note_html(
        rec, ORG, ["Бухгалтерия"], {"cases": 5, "permanent": 2, "year_min": 2001, "year_max": 2020}, [])
    assert "ПРОЕКТ" not in html
    assert "Директор" in html and "Бухгалтерия" in html


def test_arrangement_act_uses_system_data():
    rec = _record(kind="arrangement_act", fields={"conclusion": "Документы упорядочены"})
    html = nto_forms.arrangement_act_html(
        rec, ORG,
        [{"number": "1-2024/01", "title": "Опись дел постоянного хранения", "kind": "Постоянного хранения",
          "year": 2024, "cases": 40}],
        {"cases": 38, "pages": 6840},
        [{"number": "АВ-2024/01", "date": date(2024, 12, 20), "documents": 120}],
        [],
    )
    assert "6840" in html and "1-2024/01" in html and "АВ-2024/01" in html
    assert "Документы упорядочены" in html


def test_transfer_act_totals():
    act = SimpleNamespace(number="АПП-2026/01", act_date=date(2026, 9, 14),
                          archive_name="Центральный государственный архив", fond="Ф-1",
                          basis="График передачи", note="", status=nto.DRAFT)
    items = [
        {"order_no": 1, "case_index": "01-01", "case_title": "Приказы", "volume": 1,
         "year": 2010, "documents_count": 12, "retention": "Постоянно"},
        {"order_no": 2, "case_index": "01-02", "case_title": "Протоколы", "volume": 2,
         "year": 2010, "documents_count": 3, "retention": "Постоянно"},
    ]
    html = nto_forms.transfer_act_html(act, ORG, items, ["Согласовано ЭПК: протокол № 7 от 01.09.2026"])
    assert "Центральный государственный архив" in html
    assert "Итого: <b>2</b>" in html and "<b>15</b>" in html
    assert "протокол № 7" in html and "ПРОЕКТ" in html
