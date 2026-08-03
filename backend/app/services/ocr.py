"""Извлечение текста: текстовый слой PDF, если он есть, иначе распознавание
страниц движком baidu/Unlimited-OCR (VLM) с постраничным откатом на Tesseract."""
import io
import logging

from PIL import Image, ImageSequence
from pdf2image import convert_from_bytes
from pypdf import PdfReader

from ..config import settings
from . import ocr_unlimited

log = logging.getLogger(__name__)

MAX_OCR_PAGES = settings.OCR_MAX_PAGES

# Ниже этого объёма текстовый слой СТРАНИЦЫ считается «мусорным» (скан с кривым
# слоем, пустая страница, только колонтитул) — такую страницу распознаём.
_MIN_NATIVE_CHARS = 120


class OcrError(RuntimeError):
    """Распознать документ не удалось — приём должен завершиться ошибкой."""


def extract_text(data: bytes, content_type: str) -> str:
    """Бросает исключение при сбое: документ обязан получить статус «ошибка»,
    а не сохранить текст ошибки в ocr_text как содержимое."""
    ct = (content_type or "").lower()
    if ct == "application/pdf" or ct.endswith("pdf"):
        return _pdf_text(data)
    if ct.startswith("image/"):
        return _recognize(_image_pages(data))
    if ct.startswith("text/"):
        return data.decode("utf-8", errors="ignore")
    return ""


def _image_pages(data: bytes) -> list[Image.Image]:
    """Многостраничный TIFF — обычный формат сканера, читаем все кадры."""
    img = Image.open(io.BytesIO(data))
    pages = []
    for frame in ImageSequence.Iterator(img):
        pages.append(frame.copy())
        if len(pages) >= MAX_OCR_PAGES:
            break
    return pages


def _pdf_text(data: bytes) -> str:
    native = _native_pdf_pages(data)
    # Текстовый слой хорош на всех страницах — распознавание не нужно вовсе.
    if native and all(len(t) >= _MIN_NATIVE_CHARS for t in native):
        return "\n\n".join(native).strip()

    pages = convert_from_bytes(data, dpi=settings.OCR_DPI, fmt="png")[:MAX_OCR_PAGES]
    # Смешанный документ (цифровая обложка + сканы): каждую страницу решаем
    # отдельно, иначе один текстовый лист отменял бы OCR всех остальных.
    if len(native) == len(pages):
        chunks = []
        for text, page in zip(native, pages):
            chunks.append(text if len(text) >= _MIN_NATIVE_CHARS else _recognize([page]))
        return "\n\n".join(c for c in chunks if c).strip()
    return _recognize(pages)


def _native_pdf_pages(data: bytes) -> list[str]:
    """Готовый текстовый слой цифрового PDF — точнее и на порядки быстрее OCR."""
    try:
        reader = PdfReader(io.BytesIO(data))
        return [(p.extract_text() or "").strip() for p in reader.pages[:MAX_OCR_PAGES]]
    except Exception as exc:  # noqa: BLE001
        log.debug("Текстовый слой PDF не прочитан: %s", exc)
        return []


def _recognize(pages: list[Image.Image]) -> str:
    use_vlm = settings.OCR_ENGINE == "unlimited"
    if use_vlm and not ocr_unlimited.available():
        # Проверяем один раз до цикла: иначе неподнятый сервис даёт по одному
        # провалившемуся соединению на каждую страницу документа.
        if not settings.OCR_FALLBACK_TESSERACT:
            raise OcrError("Сервис Unlimited-OCR недоступен")
        log.warning("Unlimited-OCR недоступен — документ распознаётся Tesseract")
        use_vlm = False

    chunks: list[str] = []
    for num, page in enumerate(pages, 1):
        if use_vlm:
            try:
                chunks.append(ocr_unlimited.recognize_page(page))
                continue
            except ocr_unlimited.OcrServiceError as exc:
                if not settings.OCR_FALLBACK_TESSERACT:
                    raise OcrError(f"Страница {num}: {exc}") from exc
                log.warning("Страница %d: %s — откат на Tesseract", num, exc)
                # Уже распознанные страницы сохраняем; если сервис лёг совсем,
                # остальные не гоняем через него впустую.
                if not ocr_unlimited.available():
                    use_vlm = False
        chunks.append(_tesseract_page(page))
    return "\n\n".join(c for c in chunks if c).strip()


def _tesseract_page(page: Image.Image) -> str:
    # Импорт локальный: при работе на Unlimited-OCR Tesseract может отсутствовать.
    import pytesseract

    return pytesseract.image_to_string(page, lang=settings.OCR_LANGUAGES).strip()
