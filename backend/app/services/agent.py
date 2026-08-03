"""Archive AI agent: a tool-calling loop over the local LLM (Ollama).

The model decides when to search the archive and when to read a specific
document's full text, then answers grounded in what it read. Runs fully locally.
"""
import json
import logging
import re
from collections import Counter, defaultdict
from datetime import date

from sqlalchemy import extract
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Document, DocStatus, DocType
from . import llm
from . import search as search_svc

log = logging.getLogger("agent")

MAX_STEPS = 5

_DOC_TYPES_HINT = ", ".join(dt.value for dt in DocType)

SYSTEM_PROMPT = (
    "Ты — ИИ-агент электронного архива Республики Казахстан. Ты отвечаешь на вопросы "
    "по документам: как по их СОДЕРЖИМОМУ, так и по МЕТАДАННЫМ "
    "(тип, контрагент, дата, сумма, номер).\n\n"
    "Инструменты:\n"
    "• search_archive(query) — семантический поиск по смыслу/содержимому документов;\n"
    "• filter_documents(doc_type, counterparty, year, min_amount, max_amount) — "
    "выборка по метаданным (например: все счета-фактуры за 2023 год, договоры с "
    f"контрагентом X, документы на сумму свыше N). Типы: {_DOC_TYPES_HINT};\n"
    "• read_document(document_id) — прочитать полный текст документа.\n\n"
    "АЛГОРИТМ:\n"
    "1. Вопрос про содержание («что указано в…», «какие условия…») → search_archive, "
    "затем при необходимости read_document.\n"
    "2. Вопрос про выборку/перечень/суммы/даты/контрагентов/типы → filter_documents.\n"
    "3. Отвечай на основе полученных данных; не добавляй факты из общих знаний. "
    "Если ответ есть в данных — обязательно дай его.\n"
    "4. Пиши «В архиве нет информации по этому вопросу.» ТОЛЬКО если данных "
    "действительно нет.\n"
    "5. Указывай названия документов-источников. Отвечай на языке вопроса."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_archive",
            "description": "Поиск релевантных документов по смыслу/содержимому. "
            "Возвращает id, название и фрагмент текста.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Поисковый запрос на естественном языке",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "filter_documents",
            "description": "Выборка документов по метаданным (тип, контрагент, год, "
            "диапазон суммы). Используй для перечней, подсчётов, вопросов про суммы "
            "и даты.",
            "parameters": {
                "type": "object",
                "properties": {
                    "doc_type": {"type": "string",
                                 "description": f"Тип документа: {_DOC_TYPES_HINT}"},
                    "counterparty": {"type": "string",
                                     "description": "Название контрагента (частично)"},
                    "year": {"type": "integer", "description": "Год документа, напр. 2023"},
                    "min_amount": {"type": "number", "description": "Мин. сумма, тенге"},
                    "max_amount": {"type": "number", "description": "Макс. сумма, тенге"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_document",
            "description": "Прочитать полный распознанный текст документа по его id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "document_id": {
                        "type": "string",
                        "description": "Идентификатор документа (id из инструментов)",
                    }
                },
                "required": ["document_id"],
            },
        },
    },
]


def _source(doc: Document, score: float = 0.0) -> dict:
    return {
        "id": doc.id, "title": doc.title, "fond": doc.fond,
        "opis": doc.opis, "delo": doc.delo, "score": round(float(score), 3),
    }


def _search_archive(query: str, db: Session, surfaced: dict) -> list[dict]:
    hits = search_svc.search(query, mode="hybrid", size=settings.RAG_TOP_K)
    out = []
    for h in hits:
        doc = db.get(Document, h["id"])
        if not doc:
            continue
        surfaced.setdefault(doc.id, {"src": _source(doc, h["score"]), "read": False})
        out.append({
            "document_id": doc.id,
            "title": doc.title,
            "snippet": (doc.ocr_text or doc.description or "")[:1500],
        })
    return out


_LEGAL_FORMS = {"тоо", "ип", "ао", "оао", "зао", "пао", "ооо", "ксзи", "гу", "рг"}


def _norm(s: str) -> str:
    """Lowercase and fold ё→е so 'счет-фактура' matches 'Счёт-фактура'."""
    return (s or "").strip().lower().replace("ё", "е")


def _match_doc_type(value: str):
    value = _norm(value)
    if not value:
        return None
    for dt in DocType:
        if value in (_norm(dt.value), dt.name.lower()):
            return dt
    # loose contains match, e.g. "счет" -> "Счёт-фактура"
    for dt in DocType:
        v = _norm(dt.value)
        if value in v or v in value:
            return dt
    return None


def _alive_docs(db: Session):
    """Базовый запрос по документам архива: готовые и не уничтоженные по акту."""
    return db.query(Document).filter(
        Document.status == DocStatus.ready, Document.destroyed_at.is_(None)
    )


def _filter_documents(args: dict, db: Session, surfaced: dict) -> dict:
    q = _alive_docs(db)

    dt = _match_doc_type(args.get("doc_type"))
    if dt is not None:
        q = q.filter(Document.doc_type == dt)
    cp = (args.get("counterparty") or "").strip()
    if cp:
        # Match by significant tokens so «guillemets», legal forms (ТОО/ИП) and
        # punctuation don't break the match: "ТОО Кагаз Логистик" finds
        # "ТОО «Кагаз Логистик»".
        tokens = [t for t in re.split(r"[^\w]+", cp, flags=re.UNICODE)
                  if len(t) >= 2 and t.lower() not in _LEGAL_FORMS]
        for t in (tokens or [cp]):
            q = q.filter(Document.counterparty.ilike(f"%{t}%"))
    year = args.get("year")
    if year:
        try:
            q = q.filter(extract("year", Document.doc_date) == int(year))
        except (ValueError, TypeError):
            pass
    # A bound of 0 (or falsy) means "no limit" — applying `amount >= 0` would
    # wrongly drop documents whose amount is NULL (orders, references).
    for key, is_min in (("min_amount", True), ("max_amount", False)):
        val = args.get(key)
        try:
            v = float(val) if val is not None else 0.0
        except (ValueError, TypeError):
            continue
        if v > 0:
            q = q.filter(Document.amount >= v if is_min else Document.amount <= v)

    docs = q.order_by(Document.doc_date.desc().nullslast()).limit(25).all()
    items, total_amount = [], 0.0
    for doc in docs:
        # A filter match is a deliberate selection (like read_document), so mark
        # it read=True — otherwise _package's zero-score path shows only one chip.
        surfaced[doc.id] = {"src": _source(doc), "read": True}
        amt = float(doc.amount) if doc.amount is not None else None
        if amt:
            total_amount += amt
        items.append({
            "document_id": doc.id,
            "title": doc.title,
            "doc_type": doc.doc_type.value if doc.doc_type else "",
            "counterparty": doc.counterparty,
            "doc_date": doc.doc_date.isoformat() if doc.doc_date else None,
            "doc_number": doc.doc_number,
            "amount": amt,
            "currency": doc.currency,
        })
    return {"count": len(items), "total_amount": round(total_amount, 2), "documents": items}


def _read_document(document_id: str, db: Session, surfaced: dict) -> dict:
    doc = db.get(Document, document_id)
    if not doc:
        return {"error": "Документ не найден"}
    surfaced[doc.id] = {"src": _source(doc), "read": True}
    return {
        "document_id": doc.id,
        "title": doc.title,
        "fond": doc.fond, "opis": doc.opis, "delo": doc.delo,
        "text": (doc.ocr_text or doc.description or "")[: settings.RAG_CONTEXT_CHARS],
    }


def _parse_args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return {}


def _last_user(history: list[dict]) -> str:
    for m in reversed(history):
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


# ---- Fast path: instant, LLM-free answers for generic overview questions ----
_OVERVIEW_TRIGGERS = (
    "какие документ", "что в баз", "что в архив", "что есть в баз", "что хранит",
    "сколько документ", "сколько всего", "какие типы", "какие вид", "состав архив",
    "обзор архив", "содержимое архив", "список документ", "все документ",
    "что за документ", "какие файл", "статистик",
)
# Specific-intent markers — if present the question isn't a generic overview.
_SPECIFIC_MARKERS = (
    "договор", "счет", "счёт", "фактур", "акт", "приказ", "платеж", "платёж",
    "справк", "письм", "подписан", "эцп", "ндс", "контрагент", "сумм", "оплат",
    "услови", "пеня", "срок", "номер", " за ", " по ", " с тоо", " с ип",
)


def _quick_answer(question: str, db: Session) -> dict | None:
    """Return a deterministic archive summary for generic overview questions,
    computed directly from the DB (no LLM). Returns None to defer to the agent."""
    q = _norm(question)
    if not any(t in q for t in _OVERVIEW_TRIGGERS):
        return None
    if any(w in q for w in _SPECIFIC_MARKERS) or re.search(r"(19|20)\d{2}", q):
        return None  # specific question → let the tool-calling agent handle it

    docs = _alive_docs(db).all()
    if not docs:
        return {"answer": "В архиве пока нет обработанных документов.",
                "sources": [], "steps": []}

    by_type = Counter(d.doc_type.value for d in docs)
    total_amount = sum(float(d.amount) for d in docs if d.amount is not None)
    dates = [d.doc_date for d in docs if d.doc_date]
    period = f"{min(dates).year}–{max(dates).year}" if dates else "—"
    types_str = "; ".join(f"{t} — {n}" for t, n in by_type.most_common())
    amount_str = f"{total_amount:,.0f}".replace(",", " ")

    answer = (
        f"В архиве {len(docs)} документов.\n\n"
        f"По типам: {types_str}.\n"
        f"Период: {period} гг.\n"
        f"Суммарная стоимость (по документам с указанной суммой): {amount_str} ₸."
    )
    recent = sorted(docs, key=lambda d: d.doc_date or date.min, reverse=True)[:5]
    return {
        "answer": answer,
        "sources": [_source(d) for d in recent],
        "steps": [{"tool": "filter_documents", "input": "обзор архива",
                   "summary": f"агрегация по БД: {len(docs)} документов"}],
    }


# ---- Fast path: deterministic amount aggregation (sums, totals per counterparty) ----
def _money(x: float) -> str:
    return f"{x:,.0f}".replace(",", " ")


def _cp_tokens(cp: str) -> list[str]:
    return [t for t in re.split(r"[^\w]+", _norm(cp), flags=re.UNICODE)
            if len(t) >= 3 and t not in _LEGAL_FORMS]


def _match_counterparty(q: str, db: Session) -> str | None:
    """Find the known counterparty whose distinctive tokens appear in the question."""
    rows = db.query(Document.counterparty).filter(Document.counterparty != "").distinct().all()
    best, best_score = None, 0
    for (cp,) in rows:
        present = [t for t in _cp_tokens(cp) if t in q]
        if any(len(t) >= 5 for t in present) and len(present) > best_score:
            best, best_score = cp, len(present)
    return best


_AGG_PAYMENT = ("заплат", "оплат", "потрат", "перечислен", "обошл", "стои")
_AGG_TRIGGERS = ("на какую сумму", "общая сумма", "суммарн", "итого", "в сумме",
                 "сумма документов", "сумму документов", "сумма по", "сумму по")
_TYPE_ORDER = [DocType.payment, DocType.invoice, DocType.contract, DocType.act,
               DocType.order, DocType.reference, DocType.letter, DocType.other]


def _aggregate_answer(question: str, db: Session) -> dict | None:
    """Compute sums over matching documents (e.g. total paid to a counterparty),
    grouped by type to avoid double-counting one transaction across documents."""
    q = _norm(question)
    is_payment = "скольк" in q and any(w in q for w in _AGG_PAYMENT)
    is_total = any(t in q for t in _AGG_TRIGGERS)
    if not (is_payment or is_total):
        return None

    cp = _match_counterparty(q, db)
    global_ok = (any(w in q for w in ("всего", "итого", "суммарн", "общая сумма", "в сумме"))
                 and ("документ" in q or "архив" in q))
    if cp is None and not global_ok:
        return None  # e.g. "сколько стоит договор аренды" → defer to the agent

    query = _alive_docs(db)
    if cp:
        for t in _cp_tokens(cp):
            query = query.filter(Document.counterparty.ilike(f"%{t}%"))
    docs = query.all()
    if not docs:
        if cp:
            return {"answer": f"Документов контрагента {cp} в архиве нет — "
                              "они выбыли (уничтожены по акту) либо не поступали.",
                    "sources": [], "steps": [
                        {"tool": "filter_documents", "input": cp, "summary": "найдено: 0"}]}
        return None

    groups: dict[str, dict] = {}
    for d in docs:
        g = groups.setdefault(d.doc_type.value, {"n": 0, "sum": 0.0})
        g["n"] += 1
        if d.amount is not None:
            g["sum"] += float(d.amount)
    paid = sum(float(d.amount) for d in docs
               if d.doc_type == DocType.payment and d.amount is not None)
    contracted = sum(float(d.amount) for d in docs
                     if d.doc_type == DocType.contract and d.amount is not None)
    # counterparty values often already carry their own «guillemets»
    cp_disp = cp.strip() if cp else ""
    who = f"контрагенту {cp_disp}" if cp else "по всем документам архива"

    if is_payment:
        if paid > 0:
            head = f"Фактически оплачено {who} (по платёжным поручениям): {_money(paid)} ₸."
        elif contracted > 0:
            head = (f"Платёжных поручений{(' в адрес ' + cp) if cp else ''} в архиве не "
                    f"зафиксировано. Сумма обязательств по договорам: {_money(contracted)} ₸.")
        else:
            head = f"Документов с указанной суммой {who} не найдено."
    else:
        head = f"Документы {who}: {len(docs)} шт."

    lines = []
    for dt in _TYPE_ORDER:
        g = groups.get(dt.value)
        if g:
            amt = f" — на {_money(g['sum'])} ₸" if g["sum"] else ""
            lines.append(f"• {dt.value}: {g['n']}{amt}")

    answer = head + "\n\n" + "\n".join(lines)
    if cp and len(groups) > 1:
        real = paid if paid else contracted
        answer += ("\n\nПримечание: одна сделка отражается в нескольких документах "
                   "(договор → счёт → акт → платёж), поэтому фактическая сумма сделки — "
                   f"{_money(real)} ₸, а не сумма всех строк.")

    recent = sorted(docs, key=lambda d: d.doc_date or date.min, reverse=True)[:8]
    return {
        "answer": answer,
        "sources": [_source(d) for d in recent],
        "steps": [{"tool": "filter_documents", "input": cp or "все контрагенты",
                   "summary": f"подсчёт по {len(docs)} документам"}],
    }


def _ready_docs_with_cp(db: Session):
    return _alive_docs(db).filter(Document.counterparty != "").all()


def _paid_period_answer(question: str, db: Session) -> dict | None:
    """«Сколько всего оплачено за 2021 год» — sum of payment orders in a year."""
    q = _norm(question)
    if not ("скольк" in q and any(w in q for w in ("оплач", "заплат", "потрат"))):
        return None
    m = re.search(r"(19|20)\d{2}", q)
    if not m:
        return None  # no period → cp-based handler covers it
    year = int(m.group(0))
    cp = _match_counterparty(q, db)

    query = _alive_docs(db).filter(
        Document.doc_type == DocType.payment,
        extract("year", Document.doc_date) == year,
    )
    if cp:
        for t in _cp_tokens(cp):
            query = query.filter(Document.counterparty.ilike(f"%{t}%"))
    docs = query.order_by(Document.doc_date).all()
    who = f" контрагенту {cp}" if cp else ""
    total = sum(float(d.amount) for d in docs if d.amount is not None)

    if not docs:
        answer = f"За {year} год платёжных поручений{who} в архиве не найдено."
        return {"answer": answer, "sources": [], "steps": [
            {"tool": "filter_documents", "input": f"платежи {year}", "summary": "найдено: 0"}]}
    lines = [f"• {d.doc_number or d.title} — {d.counterparty} — "
             f"{_money(float(d.amount)) if d.amount is not None else '—'} ₸"
             f" ({d.doc_date.strftime('%d.%m.%Y') if d.doc_date else ''})" for d in docs]
    answer = (f"За {year} год оплачено{who} (платёжные поручения): {_money(total)} ₸ "
              f"— {len(docs)} платёж(ей).\n\n" + "\n".join(lines))
    return {"answer": answer, "sources": [_source(d) for d in docs],
            "steps": [{"tool": "filter_documents", "input": f"платежи {year}",
                       "summary": f"подсчёт по {len(docs)} платежам"}]}


def _top_counterparties_answer(question: str, db: Session) -> dict | None:
    """«Топ контрагентов по сумме» — ranked by contracted (deal) value."""
    q = _norm(question)
    hit = (("топ" in q and ("контрагент" in q or "поставщик" in q or "сумм" in q))
           or "крупнейш" in q
           or ("контрагент" in q and ("по сумме" in q or "больше всего" in q or "рейтинг" in q)))
    if not hit:
        return None
    docs = _ready_docs_with_cp(db)
    if not docs:
        return None
    deal, paid = defaultdict(float), defaultdict(float)
    for d in docs:
        if d.amount is None:
            continue
        if d.doc_type == DocType.contract:
            deal[d.counterparty] += float(d.amount)
        elif d.doc_type == DocType.payment:
            paid[d.counterparty] += float(d.amount)
    ranking = deal if any(deal.values()) else paid
    label = "по сумме договоров" if any(deal.values()) else "по сумме платежей"
    top = sorted(ranking.items(), key=lambda x: x[1], reverse=True)[:10]
    if not top:
        return None
    lines = [f"{i}. {cp} — {_money(v)} ₸" for i, (cp, v) in enumerate(top, 1)]
    answer = f"Топ контрагентов {label}:\n\n" + "\n".join(lines)
    return {"answer": answer, "sources": [], "steps": [
        {"tool": "filter_documents", "input": "группировка по контрагентам",
         "summary": f"ранжирование {len(top)} контрагентов"}]}


def _obligations_vs_paid_answer(question: str, db: Session) -> dict | None:
    """«Обязательства vs оплачено» — per-counterparty contracts vs payments."""
    q = _norm(question)
    hit = (("обязательств" in q and ("оплач" in q or "плач" in q or "vs" in q or "против" in q))
           or "обязательства и оплата" in q
           or ("сводк" in q and ("контрагент" in q or "оплат" in q or "обязательств" in q)))
    if not hit:
        return None
    docs = _ready_docs_with_cp(db)
    if not docs:
        return None
    contracted, paid, cps = defaultdict(float), defaultdict(float), set()
    for d in docs:
        cps.add(d.counterparty)
        if d.amount is None:
            continue
        if d.doc_type == DocType.contract:
            contracted[d.counterparty] += float(d.amount)
        elif d.doc_type == DocType.payment:
            paid[d.counterparty] += float(d.amount)
    rows = sorted(cps, key=lambda c: contracted.get(c, 0.0), reverse=True)
    lines = []
    for c in rows:
        ob, pd = contracted.get(c, 0.0), paid.get(c, 0.0)
        if ob == 0 and pd == 0:
            continue
        if ob > 0 and pd >= ob:
            status = "закрыто"
        elif pd == 0:
            status = "не оплачено"
        else:
            status = "частично"
        lines.append(f"• {c}: обязательства {_money(ob)} ₸, оплачено {_money(pd)} ₸ ({status})")
    total_ob = sum(contracted.values())
    total_paid = sum(paid.values())
    answer = ("Обязательства vs оплачено по контрагентам:\n\n" + "\n".join(lines)
              + f"\n\nИтого: обязательства {_money(total_ob)} ₸, "
                f"оплачено {_money(total_paid)} ₸.")
    return {"answer": answer, "sources": [], "steps": [
        {"tool": "filter_documents", "input": "договоры vs платёжные поручения",
         "summary": f"сводка по {len(lines)} контрагентам"}]}


def _retention_answer(question: str, db: Session) -> dict | None:
    """«Какие документы/дела истекают», «истёк срок хранения» — сводка по срокам."""
    q = _norm(question)
    if not (("срок" in q and ("хранен" in q or "истек" in q or "истёк" in q))
            or "истекает срок" in q or "истек срок" in q):
        return None
    from datetime import date as _d, timedelta as _td

    today = _d.today()
    horizon = today + _td(days=365)
    docs = (db.query(Document)
            .filter(Document.status == DocStatus.ready,
                    Document.retention_until.isnot(None),
                    Document.destroyed_at.is_(None))
            .order_by(Document.retention_until).all())
    expired = [d for d in docs if d.retention_until < today and not d.permanent]
    expiring = [d for d in docs
                if not d.permanent and today <= d.retention_until <= horizon]
    if not docs:
        return {"answer": "Сроки хранения пока не присвоены ни одному документу.",
                "sources": [], "steps": []}

    lines = []
    if expired:
        lines.append(f"Истёк срок хранения: {len(expired)} документ(ов) — "
                     "можно готовить акт о выделении к уничтожению:")
        lines += [f"• {d.title} — до {d.retention_until.strftime('%d.%m.%Y')} "
                  f"({d.retention_label})" for d in expired[:8]]
    if expiring:
        lines.append(f"\nИстекает в ближайшие 12 месяцев: {len(expiring)}:")
        lines += [f"• {d.title} — до {d.retention_until.strftime('%d.%m.%Y')}"
                  for d in expiring[:8]]
    if not expired and not expiring:
        nearest = docs[0]
        lines.append("Истёкших и истекающих в ближайший год сроков нет. "
                     f"Ближайший срок: {nearest.title} — до "
                     f"{nearest.retention_until.strftime('%d.%m.%Y')}.")
    srcs = [_source(d) for d in (expired + expiring)[:5]]
    return {"answer": "\n".join(lines), "sources": srcs,
            "steps": [{"tool": "filter_documents", "input": "сроки хранения",
                       "summary": f"истекло: {len(expired)}, истекает: {len(expiring)}"}]}


_OWNERSHIP_TYPES = (DocType.title_deed, DocType.rights_certificate, DocType.registry_extract)


def _real_estate_answer(question: str, db: Session) -> dict | None:
    """«Кто собственник объекта [кадастровый номер]», «история объекта» —
    текущий правообладатель и цепочка смены собственника по кадастровому
    номеру (правоустанавливающие/правоудостоверяющие документы)."""
    q = _norm(question)
    if not any(t in q for t in ("собственник", "правообладат", "объект недвижимост", "кадастров")):
        return None

    base = _alive_docs(db).filter(Document.cadastral_number != "")
    m = re.search(r"\d{1,3}(?::\d{1,4}){1,4}", question)
    cad = m.group(0) if m else None
    if cad:
        docs = base.filter(Document.cadastral_number == cad).order_by(
            Document.doc_date.asc().nullslast()).all()
        if not docs:
            return {"answer": f"Документов с кадастровым номером {cad} в архиве нет.",
                    "sources": [], "steps": [{"tool": "filter_documents",
                    "input": f"кадастровый номер {cad}", "summary": "найдено: 0"}]}
    else:
        # Без явного номера отвечаем только если объект в архиве один — иначе
        # неоднозначно, и вопрос лучше обработает семантический поиск.
        distinct = {d.cadastral_number for d in base.all()}
        if len(distinct) != 1:
            return None
        cad = next(iter(distinct))
        docs = base.filter(Document.cadastral_number == cad).order_by(
            Document.doc_date.asc().nullslast()).all()

    address = next((d.real_estate_address for d in docs if d.real_estate_address), "")
    owner_docs = [d for d in docs if d.doc_type in _OWNERSHIP_TYPES and d.counterparty]
    current = [d for d in owner_docs if d.superseded_at is None]
    current_doc = current[-1] if current else (owner_docs[-1] if owner_docs else None)

    lines = [f"Объект недвижимости: кадастровый номер {cad}"
             + (f", {address}" if address else "") + "."]
    if current_doc:
        lines.append(f"Текущий правообладатель: {current_doc.counterparty} "
                     f"(по документу «{current_doc.title}» от "
                     f"{current_doc.doc_date.strftime('%d.%m.%Y') if current_doc.doc_date else '—'}).")
    else:
        lines.append("Текущий правообладатель по документам архива не определён.")
    if len(owner_docs) > 1:
        lines.append("\nИстория смены собственника:")
        for d in owner_docs:
            status = "текущий" if d.superseded_at is None else f"до {d.superseded_at.strftime('%d.%m.%Y')}"
            lines.append(f"• {d.counterparty} — {d.title} ({status})")

    return {"answer": "\n".join(lines), "sources": [_source(d) for d in docs[-5:]],
            "steps": [{"tool": "filter_documents", "input": f"кадастровый номер {cad}",
                       "summary": f"найдено документов: {len(docs)}"}]}


def quick_answer(history: list[dict], db: Session) -> dict | None:
    q = _last_user(history)
    return (_real_estate_answer(q, db)
            or _retention_answer(q, db)
            or _top_counterparties_answer(q, db)
            or _obligations_vs_paid_answer(q, db)
            or _paid_period_answer(q, db)
            or _aggregate_answer(q, db)
            or _quick_answer(q, db))


def _retrieval_query(history: list[dict]) -> str:
    """Combine the last two user turns so follow-ups ('а на какой срок?') still
    retrieve the document the conversation is about."""
    users = [m.get("content", "") for m in history if m.get("role") == "user"]
    return " ".join(users[-2:]).strip()


_UNANSWERED_MARKERS = ("не найден", "нет информации", "не содержит", "не удалось",
                       "не могу", "недостаточно информации")


def _looks_unanswered(answer: str) -> bool:
    a = (answer or "").lower()
    return not a or any(m in a for m in _UNANSWERED_MARKERS)


def _rag_fallback(query: str, question: str, db: Session,
                  surfaced: dict, steps: list[dict]) -> str:
    """Deterministic retrieve-then-answer. `query` seeds retrieval (uses dialog
    context); `question` is what the model actually answers. Reliable path used
    when the tool-calling loop yields no real answer."""
    hits = search_svc.search(query, mode="hybrid", size=settings.RAG_TOP_K)
    if not any(s["tool"] == "search_archive" for s in steps):
        steps.append({"tool": "search_archive", "input": query,
                      "summary": f"поиск: {len(hits)} документов"})
    contexts = []
    for h in hits:
        doc = db.get(Document, h["id"])
        if not doc:
            continue
        text = (doc.ocr_text or doc.description or "").strip()[: settings.RAG_CONTEXT_CHARS]
        if not text:
            continue
        # Only surface docs that also enter `contexts`, so the [n] the model
        # emits (numbered over contexts) stays aligned with the source order.
        surfaced.setdefault(doc.id, {"src": _source(doc, h["score"]), "read": False})
        contexts.append({"title": doc.title, "text": text})
    if not contexts:
        return "В архиве нет информации по этому вопросу."
    return llm.answer(question, contexts)


def _run_tool_loop(history: list[dict], db: Session, surfaced: dict,
                   steps: list[dict]) -> str:
    """Autonomous tool-calling loop. Reliable only with capable models (7b+);
    for smaller models the caller falls back to seeded RAG."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    for _ in range(MAX_STEPS):
        msg = llm.chat(messages, tools=TOOLS)
        messages.append(msg)
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return (msg.get("content") or "").strip()
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name")
            args = _parse_args(fn.get("arguments"))
            if name == "search_archive":
                q = args.get("query", "")
                result = _search_archive(q, db, surfaced)
                steps.append({"tool": "search_archive", "input": q,
                              "summary": f"найдено документов: {len(result)}"})
            elif name == "filter_documents":
                result = _filter_documents(args, db, surfaced)
                crit = ", ".join(f"{k}={v}" for k, v in args.items() if v not in (None, ""))
                steps.append({"tool": "filter_documents", "input": crit or "все",
                              "summary": f"найдено: {result['count']}"})
            elif name == "read_document":
                did = args.get("document_id", "")
                result = _read_document(did, db, surfaced)
                steps.append({"tool": "read_document", "input": result.get("title", did),
                              "summary": "прочитан документ"})
            else:
                result = {"error": f"Неизвестный инструмент: {name}"}
            messages.append({"role": "tool",
                             "content": json.dumps(result, ensure_ascii=False)})
    return ""


def run(history: list[dict], db: Session) -> dict:
    """history: cleaned [{role, content}] conversation (no tool internals).
    Returns {answer, sources, steps}.

    Strategy: if enabled, try the autonomous tool loop; then ALWAYS ensure a
    reliable answer via dialog-aware retrieve-then-answer when the loop deflects
    or refuses. This keeps the assistant dependable on small local models while
    letting capable models drive the tools themselves."""
    surfaced: dict = {}
    steps: list[dict] = []
    answer = ""

    if settings.AGENT_TOOL_LOOP:
        answer = _run_tool_loop(history, db, surfaced, steps)

    if _looks_unanswered(answer) or not steps:
        answer = _rag_fallback(
            _retrieval_query(history), _last_user(history), db, surfaced, steps
        )

    return _package(answer, surfaced, steps)


def _package(answer: str, surfaced: dict, steps: list[dict]) -> dict:
    if "нет информации по этому вопросу" in answer.lower():
        return {"answer": "В архиве нет информации по этому вопросу.",
                "sources": [], "steps": steps}

    ordered = list(surfaced.values())  # insertion order == citation order [n]

    # Most precise: show exactly the documents the answer cites.
    cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer)})
    cited_sources = [ordered[n - 1]["src"] for n in cited if 1 <= n <= len(ordered)]
    if cited_sources:
        return {"answer": answer, "sources": cited_sources[:5], "steps": steps}

    # No citations: prefer documents the agent read, else relevant search hits.
    read = [v["src"] for v in ordered if v["read"]]
    if read:
        sources = read
    else:
        vals = sorted(ordered, key=lambda v: v["src"]["score"], reverse=True)
        top = vals[0]["src"]["score"] if vals else 0.0
        sources = ([v["src"] for v in vals if v["src"]["score"] >= 0.3 * top]
                   if top > 0 else [v["src"] for v in vals[:1]])
    return {"answer": answer, "sources": sources[:5], "steps": steps}
