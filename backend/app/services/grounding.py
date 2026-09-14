"""Проверка заземления ответа: подтверждаются ли числа из ответа документами.

Зачем именно для архива. Худший отказ архивной системы — не «документ не
найден», а уверенно названная неверная сумма или год: такой ответ выглядит
достоверным и попадает в работу. Строгая инструкция модели («отвечай только по
документам») ситуацию улучшает, но ничего не гарантирует.

Проверка намеренно детерминированная, без второй модели-судьи: она сверяет
числовые факты ответа с текстом, который был отдан модели. Числа — как раз то,
из чего состоят архивные ответы (суммы, годы, номера документов), и именно в
них ошибка дороже всего. Смысловые утверждения так не проверить, поэтому
результат — не «правда/ложь», а доля подтверждённых фактов.
"""
import re

# Числа с пробелом как разделителем тысяч («450 000») собираются в один токен,
# а «п. 4.2» — нет: группа после пробела должна быть ровно из трёх цифр.
_NUMBER = re.compile(r"\d{1,3}(?:[   ]\d{3})+|\d+")
_CITATION = re.compile(r"\[\d+\]")
_SEPARATORS = re.compile(r"[   ]")

# Короткие числа не проверяем: это пункты, нумерация списков и порядковые
# числительные, а не факты, ради которых задают вопрос.
MIN_DIGITS = 3


def _tokens(text: str) -> set[str]:
    out: set[str] = set()
    for m in _NUMBER.finditer(text or ""):
        token = _SEPARATORS.sub("", m.group(0))
        out.add(token.lstrip("0") or "0")
    return out


def facts(answer: str) -> set[str]:
    """Числовые факты ответа, подлежащие проверке."""
    text = _CITATION.sub(" ", answer or "")
    return {t for t in _tokens(text) if len(t) >= MIN_DIGITS}


def check(answer: str, contexts: list[dict], sources_count: int = 0) -> dict:
    """Сверяет ответ с переданным модели контекстом.

    Возвращает долю подтверждённых числовых фактов, список неподтверждённых и
    корректность ссылок на источники. `score is None` означает «проверять
    нечего»: в ответе нет числовых фактов, и заземление этим способом не
    оценивается — выдавать в таком случае низкую уверенность было бы неверно.
    """
    context_tokens: set[str] = set()
    for c in contexts:
        context_tokens |= _tokens(c.get("text", ""))
        context_tokens |= _tokens(c.get("title", ""))

    claimed = facts(answer)
    unsupported = sorted(t for t in claimed if t not in context_tokens)
    score = None if not claimed else (len(claimed) - len(unsupported)) / len(claimed)

    # Ссылка на несуществующий источник — признак того, что модель
    # «дописала» обоснование, которого ей не давали.
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", answer or "")}
    bad_citations = sorted(n for n in cited if n < 1 or n > max(sources_count, len(contexts)))

    return {
        "score": score,
        "checked": len(claimed),
        "unsupported": unsupported[:10],
        "bad_citations": bad_citations,
    }


def confidence(result: dict, retrieval_score: float = 0.0) -> str:
    """Итоговая уверенность в ответе: high | medium | low.

    Когда числовых фактов нет, опираемся на релевантность найденного —
    единственный доступный сигнал."""
    score = result.get("score")
    if result.get("bad_citations"):
        return "low"
    if score is None:
        return "high" if retrieval_score >= 0.6 else "medium"
    if score >= 0.999:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


WARNING = ("\n\n⚠️ Часть числовых данных в ответе не подтверждается текстом "
           "найденных документов — проверьте по оригиналу.")
