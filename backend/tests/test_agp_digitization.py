# -*- coding: utf-8 -*-
"""ТЗ «Азиатский Газопровод»: постраничный OCR, реквизиты, качество, дубли,
расширенный поиск."""
import pytest

from app.config import settings
from app.services import chunking, entities, ocr, quality, search

PB = chunking.PAGE_BREAK


# ------------------------------------------------------------ страницы и чанки
def test_chunks_carry_page_numbers():
    text = "Первая страница договора." + PB + "Вторая страница с суммой 450 000 тенге."
    chunks = chunking.build({"title": "Договор", "ocr_text": text})
    assert [c["page_no"] for c in chunks] == [1, 2]
    assert "450 000" in chunks[1]["text"]


def test_chunk_never_crosses_page_border():
    long_page = "Слово предложения для нарезки на части. " * 60
    chunks = chunking.build({"ocr_text": long_page + PB + "Короткая вторая."})
    assert chunks[-1]["page_no"] == 2
    assert all(c["page_no"] == 1 for c in chunks[:-1])


def test_empty_first_page_keeps_numbering():
    """Пустая первая страница (обложка без текста) не должна сдвигать номера."""
    chunks = chunking.build({"ocr_text": PB + "Текст на второй странице."})
    assert chunks[0]["page_no"] == 2


# ------------------------------------------------------------ разбор TSV OCR
TSV = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
    "1\t1\t0\t0\t0\t0\t0\t0\t800\t160\t-1\t\n"
    "5\t1\t1\t1\t1\t1\t10\t10\t50\t20\t90.5\tДоговор\n"
    "5\t1\t1\t1\t1\t2\t70\t10\t20\t20\t80.5\t№14\n"
    "5\t1\t1\t1\t2\t1\t10\t40\t60\t20\t70\tаренды\n"
    "5\t1\t1\t2\t1\t1\t10\t80\t60\t20\t60\tСумма\n"
)


def test_tsv_rebuilds_lines_and_paragraphs():
    text, conf, words = ocr.parse_tsv(TSV)
    assert text == "Договор №14\nаренды\n\nСумма"
    assert words == 4
    assert conf == pytest.approx((90.5 + 80.5 + 70 + 60) / 4)


def test_tsv_without_words_has_no_confidence():
    header = TSV.splitlines()[0] + "\n"
    assert ocr.parse_tsv(header) == ("", None, 0)
    assert ocr.parse_tsv("") == ("", None, 0)


# ------------------------------------------------------------ реквизиты
DOC = (
    "ДОГОВОР ПОСТАВКИ № АГП-2019/14\n"
    "г. Алматы, 11 марта 2019 г.\n"
    "ТОО «Азиатский Газопровод», БИН 070540011223, и ТОО «Кагаз Логистик».\n"
    "Сумма договора 12 800 000 тенге." + PB +
    "Оплата по счёту № СФ-2019/7 от 15.03.2019. Подписал Мукушев Д.Б.\n"
    "Ответственный: Иванов Сергей Петрович, пр. Абая 109В."
)


def _by_kind(found, kind):
    return [e for e in found if e.kind == kind]


def test_dates_are_normalized_from_words_and_digits():
    found = entities.extract(DOC)
    dates = {e.normalized for e in _by_kind(found, "date")}
    assert "2019-03-11" in dates and "2019-03-15" in dates


def test_amount_and_bin_are_extracted():
    found = entities.extract(DOC)
    assert "12800000.00 KZT" in {e.normalized for e in _by_kind(found, "amount")}
    assert "070540011223" in {e.normalized for e in _by_kind(found, "bin")}


def test_every_entity_is_bound_to_page_and_fragment():
    found = entities.extract(DOC)
    ref = _by_kind(found, "doc_ref")
    assert ref and ref[0].page_no == 2
    assert "СФ-2019/7" in ref[0].normalized
    assert all(e.fragment for e in found)


def test_reference_number_is_not_duplicated_as_own_number():
    """«по счёту № СФ-2019/7» — ссылка на другой документ, а не номер этого."""
    found = entities.extract(DOC)
    own_numbers = {e.normalized for e in _by_kind(found, "reg_number")}
    assert "АГП-2019/14" in own_numbers
    assert "СФ-2019/7" not in own_numbers


def test_organizations_persons_and_places():
    found = entities.extract(DOC)
    orgs = {e.normalized for e in _by_kind(found, "organization")}
    assert "ТОО «Кагаз Логистик»" in orgs
    persons = {e.normalized for e in _by_kind(found, "person")}
    assert "Иванов Сергей Петрович" in persons
    assert any("Мукушев" in p for p in persons)
    geo = " ".join(e.normalized for e in _by_kind(found, "geo"))
    assert "Алматы" in geo


def test_kazakh_date_is_recognised():
    found = entities.extract("Шарт 2021 жылғы 5 наурыз жасалды.")
    assert "2021-03-05" in {e.normalized for e in _by_kind(found, "date")}


def test_invalid_date_is_rejected():
    assert not _by_kind(entities.extract("Код 45.17.2019 не дата."), "date")


def test_suggestions_skip_own_organization():
    sugg = entities.suggest_requisites(entities.extract(DOC),
                                       own_org="Азиатский Газопровод")
    assert sugg["doc_date"] == "2019-03-11"
    assert sugg["doc_number"] == "АГП-2019/14"
    assert sugg["counterparty"] == "ТОО «Кагаз Логистик»"
    assert sugg["amount"] == 12800000.0 and sugg["currency"] == "KZT"


# ------------------------------------------------------------ качество OCR
def test_clean_text_needs_no_review():
    text = "Договор аренды офисного помещения заключён между сторонами. " * 5
    assert quality.assess(text, 92.0, 1) == (False, "")


def test_low_confidence_is_flagged():
    flagged, reason = quality.assess("Текст " * 20, 45.0, 1)
    assert flagged and "уверенность" in reason


def test_garbage_and_empty_pages_are_flagged():
    garbage = "~#| ,.; ### @@ " * 20
    flagged, reason = quality.assess(garbage + PB + "", 80.0, 2)
    assert flagged
    assert "пустых страниц" in reason


def test_truncated_document_is_flagged():
    flagged, reason = quality.assess("Нормальный текст документа. " * 10, 90.0, 1,
                                     truncated=True)
    assert flagged and "не все страницы" in reason


def test_rescan_of_same_text_is_similar():
    base = " ".join(f"пункт {i} договора о поставке газа" for i in range(40))
    rescan = base.replace("пункт 7 ", "пупкт 7 ")   # одна ошибка распознавания
    assert quality.jaccard(quality.shingles(base), quality.shingles(rescan)) > 0.85


def test_edited_rescan_lands_in_the_review_band():
    """Лист, пересканированный с добавленной строкой, дублем не считается, но
    похож достаточно, чтобы попасть на ручную проверку."""
    # Короткий документ на один лист: приписка в несколько слов меняет заметную
    # долю его текста — в отличие от многостраничного дела.
    base = " ".join(f"пункт {i} договора о поставке газа" for i in range(6))
    edited = base + " лист пересканирован после внесения рукописной правки в текст"
    score = quality.jaccard(quality.shingles(base), quality.shingles(edited))
    assert settings.SIMILAR_REVIEW_THRESHOLD <= score < settings.NEAR_DUPLICATE_THRESHOLD


def test_different_documents_are_not_similar():
    a = " ".join(f"договор аренды пункт {i}" for i in range(40))
    b = " ".join(f"приказ о приёме работника {i}" for i in range(40))
    assert quality.jaccard(quality.shingles(a), quality.shingles(b)) < 0.1


# ------------------------------------------------------------ расширенный поиск
@pytest.mark.parametrize("q, expected", [
    ("договор И аренда", "договор + аренда"),
    ("договор ИЛИ приказ", "договор | приказ"),
    ("договор НЕ аренда", "договор -аренда"),
    ('"договор аренды" ИЛИ акт', '"договор аренды" | акт'),
])
def test_operators_are_translated(q, expected):
    assert search.has_operators(q)
    assert search.to_simple_syntax(q) == expected


def test_lowercase_words_are_not_operators():
    """Строчные «и», «не» — обычные слова запроса, а не операторы."""
    assert not search.has_operators("договор и акт не подписан")
