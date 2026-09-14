# -*- coding: utf-8 -*-
"""Нарезка текста на чанки — основа поиска по длинным делам."""
from app.services import chunking


def test_short_text_stays_one_chunk():
    text = "Договор аренды № 14. Ежемесячная плата 450 000 тенге."
    assert chunking.split(text) == [text]


def test_empty_text_gives_no_chunks():
    assert chunking.split("") == []
    assert chunking.split("   \n  ") == []


def test_long_text_is_split_into_bounded_chunks():
    para = ("Пункт договора об ответственности сторон и порядке расчётов. " * 4).strip()
    text = "\n\n".join(para for _ in range(12))
    chunks = chunking.split(text, size=800, overlap=150)
    assert len(chunks) > 1
    # Небольшое превышение допустимо: чанк не рвётся посреди предложения.
    assert all(len(c) <= 1000 for c in chunks), [len(c) for c in chunks]


def test_no_content_is_lost_between_chunks():
    """Каждое предложение исходника должно найтись хотя бы в одном чанке:
    потерянный фрагмент — это факт, который архив больше не найдёт."""
    sentences = [f"Пункт {i} договора о порядке расчётов между сторонами."
                 for i in range(40)]
    text = " ".join(sentences)
    joined = " ".join(chunking.split(text))
    for s in sentences:
        assert s in joined


def test_chunks_overlap_so_facts_on_the_seam_survive():
    text = " ".join(f"Предложение номер {i} с достаточной длиной для нарезки."
                    for i in range(60))
    chunks = chunking.split(text, size=600, overlap=150)
    assert len(chunks) >= 2
    # Хвост предыдущего чанка должен встречаться в начале следующего.
    tail_words = chunks[0].split()[-5:]
    assert any(w in chunks[1] for w in tail_words)


def test_context_prefix_carries_card_metadata():
    prefix = chunking.context_prefix({
        "title": "Договор аренды", "doc_type": "Договор", "doc_number": "АР-2019/14",
        "doc_date": "2019-03-11", "counterparty": "ТОО «Астана Бизнес Центр»",
    })
    for part in ("Договор аренды", "АР-2019/14", "Астана Бизнес Центр"):
        assert part in prefix


def test_build_separates_display_text_from_embedding_text():
    """В контекст модели идёт чистый текст, а в индекс — текст с шапкой:
    иначе реквизиты попадали бы в цитату как шум."""
    doc = {"title": "Договор аренды", "doc_type": "Договор",
           "ocr_text": "Ежемесячная плата составляет 450 000 тенге."}
    chunks = chunking.build(doc)
    assert len(chunks) == 1
    assert chunks[0]["text"] == doc["ocr_text"]
    assert "Договор аренды" in chunks[0]["embed_text"]
    assert chunks[0]["text"] in chunks[0]["embed_text"]


def test_document_without_text_is_still_findable():
    """Скан без распознанного текста должен оставаться в индексе — по описанию
    и реквизитам, иначе он исчезнет из поиска совсем."""
    chunks = chunking.build({"title": "Акт без OCR", "doc_type": "Акт",
                             "ocr_text": "", "description": "Акт приёма-передачи"})
    assert len(chunks) == 1
    assert "Акт приёма-передачи" in chunks[0]["text"]
