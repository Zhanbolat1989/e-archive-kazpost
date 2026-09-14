"""Multilingual sentence embeddings via fastembed (ONNX, no torch).

Default model: paraphrase-multilingual-MiniLM-L12-v2 (384 dims) — ru/kk/en.
The e5 family (if configured) expects "query:" / "passage:" prefixes; other
models are fed the raw text.
"""
import threading
from typing import Optional

from ..config import settings

_MAX_CHARS = 6000  # keep embedding input bounded
_IS_E5 = "e5" in settings.EMBEDDING_MODEL.lower()

# The model is initialized once. The first init downloads the ONNX weights via
# tqdm, which is NOT thread-safe — concurrent ingest tasks would race and crash
# ("tqdm has no attribute '_lock'"). Serialize init behind a lock.
_model_instance = None
_init_lock = threading.Lock()


def _model():
    global _model_instance
    if _model_instance is None:
        with _init_lock:
            if _model_instance is None:
                from fastembed import TextEmbedding

                _model_instance = TextEmbedding(model_name=settings.EMBEDDING_MODEL)
    return _model_instance


def warmup() -> None:
    """Load the model eagerly (e.g. at startup) so the first upload doesn't pay
    the download cost or race a concurrent ingest."""
    _embed("warmup", "passage: ")


def _embed(text: str, prefix: str) -> Optional[list[float]]:
    text = (text or "").strip()
    if not text:
        return None
    payload = f"{prefix}{text[:_MAX_CHARS]}" if _IS_E5 else text[:_MAX_CHARS]
    vec = next(_model().embed([payload]))
    return [float(x) for x in vec]


def embed_passage(text: str) -> Optional[list[float]]:
    return _embed(text, "passage: ")


def embed_passages(texts: list[str]) -> list[Optional[list[float]]]:
    """Кодирует список фрагментов одной прогонкой модели.

    Документ режется на чанки, и вызов embed_passage() на каждый означал бы
    сотни отдельных инференсов ONNX на одно дело — модель загружается в
    батчевом режиме и на длинных документах это разница в разы.
    Возвращает вектор на каждый вход, None — на пустые строки.
    """
    prepared: list[str] = []
    positions: list[int] = []
    for i, raw in enumerate(texts):
        text = (raw or "").strip()
        if not text:
            continue
        prepared.append(f"passage: {text[:_MAX_CHARS]}" if _IS_E5 else text[:_MAX_CHARS])
        positions.append(i)

    out: list[Optional[list[float]]] = [None] * len(texts)
    if not prepared:
        return out
    for pos, vec in zip(positions, _model().embed(prepared)):
        out[pos] = [float(x) for x in vec]
    return out


def embed_query(text: str) -> Optional[list[float]]:
    return _embed(text, "query: ")
