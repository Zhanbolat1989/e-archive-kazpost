"""Приём документа: антивирус → WORM-хранилище → распознавание → PDF/A с
текстовым слоем → контроль качества и дубли → извлечение реквизитов →
поисковый индекс → аннотация и автоклассификация моделью.

Шаги, требующие сети или процессора надолго (OCR, LLM), выполняются БЕЗ
удерживаемого соединения с БД: пул соединений не рассчитан на минуты ожидания.
"""
import logging
from datetime import date as _date

from .config import settings
from .db import SessionLocal
from .models import Document, DocStatus, DocType, ExtractedEntity, Organization
from .retention import compute_until
from .services import antivirus, storage, ocr, search, llm, pdfa, entities, quality

log = logging.getLogger("ingest")


def _index_payload(doc: Document) -> dict:
    """Тело документа для OpenSearch. Единый источник правды для всех мест
    индексации — чтобы новое поле нельзя было добавить в одно и забыть в другом."""
    return {
        "id": doc.id,
        "title": doc.title,
        "description": doc.description,
        "ocr_text": doc.ocr_text,
        "fond": doc.fond,
        "opis": doc.opis,
        "delo": doc.delo,
        "department_id": doc.department_id or "",
        "doc_type": doc.doc_type.value if doc.doc_type else "",
        "doc_number": doc.doc_number,
        "counterparty": doc.counterparty,
        "doc_date": doc.doc_date.isoformat() if doc.doc_date else None,
        "amount": float(doc.amount) if doc.amount is not None else None,
        "cadastral_number": doc.cadastral_number,
        "real_estate_address": doc.real_estate_address,
        "status": doc.status.value if doc.status else DocStatus.ready.value,
        "created_at": doc.created_at.isoformat(),
    }


def _classify(title: str, text: str) -> DocType | None:
    """Best-guess DocType from the content (used when the type is 'Прочее')."""
    raw = (llm.classify(title, text, [dt.value for dt in DocType]) or "").lower().replace("ё", "е")
    if not raw:
        return None
    for dt in DocType:
        v = dt.value.lower().replace("ё", "е")
        if v == raw or v in raw or raw in v:
            return dt
    return None


def _fail(document_id: str, detail: str) -> None:
    """Пометить документ ошибкой из отдельной короткой сессии."""
    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if doc is not None:
            doc.status = DocStatus.failed
            doc.status_detail = detail
            db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("Не удалось записать ошибку для %s", document_id)
    finally:
        db.close()


def process_document(document_id: str, data: bytes) -> None:
    # 1-2) Антивирус и WORM-хранение — под сессией БД (шаги быстрые).
    content_type = _scan_and_store(document_id, data)
    if content_type is None:
        return

    # 3) Распознавание — БЕЗ удерживаемого соединения: оно идёт минутами.
    try:
        result = ocr.extract(data, content_type)
    except Exception as exc:  # noqa: BLE001
        _fail(document_id, f"Ошибка распознавания: {exc}")
        log.exception("OCR failed for %s", document_id)
        return

    # 4) PDF/A с текстовым слоем — именно он по ТЗ является результатом
    #    оцифровки (п. 3). Ghostscript работает секундами, поэтому конвертация
    #    идёт до открытия сессии.
    pdfa_bytes = None
    # Текстового слоя может не быть (страницы распознавал VLM, страница PDF не
    # разобралась) — тогда к PDF/A приводится хотя бы оригинал PDF, как было
    # до появления слоя: документ постоянного хранения без PDF/A не остаётся.
    source = result.searchable_pdf or (data if (content_type or "").endswith("pdf") else None)
    if source and (settings.PDFA_FOR_ALL or _is_permanent(document_id)):
        pdfa_bytes = pdfa.convert_to_pdfa(source)
        if pdfa_bytes is None and result.searchable_pdf:
            # PDF/A не собрался (битые шрифты, старый ghostscript) — текстовый
            # слой всё равно ценнее отсутствия копии: по нему работает поиск.
            log.warning("Документ %s: PDF/A не сформирован, сохраняю слой как есть",
                        document_id)
            pdfa_bytes = result.searchable_pdf

    # 5) Индексация и завершение — снова под сессией.
    _index_and_finish(document_id, result, pdfa_bytes)


def _is_permanent(document_id: str) -> bool:
    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        return bool(doc and doc.permanent)
    finally:
        db.close()


def _scan_and_store(document_id: str, data: bytes) -> str | None:
    """Возвращает content_type документа либо None, если приём прерван."""
    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if doc is None:
            return None

        # 1) Antivirus (fail closed). Distinguish a real detection (infected)
        #    from the scanner being unavailable (failed — safe to retry).
        doc.status = DocStatus.scanning
        db.commit()
        try:
            clean, detail = antivirus.scan_bytes(data)
        except antivirus.ScannerUnavailable as exc:
            doc.status = DocStatus.failed
            doc.status_detail = f"Антивирус недоступен: {exc}"
            db.commit()
            log.warning("Document %s: AV unavailable: %s", document_id, exc)
            return None
        if not clean:
            doc.status = DocStatus.infected
            doc.status_detail = detail
            db.commit()
            log.warning("Document %s rejected by AV: %s", document_id, detail)
            return None

        # 2) Store original under WORM lock
        doc.status = DocStatus.processing
        doc.status_detail = "Сохранение оригинала…"
        db.commit()
        storage.put_original(doc.storage_key, data, doc.content_type)

        doc.status_detail = "Распознавание текста (OCR)…"
        content_type = doc.content_type
        db.commit()
        return content_type
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        log.exception("Ingest failed for %s", document_id)
        _fail(document_id, f"Ошибка обработки: {exc}")
        return None
    finally:
        db.close()


def _store_pdfa(doc: Document, pdfa_bytes: bytes | None) -> None:
    if not pdfa_bytes:
        return
    key = doc.storage_key + ".pdfa.pdf"
    try:
        storage.put_original(key, pdfa_bytes, "application/pdf")
        doc.pdfa_key = key
    except Exception:  # noqa: BLE001
        # Потеря PDF/A-копии не отменяет приём: оригинал уже в WORM, а копию
        # можно сформировать повторно.
        log.exception("Не удалось сохранить PDF/A для %s", doc.id)


def _save_entities(db, doc: Document) -> list:
    """Реквизиты документа: старые снимаются, новые записываются — повторная
    обработка документа не должна удваивать значения."""
    found = entities.extract(doc.ocr_text)
    db.query(ExtractedEntity).filter(ExtractedEntity.document_id == doc.id).delete()
    for e in found:
        db.add(ExtractedEntity(
            document_id=doc.id, kind=e.kind, value=e.value, normalized=e.normalized,
            page_no=e.page_no, fragment=e.fragment, source="rule",
        ))
    return found


def _fill_requisites(db, doc: Document, found: list) -> list[str]:
    """Подставляет найденные реквизиты в ПУСТЫЕ поля карточки (ТЗ АГП п. 2:
    снижение ручного труда по вводу метаданных). Введённое человеком значение
    не трогаем: машина уточняет карточку, но не спорит с архивариусом."""
    org = db.query(Organization).first()
    own = ((org.short_name or org.name) if org is not None else "")
    sugg = entities.suggest_requisites(found, own_org=own)
    filled: list[str] = []
    if not doc.doc_number and sugg.get("doc_number"):
        doc.doc_number = sugg["doc_number"][:128]
        filled.append("номер")
    if doc.doc_date is None and sugg.get("doc_date"):
        try:
            doc.doc_date = _date.fromisoformat(sugg["doc_date"])
            # При приёме срок хранения считался от года загрузки — даты
            # документа тогда не было. Теперь она известна: пересчитываем.
            doc.retention_until = compute_until(doc.doc_date.year, doc.retention_years)
            filled.append("дата")
        except ValueError:
            pass
    if not doc.counterparty and sugg.get("counterparty"):
        doc.counterparty = sugg["counterparty"][:512]
        filled.append("контрагент")
    if doc.amount is None and sugg.get("amount"):
        doc.amount = sugg["amount"]
        doc.currency = sugg.get("currency") or doc.currency
        filled.append("сумма")
    return filled


def _check_duplicate(db, doc: Document) -> str:
    """Проверка дублей при загрузке (ТЗ АГП п. 12.5). Возвращает причину для
    отметки «требует проверки» либо пустую строку.

    Кандидаты берутся из поискового индекса: сравнивать текст со всем архивом
    на миллионе страниц нельзя, а похожий документ по определению находится
    лексическим поиском по собственному тексту."""
    try:
        candidates = search.similar_doc_ids(doc.ocr_text, exclude_id=doc.id)
    except Exception:  # noqa: BLE001
        log.exception("Поиск похожих документов не выполнен для %s", doc.id)
        candidates = []
    dup_id, score, kind = quality.find_duplicate(db, doc, candidates)
    if not dup_id:
        return ""
    other = db.get(Document, dup_id)
    title = other.title if other is not None else dup_id
    if kind == "similar":
        # Не дубль: связь не проставляем, но показываем архивариусу, с чем
        # документ схож — решение о том, одна это единица хранения или две,
        # остаётся за человеком.
        return f"похож на документ «{title}» (совпадение текста {score:.0%})"
    doc.duplicate_of_id = dup_id
    if kind == "exact":
        return f"полный дубль документа «{title}» (файл совпадает побайтно)"
    return f"вероятный дубль документа «{title}» (совпадение текста {score:.0%})"


def _index_and_finish(document_id: str, result: ocr.OcrResult,
                      pdfa_bytes: bytes | None) -> None:
    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if doc is None:
            return
        doc.ocr_text = result.text or ""
        doc.page_count = result.pages or None
        doc.ocr_confidence = result.confidence
        _store_pdfa(doc, pdfa_bytes)

        # Контроль качества оцифровки и дубли (п. 12.5).
        needs_review, reason = quality.assess(
            doc.ocr_text, result.confidence, result.pages, result.truncated
        )
        dup_reason = _check_duplicate(db, doc)
        if dup_reason:
            needs_review = True
            reason = "; ".join(x for x in (dup_reason, reason) if x)
        doc.needs_review = needs_review
        doc.review_reason = reason[:512]

        # Реквизиты с привязкой к странице и фрагменту (п. 12.1).
        found = _save_entities(db, doc)
        filled = _fill_requisites(db, doc, found)

        doc.status_detail = "Индексация для поиска…"
        db.commit()
        search.index_document(_index_payload(doc))

        # Примитивы для шага LLM снимаем ДО закрытия сессии: медленный вызов
        # ниже не должен держать соединение с БД.
        title, otext = doc.title, doc.ocr_text
        is_other = doc.doc_type == DocType.other
        dtype_value = doc.doc_type.value

        doc.status = DocStatus.ready
        doc.status_detail = ("Готов" + (f" · заполнено по документу: {', '.join(filled)}"
                                        if filled else ""))
        db.commit()
        log.info("Документ %s принят: страниц %s, уверенность %s, реквизитов %d%s",
                 document_id, result.pages, result.confidence, len(found),
                 ", требует проверки" if needs_review else "")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        log.exception("Ingest failed for %s", document_id)
        _fail(document_id, f"Ошибка обработки: {exc}")
        return
    finally:
        db.close()

    # 6) LLM-анализ (автоклассификация + аннотация) без удерживаемого соединения.
    _analyze_and_save(document_id, title, otext, is_other, dtype_value)


def _analyze_and_save(document_id, title, otext, is_other, dtype_value) -> None:
    if not (otext or "").strip():
        return
    new_type = None
    annotation = ""
    try:
        if is_other:
            new_type = _classify(title, otext)
        annotation = llm.annotate(title, otext, (new_type.value if new_type else dtype_value))
    except Exception:  # noqa: BLE001
        log.warning("Analysis skipped for %s (LLM unavailable)", document_id)
        return
    if not (annotation or new_type):
        return

    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if doc is None:
            return
        if new_type is not None:
            doc.doc_type = new_type
        doc.annotation = annotation
        db.commit()
        search.index_document(_index_payload(doc))
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("Failed to save analysis for %s", document_id)
    finally:
        db.close()
