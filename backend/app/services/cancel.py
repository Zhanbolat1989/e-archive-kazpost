"""Отмена выполняющихся запросов к ИИ-агенту.

Зачем нужна серверная часть, а не только кнопка в интерфейсе: генерация идёт на
локальной модели, и если просто оборвать соединение, Ollama продолжит считать
ответ до конца, занимая GPU. Следующий вопрос пользователя встанет в очередь за
ответом, который уже никому не нужен. Поэтому отмена доводится до генерации:
поток от Ollama обрывается, соединение закрывается, модель освобождается.

Реестр — в памяти процесса: отмена живёт секунды и переживать перезапуск не
должна. Записи с истёкшим сроком вычищаются, чтобы множество не росло.
"""
import threading
import time

# Сколько помнить отметку об отмене. Запрос, стартовавший позже этого срока,
# не должен отменяться из-за старой записи с тем же идентификатором.
TTL_SECONDS = 300

_cancelled: dict[str, float] = {}
_lock = threading.Lock()


class Cancelled(Exception):
    """Пользователь остановил генерацию."""


def _prune(now: float) -> None:
    stale = [k for k, ts in _cancelled.items() if now - ts > TTL_SECONDS]
    for k in stale:
        _cancelled.pop(k, None)


def cancel(request_id: str) -> None:
    if not request_id:
        return
    now = time.time()
    with _lock:
        _prune(now)
        _cancelled[request_id] = now


def is_cancelled(request_id: str | None) -> bool:
    if not request_id:
        return False
    with _lock:
        ts = _cancelled.get(request_id)
        return ts is not None and time.time() - ts <= TTL_SECONDS


def release(request_id: str | None) -> None:
    """Снять отметку по завершении запроса — обработка закончилась в любом
    случае, и держать идентификатор дальше незачем."""
    if not request_id:
        return
    with _lock:
        _cancelled.pop(request_id, None)


def check(request_id: str | None) -> None:
    """Бросает Cancelled, если запрос отменён. Ставится между шагами агента."""
    if is_cancelled(request_id):
        raise Cancelled()


def checker(request_id: str | None):
    """Замыкание для передачи в слой LLM: там нет доступа к идентификатору,
    но нужно уметь прерывать поток генерации."""
    return lambda: is_cancelled(request_id)
