"""Модуль импорта пакетов оцифровки (ТЗ АГП п. 8) и восстановления архива (п. 9).

Пакет — ZIP с manifest.xml и файлами документов. Схема манифеста та же, что у
выгрузки (services/xmlexport), поэтому один и тот же механизм принимает и
результат работы АРМ сканирования, и собственную резервную копию архива: импорт
пакета, выгруженного системой, восстанавливает дела и документы как были.

Обработка идёт последовательно, по одному документу: партия оцифровки — это
тысячи файлов, и параллельный приём просто вытеснил бы из памяти всё остальное.
"""
import hashlib
import io
import json
import logging
import zipfile
from datetime import datetime
from xml.etree.ElementTree import fromstring

from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Case, Document, ImportJob, NomenclatureItem, User
from ..retention import compute_until

log = logging.getLogger("import")

MANIFEST_NAMES = ("manifest.xml", "Manifest.xml", "MANIFEST.XML")
MAX_ERRORS = 200

_CONTENT_TYPES = {
    "pdf": "application/pdf", "tif": "image/tiff", "tiff": "image/tiff",
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "txt": "text/plain", "xml": "application/xml",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class ImportError_(ValueError):
    """Пакет не может быть принят целиком (нет манифеста, битый ZIP)."""


def _text(el, name: str, default: str = "") -> str:
    if el is None:
        return default
    child = el.find(name)
    return (child.text or "").strip() if child is not None and child.text else default


def _guess_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _CONTENT_TYPES.get(ext, "application/octet-stream")


def _find_file(zf: zipfile.ZipFile, names: list[str]) -> str | None:
    """Путь в архиве по указанному в манифесте имени.

    Манифест может ссылаться на файл полным путём, а может — одним именем;
    разные упаковщики к тому же кладут пакет во вложенную папку. Поэтому,
    не найдя точного совпадения, ищем по базовому имени."""
    entries = {n.lower(): n for n in zf.namelist()}
    for name in names:
        if not name:
            continue
        key = name.replace("\\", "/").lstrip("./").lower()
        if key in entries:
            return entries[key]
    bases = {}
    for n in zf.namelist():
        bases.setdefault(n.rsplit("/", 1)[-1].lower(), n)
    for name in names:
        if not name:
            continue
        base = name.replace("\\", "/").rsplit("/", 1)[-1].lower()
        if base in bases:
            return bases[base]
    return None


def read_manifest(data: bytes) -> tuple[zipfile.ZipFile, object]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ImportError_("Файл не является ZIP-пакетом") from exc
    name = _find_file(zf, list(MANIFEST_NAMES))
    if name is None:
        raise ImportError_("В пакете нет manifest.xml")
    try:
        root = fromstring(zf.read(name))
    except Exception as exc:  # noqa: BLE001
        raise ImportError_(f"manifest.xml не разобран: {exc}") from exc
    return zf, root


def count_documents(root) -> int:
    return len(root.findall(".//document"))


def _ensure_case(db: Session, el, created: list[str]) -> Case | None:
    """Дело из манифеста: существующее по индексу и году либо новое."""
    index = _text(el, "index")
    year_raw = _text(el, "year")
    try:
        year = int(year_raw)
    except ValueError:
        year = datetime.utcnow().year
    title = _text(el, "title") or index or f"Дело {year}"
    volume_raw = _text(el, "volume", "1")
    volume = int(volume_raw) if volume_raw.isdigit() else 1

    existing = (db.query(Case)
                .filter(Case.index == index, Case.year == year, Case.volume == volume)
                .first()) if index else None
    if existing is not None:
        return existing

    ret = el.find("retention")
    years_raw = _text(ret, "years")
    permanent = _text(ret, "permanent").lower() == "true"
    case = Case(
        index=index or f"БН-{year}", title=title, year=year, volume=volume,
        retention_label=_text(ret, "label"),
        retention_years=int(years_raw) if years_raw.isdigit() else None,
        permanent=permanent,
    )
    case.retention_until = compute_until(year, case.retention_years)

    nom_ref = el.find("nomenclature_ref")
    if nom_ref is not None:
        nom = (db.query(NomenclatureItem)
               .filter(NomenclatureItem.index == _text(nom_ref, "index"),
                       NomenclatureItem.year == year).first())
        if nom is not None:
            case.nomenclature_id = nom.id
    db.add(case)
    # Фиксируем дело сразу, а не flush: ошибка в первом же документе делает
    # rollback, который иначе снял бы и дело — и все остальные документы этого
    # дела падали бы на внешнем ключе.
    db.commit()
    created.append(case.id)
    return case


def _document_payload(el) -> dict:
    f = el.find("file")
    ret = el.find("retention")
    re_el = el.find("real_estate")
    return {
        "title": _text(el, "title"),
        "description": _text(el, "description"),
        "doc_type": _text(el, "doc_type"),
        "doc_number": _text(el, "doc_number"),
        "doc_date": _text(el, "doc_date"),
        "counterparty": _text(el, "counterparty"),
        "amount": _text(el, "amount"),
        "currency": _text(el, "currency", "KZT"),
        "fond": _text(el, "fond"),
        "opis": _text(el, "opis"),
        "delo": _text(el, "delo"),
        "cadastral_number": _text(re_el, "cadastral_number"),
        "real_estate_address": _text(re_el, "address"),
        "real_estate_area": _text(re_el, "area"),
        "filename": _text(f, "name") or _text(f, "path") or "document.pdf",
        "paths": [_text(f, "path"), _text(f, "name"), _text(f, "storage_key")],
        "content_type": _text(f, "content_type"),
        "sha256": _text(f, "sha256"),
        # Электронная копия и результат сверки (ТС-176 п. 11.6): пакет АРМ
        # сканирования ставит pending, выгрузка архива переносит статус как есть.
        "copy_status": _text(el, "copy_status"),
        "permanent": _text(ret, "permanent").lower() == "true",
    }


def run_job(job_id: str, data: bytes, user_email: str) -> None:
    """Обрабатывает пакет целиком в фоне и заполняет отчёт о загрузке."""
    from ..ingest import process_document

    db = SessionLocal()
    errors: list[str] = []
    created_cases: list[str] = []
    documents = 0
    skipped = 0
    # (id документа, путь в пакете): байты перечитываются из ZIP при обработке —
    # копия каждого файла партии в памяти до конца разбора исчерпала бы её.
    pending: list[tuple[str, str]] = []
    try:
        job = db.get(ImportJob, job_id)
        if job is None:
            return
        # Владелец импортированных документов — тот, кто загрузил пакет:
        # карточка без владельца не создаётся (внешний ключ на пользователя).
        user = db.query(User).filter(User.email == user_email).first()
        if user is None:
            job.status = "Ошибка"
            job.errors = json.dumps(["Пользователь, начавший импорт, не найден"],
                                    ensure_ascii=False)
            job.finished_at = datetime.utcnow()
            db.commit()
            return
        try:
            zf, root = read_manifest(data)
        except ImportError_ as exc:
            job.status = "Ошибка"
            job.errors = json.dumps([str(exc)], ensure_ascii=False)
            job.finished_at = datetime.utcnow()
            db.commit()
            return

        job.total = count_documents(root)
        db.commit()

        for case_el in root.findall(".//case"):
            case = _ensure_case(db, case_el, created_cases)
            for doc_el in case_el.findall(".//document"):
                ok, err = _import_document(db, user, zf, doc_el, case, pending)
                documents += 1 if ok == "created" else 0
                skipped += 1 if ok == "duplicate" else 0
                if err and len(errors) < MAX_ERRORS:
                    errors.append(err)

        # Документы вне дел (в выгрузке архива — отдельный раздел)
        for holder in root.findall("documents_without_case"):
            for doc_el in holder.findall("document"):
                ok, err = _import_document(db, user, zf, doc_el, None, pending)
                documents += 1 if ok == "created" else 0
                skipped += 1 if ok == "duplicate" else 0
                if err and len(errors) < MAX_ERRORS:
                    errors.append(err)

        job.created_documents = documents
        job.created_cases = len(created_cases)
        job.skipped_duplicates = skipped
        job.errors = json.dumps(errors, ensure_ascii=False)
        job.status = "Загружен" if not errors else "Загружен с ошибками"
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        log.exception("Импорт %s прерван", job_id)
        try:
            job = db.get(ImportJob, job_id)
            if job is not None:
                job.status = "Ошибка"
                job.errors = json.dumps(errors + [str(exc)], ensure_ascii=False)
                db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
    finally:
        db.close()

    # Распознавание запускаем ПОСЛЕ разбора пакета и закрытия сессии: приём
    # одного документа занимает минуты, и держать на это время открытой
    # транзакцию импорта нельзя.
    for doc_id, path in pending:
        try:
            process_document(doc_id, zf.read(path))
        except Exception:  # noqa: BLE001
            log.exception("Обработка импортированного документа %s не удалась", doc_id)

    db = SessionLocal()
    try:
        job = db.get(ImportJob, job_id)
        if job is not None:
            job.finished_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def _import_document(db: Session, user: User, zf: zipfile.ZipFile, el,
                     case: Case | None, pending: list) -> tuple[str, str]:
    """('created' | 'duplicate' | 'error', сообщение об ошибке)."""
    from ..routers.documents import create_document_record

    payload = _document_payload(el)
    title = payload["title"] or payload["filename"]
    path = _find_file(zf, payload["paths"])
    if path is None:
        return "error", f"{title}: файл не найден в пакете"
    try:
        blob = zf.read(path)
    except Exception as exc:  # noqa: BLE001
        return "error", f"{title}: файл не прочитан ({exc})"

    checksum = hashlib.sha256(blob).hexdigest()
    if payload["sha256"] and payload["sha256"] != checksum:
        return "error", (f"{title}: контрольная характеристика не совпадает — "
                         "файл повреждён при передаче")
    # Повторная загрузка того же пакета не должна плодить копии: это и
    # проверка дублей (п. 12.5), и условие безопасного восстановления.
    exists = (db.query(Document)
              .filter(Document.checksum_sha256 == checksum)
              .first())
    if exists is not None:
        return "duplicate", ""

    from .ecopies import PENDING as COPY_PENDING, STATUSES as COPY_STATUSES

    # Любая отметка копии из манифеста принимается как «сверка не проводилась»:
    # подпись удостоверения в пакет не входит, и перенесённый без неё статус
    # «удостоверена» ничем бы не подтверждался — после приёма копия сверяется заново.
    copy_status = COPY_PENDING if payload["copy_status"] in COPY_STATUSES else ""
    try:
        doc = create_document_record(
            db, user,
            data=blob, filename=payload["filename"],
            content_type=payload["content_type"] or _guess_type(payload["filename"]),
            title=title, description=payload["description"],
            fond=payload["fond"], opis=payload["opis"], delo=payload["delo"],
            doc_type=payload["doc_type"], doc_number=payload["doc_number"],
            counterparty=payload["counterparty"], doc_date=payload["doc_date"],
            amount=payload["amount"], currency=payload["currency"],
            case_id=case.id if case is not None else "",
            cadastral_number=payload["cadastral_number"],
            real_estate_address=payload["real_estate_address"],
            real_estate_area=payload["real_estate_area"],
            copy_status=copy_status,
        )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return "error", f"{title}: карточка не создана ({exc})"
    pending.append((doc.id, path))
    return "created", ""
