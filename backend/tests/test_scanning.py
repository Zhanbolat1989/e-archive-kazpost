# -*- coding: utf-8 -*-
"""Модуль «Сканирование» (ТС-176 п. 4.5): какой скан принимается в дело и как
складывается объём оказанных услуг к акту."""
import pytest

from app.models import DocType, WORK_STAGES
from app.services import scanning


def test_article_without_types_accepts_any_known_type():
    assert scanning.check_doc_type([], DocType.contract.value) == DocType.contract.value


def test_type_outside_article_is_rejected_with_allowed_list():
    with pytest.raises(ValueError) as err:
        scanning.check_doc_type([DocType.order.value], DocType.contract.value)
    assert DocType.order.value in str(err.value)


def test_unknown_type_is_rejected_even_without_restrictions():
    with pytest.raises(ValueError):
        scanning.check_doc_type([], "Неизвестный вид")


def test_title_from_filename():
    assert scanning.title_from_filename("Приказ_14_от_2019.pdf") == "Приказ 14 от 2019"
    assert scanning.title_from_filename("") == "Скан документа"


def test_volume_summary_lists_every_stage_in_spec_order():
    marks = [("scanning", 180), ("scanning", 175), ("nto", 180), ("unknown", 10)]
    summary = scanning.summarize(marks)
    assert [s["stage"] for s in summary] == list(WORK_STAGES)
    by_stage = {s["stage"]: s for s in summary}
    assert by_stage["scanning"]["cases"] == 2
    assert by_stage["scanning"]["pages"] == 355
    # Этап без работ за период остаётся в сводке с нулями.
    assert by_stage["expertise"] == {"stage": "expertise", "label": WORK_STAGES["expertise"],
                                     "cases": 0, "pages": 0}
