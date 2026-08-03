"""Background ingest pipeline: AV scan -> WORM store -> OCR -> semantic index
-> LLM analysis (annotation / опись)."""
import logging

from .db import SessionLocal
from .models import Document, DocStatus, DocType
from .services import antivirus, storage, ocr, search, llm, pdfa

log = logging.getLogger("ingest")


def _index_payload(doc: Document) -> dict:
    """Тело документа для OpenSearch. Единый источник правды для обоих мест
    индексации (первичного и после LLM-анализа) — чтобы новое поле нельзя было
    добавить в одно и забыть в другом."""
    return {
        "id": doc.id,
        "title": doc.title,
        "description": doc.description,
        "ocr_text": doc.ocr_text,
        "fond": doc.fond,
        "opis": doc.opis,
        "delo": doc.delo,
        "doc_type": doc.doc_type.value if doc.doc_type else "",
        "doc_number": doc.doc_number,
        "counterparty": doc.counterparty,
        "doc_date": doc.doc_date.isoformat() if doc.doc_date else None,
        "amount": float(doc.amount) if doc.amount is not None else None,
        "cadastral_number": doc.cadastral_number,
        "real_estate_address": doc.real_estate_address,
        "status": DocStatus.ready.value,
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

    # 3) OCR — БЕЗ удерживаемого соединения: распознавание идёт на внешнем
    #    VLM-сервисе и занимает минуты, connection pool столько ждать не может
    #    (та же причина, что и у LLM-анализа в конце файла).
    try:
        text = ocr.extract_text(data, content_type)
    except Exception as exc:  # noqa: BLE001
        _fail(document_id, f"Ошибка распознавания: {exc}")
        log.exception("OCR failed for %s", document_id)
        return

    # 4-5) Индексация и завершение — снова под сессией.
    _index_and_finish(document_id, text)


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

        # 2а) PDF/A-1 для документов постоянного хранения (приказ № 235)
        if doc.permanent and (doc.content_type or "").endswith("pdf"):
            doc.status_detail = "Конвертация в PDF/A-1…"
            db.commit()
            converted = pdfa.convert_to_pdfa(data)
            if converted:
                pdfa_key = doc.storage_key + ".pdfa.pdf"
                storage.put_original(pdfa_key, converted, "application/pdf")
                doc.pdfa_key = pdfa_key

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


def _index_and_finish(document_id: str, text: str) -> None:
    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if doc is None:
            return
        doc.ocr_text = text or ""

        # 4) Semantic + lexical indexing
        doc.status_detail = "Индексация для поиска…"
        db.commit()
        search.index_document(_index_payload(doc))

        # Capture primitives for the LLM step BEFORE releasing the session, so the
        # slow LLM call below holds no DB connection (avoids pool exhaustion).
        title, otext = doc.title, doc.ocr_text
        is_other = doc.doc_type == DocType.other
        dtype_value = doc.doc_type.value

        doc.status = DocStatus.ready
        doc.status_detail = "Готов"
        db.commit()
        log.info("Document %s ingested (%d chars OCR)", document_id, len(doc.ocr_text))
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        log.exception("Ingest failed for %s", document_id)
        _fail(document_id, f"Ошибка обработки: {exc}")
        return
    finally:
        db.close()

    # 5) LLM analysis (auto-classify + annotation/опись) with NO DB connection held.
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
