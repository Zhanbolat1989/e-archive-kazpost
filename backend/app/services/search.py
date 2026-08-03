"""OpenSearch index management + hybrid (lexical + semantic) search."""
from opensearchpy import OpenSearch

from ..config import settings
from . import embeddings

_client = OpenSearch(
    hosts=[{"host": settings.OPENSEARCH_HOST, "port": settings.OPENSEARCH_PORT}],
    http_compress=True,
    use_ssl=False,
    verify_certs=False,
)

INDEX = settings.OPENSEARCH_INDEX


def ensure_index() -> None:
    if _client.indices.exists(INDEX):
        return
    body = {
        "settings": {"index": {"knn": True}},
        "mappings": {
            "properties": {
                "title": {"type": "text", "fields": {"kw": {"type": "keyword"}}},
                "description": {"type": "text"},
                "ocr_text": {"type": "text"},
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
    _client.indices.create(INDEX, body=body)


def index_document(doc: dict) -> None:
    text_for_embedding = " ".join(
        filter(None, [doc.get("title", ""), doc.get("ocr_text", "")])
    )
    vec = embeddings.embed_passage(text_for_embedding)
    body = {
        "title": doc.get("title", ""),
        "description": doc.get("description", ""),
        "ocr_text": doc.get("ocr_text", ""),
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
    if vec is not None:
        body["embedding"] = vec
    _client.index(index=INDEX, id=doc["id"], body=body, refresh=True)


def delete_document(doc_id: str) -> None:
    try:
        _client.delete(index=INDEX, id=doc_id, refresh=True)
    except Exception:  # noqa: BLE001
        pass


def _normalize(scored: dict[str, float]) -> dict[str, float]:
    if not scored:
        return {}
    vals = list(scored.values())
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return {k: 1.0 for k in scored}
    return {k: (v - lo) / (hi - lo) for k, v in scored.items()}


def search(query: str, mode: str = "hybrid", size: int = 20) -> list[dict]:
    """mode: keyword | semantic | hybrid."""
    lexical: dict[str, dict] = {}
    semantic: dict[str, dict] = {}

    if mode in ("keyword", "hybrid"):
        # Идентификаторы (кадастровый номер, номер документа, фонд/опись/дело)
        # ищутся ТОЧНО, без fuzziness — иначе цифровой код вроде «21:312:001:0157»
        # нечётко совпадает с номерами платёжек и обыгрывает точное совпадение
        # в ранжировании. Свободный текст остаётся с fuzziness AUTO.
        body = {
            "size": size,
            "query": {
                "bool": {
                    "should": [
                        {"multi_match": {
                            "query": query,
                            "fields": ["title^3", "description^2", "ocr_text",
                                       "real_estate_address^2"],
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
                    ]
                }
            },
            "highlight": {
                "encoder": "html",  # escape document content, keep only <em> tags
                "fields": {"ocr_text": {}, "description": {}},
            },
        }
        for h in _client.search(index=INDEX, body=body)["hits"]["hits"]:
            lexical[h["_id"]] = h

    if mode in ("semantic", "hybrid"):
        vec = embeddings.embed_query(query)
        if vec is not None:
            body = {
                "size": size,
                "query": {"knn": {"embedding": {"vector": vec, "k": size}}},
            }
            for h in _client.search(index=INDEX, body=body)["hits"]["hits"]:
                semantic[h["_id"]] = h

    lex_norm = _normalize({k: v["_score"] for k, v in lexical.items()})
    sem_norm = _normalize({k: v["_score"] for k, v in semantic.items()})

    ids = set(lex_norm) | set(sem_norm)
    combined = []
    for _id in ids:
        source = (lexical.get(_id) or semantic.get(_id))["_source"]
        score = 0.6 * sem_norm.get(_id, 0.0) + 0.4 * lex_norm.get(_id, 0.0)
        hl = ""
        if _id in lexical and "highlight" in lexical[_id]:
            frags = []
            for v in lexical[_id]["highlight"].values():
                frags.extend(v)
            hl = " … ".join(frags[:2])
        combined.append(
            {
                "id": _id,
                "title": source.get("title", ""),
                "fond": source.get("fond", ""),
                "opis": source.get("opis", ""),
                "delo": source.get("delo", ""),
                "status": source.get("status", ""),
                "score": round(float(score), 4),
                "highlight": hl,
            }
        )
    combined.sort(key=lambda x: x["score"], reverse=True)
    return combined[:size]
