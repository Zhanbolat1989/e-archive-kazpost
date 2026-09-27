"""Извлечение текста: текстовый слой PDF, если он есть, иначе распознавание
страниц (Unlimited-OCR VLM с постраничным откатом на Tesseract).

Результат постраничный: страницы разделяются символом form feed, чтобы ответ
ассистента мог ссылаться на номер страницы.

Tesseract запускается через CLI с двумя форматами вывода сразу — `pdf tsv`:
за один проход распознавания получаются и слова с уверенностью (оценка
качества, п. 12.5), и страница PDF с невидимым текстовым слоем. Из таких
страниц собирается searchable PDF, который затем приводится к PDF/A (п. 3).
Второй проход ради PDF удвоил бы время обработки миллиона страниц.
"""
import io
import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageSequence
from pdf2image import convert_from_bytes
from pypdf import PdfReader, PdfWriter

from ..config import settings
from . import ocr_unlimited
from .chunking import PAGE_BREAK

log = logging.getLogger(__name__)

MAX_OCR_PAGES = settings.OCR_MAX_PAGES

# Ниже этого объёма текстовый слой СТРАНИЦЫ считается «мусорным» (скан с кривым
# слоем, пустая страница, только колонтитул) — такую страницу распознаём.
_MIN_NATIVE_CHARS = 120


class OcrError(RuntimeError):
    """Распознать документ не удалось — приём должен завершиться ошибкой."""


@dataclass
class OcrResult:
    text: str = ""
    pages: int = 0
    # Средняя уверенность распознавания по словам, 0–100. None — текст не
    # распознавался (цифровой PDF, текстовый файл), и оценивать нечего.
    confidence: float | None = None
    # PDF с текстовым слоем — основа для PDF/A. None, если собрать не удалось.
    searchable_pdf: bytes | None = None
    engine: str = ""
    # В документе больше страниц, чем распознаётся (OCR_MAX_PAGES).
    truncated: bool = False


@dataclass
class _Page:
    text: str
    confidence: float | None = None
    words: int = 0
    pdf: bytes | None = None
    engine: str = "native"


def extract(data: bytes, content_type: str) -> OcrResult:
    """Бросает исключение при сбое: документ обязан получить статус «ошибка»,
    а не сохранить текст ошибки в ocr_text как содержимое."""
    ct = (content_type or "").lower()
    if ct == "application/pdf" or ct.endswith("pdf"):
        return _pdf(data)
    if ct.startswith("image/"):
        frames, truncated = _image_pages(data)
        state: dict = {}
        pages = [_recognize_page(f, i + 1, state) for i, f in enumerate(frames)]
        return _assemble(pages, truncated)
    if ct.startswith("text/"):
        return OcrResult(text=data.decode("utf-8", errors="ignore"), pages=1, engine="text")
    return OcrResult()


def extract_text(data: bytes, content_type: str) -> str:
    """Только текст — для вызывающего кода, которому не нужны страницы."""
    return extract(data, content_type).text


def _image_pages(data: bytes) -> tuple[list[Image.Image], bool]:
    """Многостраничный TIFF — обычный формат сканера, читаем все кадры."""
    img = Image.open(io.BytesIO(data))
    pages: list[Image.Image] = []
    truncated = False
    for frame in ImageSequence.Iterator(img):
        if len(pages) >= MAX_OCR_PAGES:
            truncated = True
            break
        pages.append(frame.copy())
    return pages, truncated


def _pdf(data: bytes) -> OcrResult:
    try:
        reader = PdfReader(io.BytesIO(data))
        total = len(reader.pages)
    except Exception as exc:  # noqa: BLE001
        log.debug("PDF не прочитан pypdf: %s", exc)
        reader, total = None, 0
    if not total:
        # Повреждённый заголовок: число страниц узнаём у poppler.
        from pdf2image import pdfinfo_from_bytes

        total = int(pdfinfo_from_bytes(data).get("Pages", 0))
    limit = min(total, MAX_OCR_PAGES)
    native = [_native_page_text(reader, i) for i in range(limit)]

    # Текстовый слой хорош на всех страницах — распознавание не нужно вовсе,
    # а исходный файл уже и есть PDF с текстом.
    if native and all(len(t) >= _MIN_NATIVE_CHARS for t in native):
        result = _assemble([_Page(t) for t in native], total > limit)
        result.searchable_pdf = data
        return result

    state: dict = {}
    pages: list[_Page] = []
    for i in range(limit):
        # Смешанный документ (цифровая обложка + сканы): каждую страницу решаем
        # отдельно, иначе один текстовый лист отменял бы OCR всех остальных.
        if len(native[i]) >= _MIN_NATIVE_CHARS:
            pages.append(_Page(native[i], pdf=_single_page(reader, i)))
            continue
        # Страницы растрируются по одной: дело на 180 страниц при 200 dpi
        # целиком заняло бы в памяти около 2 ГБ.
        img = convert_from_bytes(data, dpi=settings.OCR_DPI, fmt="png",
                                 first_page=i + 1, last_page=i + 1)[0]
        pages.append(_recognize_page(img, i + 1, state))
    return _assemble(pages, total > limit)


def _native_page_text(reader, i: int) -> str:
    if reader is None:
        return ""
    try:
        return (reader.pages[i].extract_text() or "").strip()
    except Exception as exc:  # noqa: BLE001
        log.debug("Текстовый слой страницы %d не прочитан: %s", i + 1, exc)
        return ""


def _single_page(reader, i: int) -> bytes | None:
    if reader is None:
        return None
    try:
        w = PdfWriter()
        w.add_page(reader.pages[i])
        buf = io.BytesIO()
        w.write(buf)
        return buf.getvalue()
    except Exception:  # noqa: BLE001
        return None


def _recognize_page(img: Image.Image, num: int, state: dict) -> _Page:
    if "use_vlm" not in state:
        # Доступность сервиса проверяется один раз на документ, а не на каждую
        # страницу: неподнятый сервис давал бы по отказу соединения на страницу.
        use_vlm = settings.OCR_ENGINE == "unlimited"
        if use_vlm and not ocr_unlimited.available():
            if not settings.OCR_FALLBACK_TESSERACT:
                raise OcrError("Сервис Unlimited-OCR недоступен")
            log.warning("Unlimited-OCR недоступен — документ распознаётся Tesseract")
            use_vlm = False
        state["use_vlm"] = use_vlm

    if state["use_vlm"]:
        try:
            return _Page(ocr_unlimited.recognize_page(img), engine="unlimited")
        except ocr_unlimited.OcrServiceError as exc:
            if not settings.OCR_FALLBACK_TESSERACT:
                raise OcrError(f"Страница {num}: {exc}") from exc
            log.warning("Страница %d: %s — откат на Tesseract", num, exc)
            # Уже распознанные страницы сохраняем; если сервис лёг совсем,
            # остальные не гоняем через него впустую.
            if not ocr_unlimited.available():
                state["use_vlm"] = False
    return _tesseract(img)


def _tesseract(img: Image.Image) -> _Page:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "page.png"
        base = Path(tmp) / "out"
        (img if img.mode in ("RGB", "L") else img.convert("RGB")).save(src)
        cmd = ["tesseract", str(src), str(base), "-l", settings.OCR_LANGUAGES, "pdf", "tsv"]
        res = subprocess.run(cmd, capture_output=True, timeout=settings.OCR_TIMEOUT)
        if res.returncode != 0:
            raise OcrError("Tesseract завершился с ошибкой: "
                           + res.stderr.decode("utf-8", errors="ignore")[-200:])
        tsv_path, pdf_path = base.with_suffix(".tsv"), base.with_suffix(".pdf")
        tsv = tsv_path.read_text(encoding="utf-8", errors="ignore") if tsv_path.exists() else ""
        pdf = pdf_path.read_bytes() if pdf_path.exists() else None
    text, conf, words = parse_tsv(tsv)
    return _Page(text=text, confidence=conf, words=words, pdf=pdf, engine="tesseract")


def parse_tsv(tsv: str) -> tuple[str, float | None, int]:
    """Текст страницы из TSV Tesseract и средняя уверенность по словам.

    Слова собираются в строки по номерам блока/абзаца/строки, абзацы
    разделяются пустой строкой — так текст читается так же, как на странице.
    """
    rows = tsv.splitlines()
    if not rows:
        return "", None, 0
    header = rows[0].split("\t")
    try:
        col = {n: header.index(n) for n in ("block_num", "par_num", "line_num", "conf", "text")}
    except ValueError:
        return "", None, 0

    lines: list[str] = []
    current: list[str] = []
    line_key = paragraph = None
    confs: list[float] = []
    for row in rows[1:]:
        cells = row.split("\t")
        if len(cells) < len(header):
            continue
        word = cells[col["text"]].strip()
        if not word:
            continue
        try:
            conf = float(cells[col["conf"]])
        except ValueError:
            conf = -1.0
        if conf >= 0:
            confs.append(conf)
        key = (cells[col["block_num"]], cells[col["par_num"]], cells[col["line_num"]])
        if key != line_key:
            if current:
                lines.append(" ".join(current))
            if paragraph is not None and key[:2] != paragraph:
                lines.append("")
            current, line_key, paragraph = [], key, key[:2]
        current.append(word)
    if current:
        lines.append(" ".join(current))
    avg = sum(confs) / len(confs) if confs else None
    return "\n".join(lines).strip(), avg, len(confs)


def _assemble(pages: list[_Page], truncated: bool) -> OcrResult:
    scored = [p for p in pages if p.confidence is not None and p.words]
    confidence = None
    if scored:
        total_words = sum(p.words for p in scored)
        confidence = round(sum(p.confidence * p.words for p in scored) / total_words, 2)
    pdf = _merge([p.pdf for p in pages]) if pages and all(p.pdf for p in pages) else None
    engines = sorted({p.engine for p in pages}) or ["native"]
    return OcrResult(
        text=PAGE_BREAK.join(p.text for p in pages),
        pages=len(pages), confidence=confidence, searchable_pdf=pdf,
        engine="+".join(engines), truncated=truncated,
    )


def _merge(parts: list[bytes]) -> bytes | None:
    try:
        w = PdfWriter()
        for part in parts:
            for page in PdfReader(io.BytesIO(part)).pages:
                w.add_page(page)
        buf = io.BytesIO()
        w.write(buf)
        return buf.getvalue()
    except Exception as exc:  # noqa: BLE001
        log.warning("Не удалось собрать PDF с текстовым слоем: %s", exc)
        return None
