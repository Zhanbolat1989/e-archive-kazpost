"""Контроль качества оцифровки: оценка распознавания с
перечнем документов, требующих ручной проверки, и выявление дублей при загрузке.

Решения объяснимые: у каждой отметки «требует проверки» есть причина в
человеческих словах, а у дубля — с каким документом он совпал и насколько.
"""
import re
import zlib

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Document
from .chunking import PAGE_BREAK

_WORD = re.compile(r"\w+")


def _is_garbage(token: str) -> bool:
    """Токен, который OCR не смог разобрать: без букв и цифр или состоящий
    в основном из посторонних символов («~#|», «,.;:»)."""
    alnum = sum(ch.isalnum() for ch in token)
    return alnum == 0 or (len(token) > 2 and alnum / len(token) < 0.5)


def assess(text: str, confidence: float | None, pages: int,
           truncated: bool = False) -> tuple[bool, str]:
    """Нужна ли документу ручная проверка и почему."""
    reasons: list[str] = []
    if truncated:
        reasons.append("распознаны не все страницы")
    if confidence is not None and confidence < settings.OCR_REVIEW_CONFIDENCE:
        reasons.append(f"низкая уверенность распознавания ({confidence:.0f}%)")

    page_list = (text or "").split(PAGE_BREAK)
    empty = sum(1 for p in page_list if not p.strip())
    if pages > 1 and empty:
        reasons.append(f"пустых страниц: {empty}")
    if pages and len((text or "").strip()) < 20 * pages and not empty:
        reasons.append("мало распознанного текста")

    tokens = (text or "").split()
    if len(tokens) >= 30:
        garbage = sum(1 for t in tokens if _is_garbage(t))
        if garbage / len(tokens) > 0.3:
            reasons.append(f"много нераспознанных символов ({garbage * 100 // len(tokens)}%)")
    return bool(reasons), "; ".join(reasons)


def shingles(text: str, k: int = 5) -> set[int]:
    """Отпечаток текста — множество хэшей последовательностей из k слов.
    CRC32, а не hash(): встроенный хэш строк рандомизирован между запусками."""
    words = _WORD.findall((text or "").lower())
    if len(words) < k:
        return {zlib.crc32(" ".join(words).encode())} if words else set()
    return {zlib.crc32(" ".join(words[i:i + k]).encode()) for i in range(len(words) - k + 1)}


def jaccard(a: set[int], b: set[int]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _same_chain(doc: Document, other: Document) -> bool:
    """Новая версия документа (замена при смене собственника и т.п.) почти
    совпадает с предыдущей по тексту, но дублем не является."""
    return doc.replaces_id == other.id or other.replaces_id == doc.id


def find_duplicate(db: Session, doc: Document,
                   candidate_ids: list[str]) -> tuple[str | None, float, str]:
    """(id похожего документа, сходство, вид) либо (None, 0, "").

    Вид: exact — совпадает файл; near — почти совпадает текст (повторный скан
    того же листа); similar — текст близок, но отличается (лист пересканирован
    с правкой, другая редакция). Дублем помечается только exact и near;
    similar выносится на ручную проверку, потому что машина здесь не может
    решить за архивариуса, одна это единица хранения или две.
    """
    exact = (
        db.query(Document)
        .filter(Document.checksum_sha256 == doc.checksum_sha256,
                Document.id != doc.id, Document.destroyed_at.is_(None))
        .order_by(Document.created_at.asc())
        .first()
    )
    if exact is not None and not _same_chain(doc, exact):
        return exact.id, 1.0, "exact"

    mine = shingles(doc.ocr_text)
    # Короткий текст (справка в две строки) совпадает с другими по шаблону —
    # сравнение по нему ненадёжно и давало бы ложные дубли.
    if len(mine) < 20:
        return None, 0.0, ""
    best_id, best = None, 0.0
    for cid in candidate_ids:
        if cid == doc.id:
            continue
        other = db.get(Document, cid)
        if other is None or other.destroyed_at is not None or _same_chain(doc, other):
            continue
        score = jaccard(mine, shingles(other.ocr_text))
        if score > best:
            best_id, best = other.id, score
    if best_id and best >= settings.NEAR_DUPLICATE_THRESHOLD:
        return best_id, round(best, 3), "near"
    if best_id and best >= settings.SIMILAR_REVIEW_THRESHOLD:
        return best_id, round(best, 3), "similar"
    return None, round(best, 3), ""
