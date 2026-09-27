"""Нарезка текста документа на чанки для поиска.

Зачем: один вектор на весь документ размывает смысл — у скана дела на 180
страниц 384 измерения не удержат содержание, а в контекст модели попадали
только первые символы. Чанк соразмерен вопросу пользователя, поэтому и
находится точнее, и целиком помещается в ответ.

Контекстный префикс (приём contextual retrieval, Anthropic, 2024): к каждому
чанку добавляется краткая «шапка» с реквизитами документа. Без неё чанк из
середины договора выглядит как безымянный обрывок текста и не находится по
запросу «договор с ТОО …». В отличие от оригинального приёма, где шапку
генерирует LLM, здесь она собирается из уже имеющихся структурированных
метаданных карточки — это точнее и не стоит ни одного вызова модели.
"""
import re

# ~800 символов ≈ 200–250 токенов кириллицы: чанк остаётся тематически цельным,
# и несколько чанков свободно помещаются в контекст локальной модели.
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
# Перекрытие не даёт факту потеряться, если он попал на стык чанков.

_PARA = re.compile(r"\n\s*\n")
_SENT_END = re.compile(r"(?<=[.!?…])\s+")


def _split_long(block: str, size: int) -> list[str]:
    """Слишком длинный абзац режем по границам предложений, а если и предложение
    длиннее лимита (сплошной OCR-поток без пунктуации) — по словам."""
    out: list[str] = []
    buf = ""
    for sent in _SENT_END.split(block):
        if len(sent) > size:
            if buf:
                out.append(buf)
                buf = ""
            words, line = sent.split(), ""
            for w in words:
                if len(line) + len(w) + 1 > size:
                    out.append(line)
                    line = w
                else:
                    line = f"{line} {w}".strip()
            if line:
                buf = line
            continue
        if len(buf) + len(sent) + 1 > size:
            out.append(buf)
            buf = sent
        else:
            buf = f"{buf} {sent}".strip()
    if buf:
        out.append(buf)
    return out


def split(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Режет текст по границам абзацев и предложений, а не по счётчику символов:
    разрыв посреди фразы портит и эмбеддинг, и читаемость цитаты."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    pieces: list[str] = []
    for para in _PARA.split(text):
        para = para.strip()
        if not para:
            continue
        pieces.extend(_split_long(para, size) if len(para) > size else [para])

    # Склеиваем мелкие куски до целевого размера и добавляем перекрытие.
    chunks: list[str] = []
    buf = ""
    for p in pieces:
        if buf and len(buf) + len(p) + 1 > size:
            chunks.append(buf)
            tail = buf[-overlap:] if overlap else ""
            # Перекрытие начинаем с границы слова, чтобы не рвать слово пополам.
            if tail and " " in tail:
                tail = tail[tail.index(" ") + 1:]
            buf = f"{tail} {p}".strip()
        else:
            buf = f"{buf} {p}".strip()
    if buf:
        chunks.append(buf)
    return chunks


def context_prefix(doc: dict) -> str:
    """Шапка чанка из реквизитов карточки: тип, номер, дата, контрагент, дело.
    Она индексируется вместе с текстом, поэтому чанк находится и по запросу,
    в котором названы только реквизиты, а самих слов из чанка нет."""
    bits = []
    if doc.get("title"):
        bits.append(str(doc["title"]))
    if doc.get("doc_type"):
        bits.append(str(doc["doc_type"]))
    if doc.get("doc_number"):
        bits.append(f"№ {doc['doc_number']}")
    if doc.get("doc_date"):
        bits.append(f"от {doc['doc_date']}")
    if doc.get("counterparty"):
        bits.append(str(doc["counterparty"]))
    if doc.get("cadastral_number"):
        bits.append(f"кадастровый номер {doc['cadastral_number']}")
    for key in ("fond", "opis", "delo"):
        if doc.get(key):
            bits.append(str(doc[key]))
    return " · ".join(bits)


# Разделитель страниц в распознанном тексте (form feed — как у pdftotext).
# Страница — единица ссылки в ответе ассистента, поэтому
# чанк никогда не пересекает границу страницы.
PAGE_BREAK = "\f"


def page_texts(text: str) -> list[str]:
    """Текст по страницам. Документ без разметки страниц — одна страница."""
    return (text or "").split(PAGE_BREAK)


def build(doc: dict) -> list[dict]:
    """Чанки документа: [{chunk_no, page_no, text, embed_text}].

    `text` — то, что показывается человеку и уходит в контекст модели;
    `embed_text` — то же с контекстной шапкой, идёт в эмбеддинг и в индекс.
    Разделены намеренно: шапка помогает найти чанк, но в цитате была бы шумом.
    """
    # Без strip(): form feed — пробельный символ, и strip() съел бы границы
    # пустых первых/последних страниц, сдвинув нумерацию.
    body = doc.get("ocr_text") or ""
    prefix = context_prefix(doc)
    chunks: list[dict] = []
    for page_no, page in enumerate(page_texts(body), start=1):
        for part in split(page):
            chunks.append({
                "chunk_no": len(chunks), "page_no": page_no, "text": part,
                "embed_text": f"{prefix}\n{part}" if prefix else part,
            })
    if chunks:
        return chunks
    # Документ без распознанного текста всё равно должен быть находим —
    # по описанию и реквизитам.
    desc = (doc.get("description") or "").strip()
    base = desc or prefix
    if not base:
        return []
    return [{"chunk_no": 0, "page_no": 1, "text": base,
             "embed_text": f"{prefix}\n{desc}".strip() if desc else prefix}]
