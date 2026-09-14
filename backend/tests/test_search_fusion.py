# -*- coding: utf-8 -*-
"""Объединение результатов двух поисков (RRF) и версионирование схемы индекса."""
from app.services import search


def test_rrf_rewards_presence_in_both_rankings():
    """Документ, найденный обоими поисками, обходит найденные лишь одним —
    в этом и смысл гибридного поиска."""
    lexical = ["only_lexical", "in_both"]
    semantic = ["in_both", "only_semantic"]
    scores = search._rrf([lexical, semantic])
    assert scores["in_both"] > scores["only_lexical"]
    assert scores["in_both"] > scores["only_semantic"]
    assert set(scores) == {"only_lexical", "in_both", "only_semantic"}


def test_rrf_depends_on_rank_not_on_raw_score():
    """RRF работает с местами в выдаче: шкалы BM25 и косинусной близости
    несопоставимы, и нормализовать их пришлось бы произвольно."""
    scores = search._rrf([["x", "y"]])
    assert scores["x"] > scores["y"]
    assert scores["x"] == 1.0 / (search.RRF_K + 1)


def test_rrf_of_empty_input_is_empty():
    assert search._rrf([]) == {}
    assert search._rrf([[]]) == {}


def test_index_meta_pins_embedding_model():
    """Схема индекса помнит модель эмбеддингов: векторы, посчитанные другой
    моделью, несравнимы с новыми запросами, и поиск деградировал бы молча."""
    assert "embedding_model" in search._INDEX_META
    assert "schema" in search._INDEX_META


def test_metadata_is_copied_into_every_chunk():
    """Фильтры и точный поиск по реквизитам работают на уровне чанка."""
    meta = search._meta({
        "id": "doc-1", "title": "Договор", "doc_number": "АР-2019/14",
        "counterparty": "ТОО «Астана»", "cadastral_number": "21:312:001:0157",
    })
    assert meta["doc_id"] == "doc-1"
    assert meta["doc_number"] == "АР-2019/14"
    assert meta["cadastral_number"] == "21:312:001:0157"
