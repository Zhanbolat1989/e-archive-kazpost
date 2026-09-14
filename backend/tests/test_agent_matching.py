# -*- coding: utf-8 -*-
"""Разбор вопроса пользователя агентом.

Сопоставление типа документа ломалось дважды: «счетов-фактур» не находилось,
а «сколько договоров» попадало в «Трудовой договор». Эти случаи закреплены
тестами, чтобы правило не откатилось незаметно.
"""
import pytest

from app.models import DocType
from app.services import agent


def _match(question: str):
    """Повторяет правило выбора типа из _count_answer: совпасть должны все
    корни названия, побеждает самый специфичный тип."""
    import re

    q = agent._norm(question)
    matched, best = None, 0
    for dt in DocType:
        name = agent._norm(dt.value)
        stems = [w[:5] for w in re.split(r"[^а-яa-z]+", name) if len(w) >= 3]
        if not stems or not all(s in q for s in stems):
            continue
        if len(stems) > best:
            matched, best = dt, len(stems)
    return matched


@pytest.mark.parametrize("question, expected", [
    ("сколько договоров в архиве?", DocType.contract),
    ("сколько трудовых договоров?", DocType.employment_contract),
    ("сколько счетов-фактур?", DocType.invoice),
    ("сколько платёжных поручений?", DocType.payment),
    ("сколько приказов?", DocType.order),
    ("сколько кадастровых паспортов?", DocType.cadastral_passport),
])
def test_document_type_is_recognised_in_word_forms(question, expected):
    assert _match(question) is expected


def test_generic_question_matches_no_type():
    """«Сколько каких документов» — вопрос обо всём архиве. Слово «документов»
    входит в название нескольких типов, и по одному корню тип выбирать нельзя."""
    assert _match("сколько каких документов есть?") is None
    assert _match("сколько всего документов?") is None


def test_norm_folds_yo_and_case():
    assert agent._norm("Счёт-Фактура") == agent._norm("счет-фактура")


def test_followup_detection_requires_dialog_history():
    """Первый вопрос переписывать не по чему — лишний вызов модели не нужен."""
    history = [{"role": "user", "content": "а какая пеня?"}]
    assert agent._looks_like_followup("а какая пеня?", history) is False


def test_short_pronoun_question_is_treated_as_followup():
    history = [
        {"role": "user", "content": "какая арендная плата по договору аренды?"},
        {"role": "assistant", "content": "450 000 тенге."},
        {"role": "user", "content": "а какая пеня?"},
    ]
    assert agent._looks_like_followup("а какая пеня?", history) is True


def test_self_contained_question_is_not_rewritten():
    """Длинный самостоятельный вопрос не должен платить за лишний вызов LLM."""
    history = [
        {"role": "user", "content": "какая арендная плата?"},
        {"role": "assistant", "content": "450 000 тенге."},
        {"role": "user", "content": "x"},
    ]
    q = ("какая сумма указана в договоре поставки компьютерного оборудования "
         "с ТОО «АйТи Сервис» за 2021 год")
    assert agent._looks_like_followup(q, history) is False
