"""Клиент к baidu/Unlimited-OCR (https://github.com/baidu/Unlimited-OCR).

Модель — визуально-языковая (VLM), разворачивается отдельным сервисом через
vLLM или SGLang с OpenAI-совместимым API. Мы отправляем страницу как изображение
и получаем размеченный markdown-текст документа: в отличие от Tesseract модель
понимает структуру (таблицы, колонки, печати, рукописный текст) и не требует
указания языка — казахский/русский/английский распознаются одной моделью.
"""
import base64
import io
import json
import logging
import urllib.error
import urllib.request

from PIL import Image

from ..config import settings

log = logging.getLogger(__name__)

# Промпты, поддерживаемые моделью (см. README проекта).
PROMPT_PAGE = "<image>\ndocument parsing."


class OcrServiceError(RuntimeError):
    """Сервис распознавания недоступен или вернул ошибку."""


def available() -> bool:
    """Быстрая проверка живости сервиса — без загрузки изображений."""
    try:
        req = urllib.request.Request(settings.OCR_SERVICE_URL.rstrip("/") + "/models")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001
        return False


def _encode(img: Image.Image) -> str:
    """PNG data-URI: VLM ожидает изображение, а не текстовый слой."""
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def recognize_page(img: Image.Image) -> str:
    """Распознаёт одну страницу. Бросает OcrServiceError при недоступности."""
    payload = {
        "model": settings.OCR_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": _encode(img)}},
                    {"type": "text", "text": PROMPT_PAGE},
                ],
            }
        ],
        "max_tokens": settings.OCR_MAX_TOKENS,
        # Распознавание — детерминированная задача, температура не нужна.
        "temperature": 0.0,
    }
    req = urllib.request.Request(
        settings.OCR_SERVICE_URL.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=settings.OCR_TIMEOUT) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as exc:  # noqa: PERF203
        raise OcrServiceError(f"OCR-сервис вернул {exc.code}: {exc.reason}") from exc
    except Exception as exc:  # noqa: BLE001
        raise OcrServiceError(f"OCR-сервис недоступен: {exc}") from exc

    choices = body.get("choices") or []
    if not choices:
        raise OcrServiceError("OCR-сервис вернул пустой ответ")
    if choices[0].get("finish_reason") == "length":
        # Страница обрезана по лимиту токенов: не молча — иначе неполный текст
        # попадёт в индекс и в аннотацию как полное содержимое документа.
        log.warning(
            "Страница обрезана по лимиту OCR_MAX_TOKENS=%d — текст неполный",
            settings.OCR_MAX_TOKENS,
        )
    return (choices[0].get("message", {}).get("content") or "").strip()
