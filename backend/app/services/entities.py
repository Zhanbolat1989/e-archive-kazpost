"""Извлечение реквизитов из распознанного текста: даты,
регистрационные номера, организации, персоны, суммы, БИН/ИИН, географические
наименования и ссылки на другие документы.

Правила, а не языковая модель. Реквизиты архивного документа имеют устойчивую
форму, и регулярные выражения находят их точно, мгновенно и объяснимо — с точной
позицией в тексте, а значит со страницей и фрагментом, к которым ТЗ требует
привязать каждое значение. Локальная модель на миллионе страниц работала бы
часами и не давала бы позиции значения.
"""
import re
from dataclasses import dataclass

from .chunking import PAGE_BREAK

FRAGMENT_RADIUS = 70

_RU_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
_KZ_MONTHS = {
    "қаңтар": 1, "ақпан": 2, "наурыз": 3, "сәуір": 4, "мамыр": 5, "маусым": 6,
    "шілде": 7, "тамыз": 8, "қыркүйек": 9, "қазан": 10, "қараша": 11, "желтоқсан": 12,
}
_MONTHS = {**_RU_MONTHS, **_KZ_MONTHS}
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))

_UP = "А-ЯЁӘҒҚҢӨҰҮҺІ"
_LO = "а-яёәғқңөұүһі"

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("date", re.compile(rf"\b(\d{{1,2}})\s+({_MONTH_ALT})\w*\s+(\d{{4}})", re.IGNORECASE)),
    ("date", re.compile(rf"\b(\d{{4}})\s+жылғы\s+(\d{{1,2}})\s+({_MONTH_ALT})\w*", re.IGNORECASE)),
    ("date", re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b")),
    ("date", re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")),
    ("amount", re.compile(
        r"(\d{1,3}(?:[   ]\d{3})+|\d+)(?:[.,](\d{1,2}))?\s*"
        r"(тенге|тг\.?|₸|KZT|USD|долл\w*|\$|руб\w*|RUB|EUR|евро|€)", re.IGNORECASE)),
    ("bin", re.compile(r"\b(?:БИН|BIN)\s*:?\s*(\d{12})\b")),
    ("iin", re.compile(r"\b(?:ИИН|IIN|ЖСН)\s*:?\s*(\d{12})\b")),
    ("doc_ref", re.compile(
        r"\b(?:по|согласно|на основании|во исполнение|к)\s+"
        r"(договор\w*|приказ\w*|акт\w*|сч[её]т\w*|решени\w*|протокол\w*|"
        r"распоряжени\w*|письм\w*|постановлени\w*)\s+№\s*([^\s,;)]+)"
        r"(?:\s+от\s+(\d{1,2}[./]\d{1,2}[./]\d{2,4}))?", re.IGNORECASE)),
    ("reg_number", re.compile(r"№\s*([A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9\-/.]*\d[A-Za-zА-Яа-яЁё0-9\-/]*)")),
    ("organization", re.compile(
        r"\b(ТОО|АО|ИП|ОАО|ЗАО|ООО|ГУ|РГП|РГУ|ГКП|КГУ|ЖШС|АҚ|LLP|JSC)\s*[«\"“]([^»\"”\n]{2,80})[»\"”]")),
    ("person", re.compile(
        rf"\b([{_UP}][{_LO}]+)\s+([{_UP}][{_LO}]+)\s+([{_UP}][{_LO}]+(?:вич|вна|ична|ұлы|қызы|улы|кызы))\b")),
    ("person", re.compile(rf"\b([{_UP}][{_LO}]{{2,}})\s+([{_UP}])\.\s?([{_UP}])\.")),
    ("person", re.compile(rf"\b([{_UP}])\.\s?([{_UP}])\.\s?([{_UP}][{_LO}]{{2,}})\b")),
    ("geo", re.compile(
        rf"\b(г\.|город|с\.|село|пос\.|посёлок|область|обл\.|қ\.|қаласы)\s*([{_UP}][{_LO}\-]+(?:\s[{_UP}][{_LO}\-]+)?)")),
    ("geo", re.compile(
        rf"\b(ул\.|улица|пр\.|проспект|пр-т|мкр\.?|микрорайон|көш\.|даңғ\.)\s*([{_UP}0-9][^,\n]{{1,40}})")),
]


@dataclass
class Entity:
    kind: str
    value: str
    normalized: str
    page_no: int
    fragment: str


def _fragment(page: str, start: int, end: int) -> str:
    a, b = max(0, start - FRAGMENT_RADIUS), min(len(page), end + FRAGMENT_RADIUS)
    text = " ".join(page[a:b].split())
    return ("…" if a > 0 else "") + text + ("…" if b < len(page) else "")


def _iso(day: int, month: int, year: int) -> str | None:
    if year < 100:
        year += 2000 if year < 50 else 1900
    if not (1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2100):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _normalize(kind: str, m: re.Match) -> tuple[str, str] | None:
    """(значение как в тексте, нормализованное значение) или None, если
    совпадение формально похоже на реквизит, но им не является."""
    raw = " ".join(m.group(0).split())
    g = m.groups()
    if kind == "date":
        if g[1] and not g[1].isdigit():           # «11 марта 2019»
            iso = _iso(int(g[0]), _MONTHS.get(_month_key(g[1]), 0), int(g[2]))
        elif g[2] and not g[2].isdigit():         # «2019 жылғы 11 наурыз»
            iso = _iso(int(g[1]), _MONTHS.get(_month_key(g[2]), 0), int(g[0]))
        elif len(g[0]) == 4:                      # 2019-03-11
            iso = _iso(int(g[2]), int(g[1]), int(g[0]))
        else:                                     # 11.03.2019
            iso = _iso(int(g[0]), int(g[1]), int(g[2]))
        return (raw, iso) if iso else None
    if kind == "amount":
        whole = re.sub(r"[   ]", "", g[0])
        cents = (g[1] or "00").ljust(2, "0")
        cur = g[2].lower()
        code = ("KZT" if cur.startswith(("тенге", "тг", "₸", "kzt")) else
                "USD" if cur.startswith(("usd", "долл", "$")) else
                "RUB" if cur.startswith(("руб", "rub")) else "EUR")
        return raw, f"{whole}.{cents} {code}"
    if kind in ("bin", "iin"):
        return raw, g[0]
    if kind == "reg_number":
        return raw, g[0].rstrip(".")
    if kind == "organization":
        return raw, f"{g[0]} «{g[1].strip()}»"
    if kind == "person":
        return raw, " ".join(p for p in g if p)
    if kind == "geo":
        return raw, " ".join(raw.split())
    if kind == "doc_ref":
        base = f"{g[0].lower()} № {g[1]}"
        return raw, base + (f" от {g[2]}" if g[2] else "")
    return raw, raw


def _month_key(word: str) -> str:
    w = word.lower()
    for name in _MONTHS:
        if w.startswith(name[:5]) or w == name:
            return name
    return w


def extract(text: str) -> list[Entity]:
    """Реквизиты по страницам. Одно и то же значение на одной странице
    записывается один раз."""
    found: list[Entity] = []
    seen: set[tuple[str, str, int]] = set()
    for page_no, page in enumerate((text or "").split(PAGE_BREAK), start=1):
        # Номер внутри ссылки на документ («по договору № 14») — часть ссылки,
        # а не собственный номер документа; такие позиции отдельно не пишем.
        ref_spans: list[tuple[int, int]] = []
        for kind, pattern in _PATTERNS:
            for m in pattern.finditer(page):
                if kind == "reg_number" and any(a <= m.start() < b for a, b in ref_spans):
                    continue
                norm = _normalize(kind, m)
                if norm is None:
                    continue
                value, normalized = norm
                key = (kind, normalized, page_no)
                if key in seen:
                    continue
                seen.add(key)
                if kind == "doc_ref":
                    ref_spans.append((m.start(), m.end()))
                found.append(Entity(kind, value[:512], normalized[:512], page_no,
                                    _fragment(page, m.start(), m.end())))
    return found


def suggest_requisites(entities: list[Entity], own_org: str = "") -> dict:
    """Реквизиты для незаполненных полей карточки («снижение
    ручного труда по вводу метаданных»). Предлагаются только однозначные
    значения с первой страницы: дата, номер, контрагент, сумма. Уже введённые
    человеком поля вызывающий код не перезаписывает."""
    first = [e for e in entities if e.page_no == 1]
    out: dict = {}
    dates = [e.normalized for e in first if e.kind == "date"]
    if dates:
        out["doc_date"] = dates[0]
    numbers = [e.normalized for e in first if e.kind == "reg_number"]
    if numbers:
        out["doc_number"] = numbers[0]
    own = own_org.lower().strip()
    orgs = {e.normalized for e in first if e.kind == "organization"
            and not (own and own in e.normalized.lower())}
    if len(orgs) == 1:
        out["counterparty"] = next(iter(orgs))
    amounts = {e.normalized for e in entities if e.kind == "amount"}
    if len(amounts) == 1:
        value, currency = next(iter(amounts)).split()
        out["amount"] = float(value)
        out["currency"] = currency
    return out
