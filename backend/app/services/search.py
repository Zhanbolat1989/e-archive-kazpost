"""Индекс OpenSearch и гибридный поиск (лексика + смысл) по чанкам документов.

Единица индексации — чанк, а не документ целиком: см. services/chunking.py.
Результаты двух поисков объединяются алгоритмом RRF (Reciprocal Rank Fusion),
после чего чанки схлопываются обратно в документы.
"""
import logging
import re

from opensearchpy import OpenSearch, helpers

from ..config import settings
from . import embeddings, chunking, reranker

log = logging.getLogger(__name__)

_client = OpenSearch(
    hosts=[{"host": settings.OPENSEARCH_HOST, "port": settings.OPENSEARCH_PORT}],
    http_compress=True,
    use_ssl=False,
    verify_certs=False,
)

INDEX = settings.OPENSEARCH_INDEX

# Сколько кандидатов тянуть из каждого поиска до объединения. Реранжирование
# работает только если есть из чего выбирать, поэтому кандидатов заметно больше,
# чем нужно на выходе.
CANDIDATE_FACTOR = 6
MIN_CANDIDATES = 30
# Ограничение чанков на документ: без него один длинный документ занимает всю
# выдачу и вытесняет остальные (простая замена MMR для разнообразия контекста).
MAX_CHUNKS_PER_DOC = 2
# Константа RRF из исходной статьи Cormack et al.; сглаживает вклад хвоста.
RRF_K = 60

# Версия схемы + модель эмбеддингов. Индекс пересоздаётся при их изменении:
# векторы, посчитанные другой моделью (или другой версией с иным пулингом),
# несравнимы с новыми запросами, и поиск молча деградировал бы.
_INDEX_META = {
    # 3 — русская морфология, номер страницы и подразделение у чанка
    "schema": 3,
    "embedding_model": settings.EMBEDDING_MODEL,
}

_MAPPING = {
    "settings": {"index": {"knn": True}},
    "mappings": {
        "_meta": _INDEX_META,
        "properties": {
            # Ссылка на документ-владелец: по ней чанки схлопываются и удаляются.
            "doc_id": {"type": "keyword"},
            "chunk_no": {"type": "integer"},
            # Страница, с которой взят чанк: ответ ассистента ссылается на
            # документ, страницу и фрагмент (ТЗ АГП п. 12.3).
            "page_no": {"type": "integer"},
            "department_id": {"type": "keyword"},
            # Русский анализатор сводит словоформы к основе («договоров»,
            # «договору» → «договор»); подполе .std хранит исходные токены —
            # для точных совпадений и казахского текста, морфологии которого
            # в OpenSearch нет (ТЗ АГП п. 12.2).
            "chunk_text": {"type": "text", "analyzer": "russian",
                           "fields": {"std": {"type": "text", "analyzer": "standard"}}},
            "title": {"type": "text", "analyzer": "russian",
                      "fields": {"kw": {"type": "keyword"},
                                 "std": {"type": "text", "analyzer": "standard"}}},
            "description": {"type": "text", "analyzer": "russian",
                            "fields": {"std": {"type": "text", "analyzer": "standard"}}},
            "fond": {"type": "keyword"},
            "opis": {"type": "keyword"},
            "delo": {"type": "keyword"},
            "doc_type": {"type": "keyword"},
            "doc_number": {"type": "keyword"},
            "counterparty": {"type": "text", "fields": {"kw": {"type": "keyword"}}},
            "doc_date": {"type": "date"},
            "amount": {"type": "double"},
            "cadastral_number": {"type": "keyword"},
            "real_estate_address": {"type": "text", "fields": {"kw": {"type": "keyword"}}},
            "status": {"type": "keyword"},
            "created_at": {"type": "date"},
            "embedding": {
                "type": "knn_vector",
                "dimension": settings.EMBEDDING_DIM,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "lucene",
                },
            },
        }
    },
}


def ensure_index() -> None:
    """Создаёт индекс; если схема осталась от поиска по целым документам —
    пересоздаёт. Индекс производный (источник истины — БД и хранилище),
    поэтому пересоздание безопасно; наполнение вернёт reindex_all()."""
    if _client.indices.exists(INDEX):
        try:
            meta = (_client.indices.get_mapping(index=INDEX)[INDEX]["mappings"]
                    .get("_meta", {}))
        except Exception:  # noqa: BLE001
            # Схему прочитать не удалось (кластер ещё поднимается) — это не
            # признак устаревшего индекса, и удалять его нельзя: пересборка
            # архива означает пересчёт эмбеддингов всех документов.
            log.exception("Схема индекса %s не прочитана — индекс не трогаю", INDEX)
            return
        if meta == _INDEX_META:
            return
        log.warning("Индекс %s устарел (%s) — пересоздаю под %s",
                    INDEX, meta or "схема без версии", _INDEX_META)
        _client.indices.delete(INDEX)
    _client.indices.create(INDEX, body=_MAPPING)


def _meta(doc: dict) -> dict:
    """Метаданные карточки дублируются в каждом чанке: по ним работают фильтры
    и точный поиск по реквизитам."""
    return {
        "doc_id": doc["id"],
        "department_id": doc.get("department_id") or "",
        "title": doc.get("title", ""),
        "description": doc.get("description", ""),
        "fond": doc.get("fond", ""),
        "opis": doc.get("opis", ""),
        "delo": doc.get("delo", ""),
        "doc_type": doc.get("doc_type", ""),
        "doc_number": doc.get("doc_number", ""),
        "counterparty": doc.get("counterparty", ""),
        "doc_date": doc.get("doc_date") or None,
        "amount": doc.get("amount"),
        "cadastral_number": doc.get("cadastral_number", ""),
        "real_estate_address": doc.get("real_estate_address", ""),
        "status": doc.get("status", ""),
        "created_at": doc.get("created_at"),
    }


def index_document(doc: dict) -> None:
    """Переиндексирует документ: старые чанки удаляются, новые создаются."""
    delete_document(doc["id"])
    chunks = chunking.build(doc)
    if not chunks:
        return
    meta = _meta(doc)
    # Эмбеддинги считаем одним батчем: на деле из сотен чанков вызов модели
    # на каждый чанк по отдельности занимает кратно больше времени.
    vectors = embeddings.embed_passages([c["embed_text"] for c in chunks])
    actions = []
    for chunk, vec in zip(chunks, vectors):
        body = dict(meta)
        body["chunk_no"] = chunk["chunk_no"]
        body["page_no"] = chunk.get("page_no", 1)
        body["chunk_text"] = chunk["text"]
        if vec is not None:
            body["embedding"] = vec
        actions.append({
            "_index": INDEX,
            "_id": f"{doc['id']}#{chunk['chunk_no']}",
            "_source": body,
        })
    helpers.bulk(_client, actions, refresh=True)


def delete_document(doc_id: str) -> None:
    try:
        _client.delete_by_query(
            index=INDEX,
            body={"query": {"term": {"doc_id": doc_id}}},
            refresh=True,
            conflicts="proceed",
        )
    except Exception:  # noqa: BLE001
        pass


def reindex_all(docs: list[dict]) -> int:
    """Полная переиндексация (после смены схемы или модели эмбеддингов)."""
    ensure_index()
    n = 0
    for doc in docs:
        try:
            index_document(doc)
            n += 1
        except Exception:  # noqa: BLE001
            log.exception("Не удалось проиндексировать документ %s", doc.get("id"))
    log.info("Переиндексировано документов: %d", n)
    return n


def ping() -> bool:
    """Доступен ли поисковый кластер (для пробы готовности сервиса)."""
    try:
        return bool(_client.ping())
    except Exception:  # noqa: BLE001
        return False


def indexed_doc_ids() -> set[str] | None:
    """Документы, представленные в индексе хотя бы одним чанком.

    Нужно именно множество, а не счётчик: проверка «индекс не пуст» считала
    здоровым и наполовину собранный индекс — если индексация оборвалась
    (например, процесс убит по памяти на длинном документе), недостающие
    документы молча оставались ненаходимыми.

    None — состав выяснить не удалось (OpenSearch недоступен, агрегация
    оборвалась). Это не то же самое, что «в индексе ничего нет»: вернув в таком
    случае пустое множество, вызывающий код счёл бы ненайденными вообще все
    документы и запускал бы полную переиндексацию архива при каждом старте."""
    ids: set[str] = set()
    try:
        after = None
        while True:
            src = {"size": 1000, "sources": [{"d": {"terms": {"field": "doc_id"}}}]}
            if after:
                src["after"] = after
            body = {"size": 0, "aggs": {"docs": {"composite": src}}}
            agg = _client.search(index=INDEX, body=body)["aggregations"]["docs"]
            buckets = agg.get("buckets", [])
            if not buckets:
                break
            ids.update(b["key"]["d"] for b in buckets)
            after = agg.get("after_key")
            if not after:
                break
    except Exception:  # noqa: BLE001
        log.exception("Не удалось получить состав индекса")
        return None
    return ids


def _rrf(rankings: list[list[str]]) -> dict[str, float]:
    """Reciprocal Rank Fusion: вклад источника определяется местом в его выдаче,
    а не сырым score. BM25 и косинусная близость живут в разных шкалах, и
    нормализация min-max неустойчива — на однородной выдаче она растягивает шум
    до единицы. RRF от абсолютных значений не зависит вовсе."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, _id in enumerate(ranking, start=1):
            scores[_id] = scores.get(_id, 0.0) + 1.0 / (RRF_K + rank)
    return scores


# Логические операторы расширенного поиска (ТЗ АГП п. 8: «расширенный поиск с
# использованием логических операторов и условий»). Операторами считаются только
# слова ЗАГЛАВНЫМИ буквами: строчные «и»/«не» — обычные слова запроса.
_OPERATORS = re.compile(
    r'"|(^|\s)(ИЛИ|OR|И|AND)(\s|$)|(^|\s)(НЕ|NOT)\s|(^|\s)[-+]\S|\s\|\s'
)
# Поля свободного текста: основное поле — по основам слов (русская морфология),
# подполе .std — по исходным токенам.
_TEXT_FIELDS = ["title^3", "title.std^2", "description^2", "description.std",
                "chunk_text", "chunk_text.std", "real_estate_address^2"]


def has_operators(query: str) -> bool:
    return bool(_OPERATORS.search(query or ""))


def to_simple_syntax(query: str) -> str:
    """Переводит операторы пользователя в синтаксис simple_query_string:
    И → +, ИЛИ → |, НЕ → -, фраза в кавычках остаётся фразой."""
    q = re.sub(r"\s+(ИЛИ|OR)\s+", " | ", query)
    q = re.sub(r"\s+(И|AND)\s+", " + ", q)
    q = re.sub(r"(^|\s+)(НЕ|NOT)\s+", r"\1-", q)
    return q.strip()


def _restrict(body: dict, allowed_types: list[str] | None) -> dict:
    """Ограничение выдачи типами документов, доступными роли (ТЗ АГП п. 8:
    доступ в зависимости от категорий и типов документов). None — без
    ограничений; пустой список означает, что роли не открыт ни один тип.

    post_filter, а не условие в самом запросе: он применяется одинаково и к
    лексическому, и к векторному поиску, где фильтр внутри knn поддерживается
    не всеми движками индекса.
    """
    if allowed_types is None:
        return body
    body["post_filter"] = {"terms": {"doc_type": allowed_types}}
    return body


def _lexical(query: str, size: int, allowed_types: list[str] | None = None,
             operators: bool = True) -> list[dict]:
    if operators and has_operators(query):
        # Запрос с операторами выполняется строго по логике пользователя: без
        # параллельного поиска по идентификаторам, который вернул бы документы,
        # исключённые оператором НЕ.
        bool_query = {"must": [{"simple_query_string": {
            "query": to_simple_syntax(query),
            "fields": _TEXT_FIELDS,
            "default_operator": "and",
        }}]}
    else:
        # Идентификаторы (кадастровый номер, номер документа, фонд/опись/дело)
        # ищутся ТОЧНО: цифровой код вроде «21:312:001:0157» при нечётком поиске
        # совпал бы с номерами платёжек и обыграл точное совпадение.
        bool_query = {"should": [
            {"multi_match": {
                "query": query,
                "fields": _TEXT_FIELDS,
                "type": "best_fields",
                "fuzziness": "AUTO",
            }},
            {"multi_match": {
                "query": query,
                "fields": ["fond^2", "opis^2", "delo^2",
                           "doc_number^3", "cadastral_number^4"],
                "type": "best_fields",
                "fuzziness": 0,
            }},
        ]}
    body = {
        "size": size,
        "query": {"bool": bool_query},
        "highlight": {
            "encoder": "html",  # экранируем содержимое, оставляя только <em>
            "fields": {"chunk_text": {}, "description": {}},
        },
    }
    return _client.search(index=INDEX, body=_restrict(body, allowed_types))["hits"]["hits"]


def similar_doc_ids(text: str, exclude_id: str = "", size: int = 5) -> list[str]:
    """Документы, похожие по тексту, — кандидаты на дубль (ТЗ АГП п. 12.5).

    more_like_this отбирает по характерным словам документа: сравнивать текст
    со всем архивом нельзя (миллион страниц), а повторный скан того же листа
    по определению находится поиском по собственному тексту.
    """
    body = (text or "").strip()
    if len(body) < 200:
        # Слишком короткий текст даёт совпадения по шаблонным фразам, а не по
        # содержанию: сходство по нему всё равно не будет достоверным.
        return []
    query = {
        "more_like_this": {
            "fields": ["chunk_text"],
            "like": body[:5000],
            "min_term_freq": 1,
            "min_doc_freq": 1,
            "minimum_should_match": "30%",
        }
    }
    if exclude_id:
        query = {"bool": {"must": [query],
                          "must_not": [{"term": {"doc_id": exclude_id}}]}}
    try:
        hits = _client.search(index=INDEX, body={
            "size": size * MAX_CHUNKS_PER_DOC,
            "query": query,
            "_source": ["doc_id"],
        })["hits"]["hits"]
    except Exception:  # noqa: BLE001
        log.exception("Поиск похожих документов не выполнен")
        return []
    out: list[str] = []
    for h in hits:
        did = h["_source"].get("doc_id")
        if did and did != exclude_id and did not in out:
            out.append(did)
    return out[:size]


def _semantic(query: str, size: int, allowed_types: list[str] | None = None) -> list[dict]:
    vec = embeddings.embed_query(query)
    if vec is None:
        return []
    body = {"size": size, "query": {"knn": {"embedding": {"vector": vec, "k": size}}}}
    return _client.search(index=INDEX, body=_restrict(body, allowed_types))["hits"]["hits"]


def search(query: str, mode: str = "hybrid", size: int = 20,
           allowed_types: list[str] | None = None,
           operators: bool = True) -> list[dict]:
    """mode: keyword | semantic | hybrid. Возвращает документы (не чанки),
    в каждом — наиболее релевантные фрагменты его текста.

    allowed_types — виды документов, открытые роли пользователя (None — все).
    operators — разбирать ли логические операторы. Вопрос ассистенту — фраза
    на естественном языке: кавычки в «ТОО "Альфа"» не делают её булевым
    запросом, где обязательным стало бы каждое слово вопроса."""
    # Запрос с логическими операторами — это явное требование точной логики:
    # смысловой поиск операторов не понимает и вернул бы документы, которые
    # пользователь исключил через НЕ.
    if operators and has_operators(query):
        mode = "keyword"
    candidates = max(size * CANDIDATE_FACTOR, MIN_CANDIDATES)
    hits: dict[str, dict] = {}
    rankings: list[list[str]] = []

    if allowed_types is not None and not allowed_types:
        return []

    if mode in ("keyword", "hybrid"):
        lex = _lexical(query, candidates, allowed_types, operators)
        rankings.append([h["_id"] for h in lex])
        for h in lex:
            hits[h["_id"]] = h

    if mode in ("semantic", "hybrid"):
        sem = _semantic(query, candidates, allowed_types)
        rankings.append([h["_id"] for h in sem])
        for h in sem:
            hits.setdefault(h["_id"], h)

    fused = _rrf(rankings)
    if not fused:
        return []

    ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)

    # Переранжирование кросс-энкодером. RRF учитывает только ранг и теряет
    # величину совпадения: документ, уверенно выигравший лексический поиск,
    # проигрывал середнякам, попавшим в обе выдачи. Кросс-энкодер оценивает
    # пару «запрос + фрагмент» целиком и такие случаи исправляет.
    if mode != "keyword" and reranker.available():
        head = ranked[: settings.RERANK_CANDIDATES]
        passages = [(hits[c]["_source"].get("chunk_text") or "") for c, _ in head]
        scores = reranker.rerank(query, passages)
        if scores is not None:
            reordered = [head[i][0] for i in
                         sorted(range(len(head)), key=lambda i: -scores[i])]
            n = max(len(reordered), 1)
            # Оценки кросс-энкодера живут в своей шкале, несравнимой с RRF,
            # поэтому переводим обе части в общий диапазон: переранжированные
            # кандидаты занимают [0.5, 1.0], непроверенный хвост — ниже 0.5,
            # сохраняя между собой исходный порядок RRF.
            head_scored = [(cid, 1.0 - 0.5 * i / n) for i, cid in enumerate(reordered)]
            tail = ranked[settings.RERANK_CANDIDATES:]
            tail_scored = [(cid, 0.5 * (len(tail) - i) / (len(tail) + 1))
                           for i, (cid, _) in enumerate(tail)]
            ranked = head_scored + tail_scored

    # Чанки схлопываем в документы: пользователю нужен документ, но с теми
    # фрагментами, которые действительно относятся к вопросу.
    docs: dict[str, dict] = {}
    for chunk_id, score in ranked:
        hit = hits.get(chunk_id)
        if hit is None:
            continue
        src = hit["_source"]
        doc_id = src.get("doc_id") or chunk_id.split("#")[0]
        entry = docs.get(doc_id)
        if entry is None:
            if len(docs) >= size and doc_id not in docs:
                continue
            hl = ""
            if "highlight" in hit:
                frags = []
                for v in hit["highlight"].values():
                    frags.extend(v)
                hl = " … ".join(frags[:2])
            docs[doc_id] = {
                "id": doc_id,
                "title": src.get("title", ""),
                "fond": src.get("fond", ""),
                "opis": src.get("opis", ""),
                "delo": src.get("delo", ""),
                "doc_type": src.get("doc_type", ""),
                "status": src.get("status", ""),
                "score": round(float(score), 5),
                "highlight": hl,
                "chunks": [_fragment(src)],
            }
        elif len(entry["chunks"]) < MAX_CHUNKS_PER_DOC:
            entry["chunks"].append(_fragment(src))
            if not entry["highlight"] and "highlight" in hit:
                frags = []
                for v in hit["highlight"].values():
                    frags.extend(v)
                entry["highlight"] = " … ".join(frags[:2])

    out = sorted(docs.values(), key=lambda d: d["score"], reverse=True)[:size]
    for d in out:
        # Фрагменты идут в порядке убывания релевантности — так модель читает
        # сначала самое существенное. Каждый помнит свою страницу: по ним
        # строится ссылка «документ, страница, фрагмент» в ответе ассистента.
        d["fragments"] = [c for c in d.pop("chunks") if c["text"]]
        d["chunk_text"] = "\n…\n".join(c["text"] for c in d["fragments"])
        d["pages"] = sorted({c["page_no"] for c in d["fragments"]})
    return out


def _fragment(src: dict) -> dict:
    return {"page_no": int(src.get("page_no") or 1), "text": src.get("chunk_text", "")}
