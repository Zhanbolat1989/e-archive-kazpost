"""Переранжирование результатов поиска кросс-энкодером.

Зачем нужен отдельный этап. Векторный поиск и BM25 оценивают запрос и документ
по отдельности (bi-encoder): вектор документа посчитан заранее и о запросе
ничего не знает. Кросс-энкодер читает пару «запрос + фрагмент» вместе и потому
различает случаи, где первые два этапа ошибаются, — например, отличает сам
договор аренды от платёжного поручения по этой аренде, где те же слова и суммы.

Схема стандартная для промышленного RAG: широкая выборка кандидатов (лексика +
смысл) → переранжирование → узкий контекст для модели.

Модель мультиязычная (jina-reranker-v2), работает на CPU: видеопамять занята
Ollama, а на 15–20 фрагментах CPU-инференс укладывается в пару секунд.
"""
import logging
import threading

from ..config import settings

log = logging.getLogger("reranker")

_model = None
_lock = threading.Lock()
_failed = False


def available() -> bool:
    return settings.RERANK_ENABLED and not _failed


def _get():
    """Ленивая потокобезопасная инициализация: первая загрузка скачивает веса."""
    global _model, _failed
    if _model is not None or _failed:
        return _model
    with _lock:
        if _model is None and not _failed:
            try:
                from fastembed.rerank.cross_encoder import TextCrossEncoder

                _model = TextCrossEncoder(model_name=settings.RERANK_MODEL)
                log.info("Реранкер загружен: %s", settings.RERANK_MODEL)
            except Exception:  # noqa: BLE001
                # Без реранкера поиск остаётся рабочим, просто менее точным, —
                # ронять запросы из-за необязательного этапа нельзя.
                _failed = True
                log.exception("Реранкер недоступен — работаю без него")
    return _model


def warmup() -> None:
    if settings.RERANK_ENABLED:
        try:
            rerank("проверка", ["проверка"])
        except Exception:  # noqa: BLE001
            log.warning("Прогрев реранкера не удался")


def rerank(query: str, passages: list[str]) -> list[float] | None:
    """Оценки релевантности для каждого фрагмента. None — если реранкер не
    поднялся: вызывающий код должен сохранить исходный порядок."""
    if not passages or not available():
        return None
    model = _get()
    if model is None:
        return None
    try:
        return [float(s) for s in model.rerank(query, passages)]
    except Exception:  # noqa: BLE001
        log.exception("Ошибка переранжирования — оставляю порядок поиска")
        return None
