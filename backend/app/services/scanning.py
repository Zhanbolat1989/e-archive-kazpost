"""Правила модуля «Сканирование» (ТС-176 п. 4.5) и учёта работ оцифровки.

Отделены от маршрутов: решения о том, какой скан принимать в дело и как
складывается объём оказанных услуг, проверяются тестами без базы данных.
"""
from pathlib import PurePath

from ..models import DocType, WORK_STAGES


def allowed_types(doc_types: list[str] | None) -> set[str] | None:
    """Виды документов, разрешённые статьёй номенклатуры; None — любые.

    Пустой список означает «ограничений нет», а не «ничего нельзя»: статьи,
    заведённые до появления модуля, не должны блокировать ввод сканов."""
    values = {t for t in (doc_types or []) if t}
    return values or None


def check_doc_type(doc_types: list[str] | None, doc_type: str) -> str:
    """Вид документа, допустимый для дела статьи; иначе ValueError с причиной."""
    if doc_type not in {dt.value for dt in DocType}:
        raise ValueError(f"Неизвестный вид документа: «{doc_type}»")
    allowed = allowed_types(doc_types)
    if allowed is not None and doc_type not in allowed:
        raise ValueError(
            f"Вид «{doc_type}» не предусмотрен статьёй номенклатуры. "
            "Допустимые виды: " + ", ".join(sorted(allowed))
        )
    return doc_type


def title_from_filename(filename: str) -> str:
    """Заголовок документа по имени файла скана — архивариус уточнит его при
    верификации, а пустой заголовок сделал бы карточку ненаходимой в описи."""
    stem = PurePath(filename or "").stem.replace("_", " ").strip()
    return stem or "Скан документа"


def summarize(marks: list[tuple[str, int]]) -> list[dict]:
    """Сводка объёма по этапам: (этап, страниц) по отметкам за период.

    Возвращаются все этапы в порядке ТС, в том числе без работ за период: акт
    показывает и то, что по этапу ничего не выполнялось."""
    acc = {stage: {"cases": 0, "pages": 0} for stage in WORK_STAGES}
    for stage, pages in marks:
        if stage in acc:
            acc[stage]["cases"] += 1
            acc[stage]["pages"] += int(pages or 0)
    return [{"stage": s, "label": WORK_STAGES[s], **acc[s]} for s in WORK_STAGES]
