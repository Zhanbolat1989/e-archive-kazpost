"""Информационные пакеты электронных дел для передачи в госархив
(ТС-176 п. 5.3): файлы документов, метаданные с контрольными
характеристиками, опись электронного дела и контрольный лист."""
import hashlib
import zipfile

from ..models import Case, Document
from . import forms as forms_svc
from . import storage


def add_case(zf: zipfile.ZipFile, case: Case, docs: list[Document], prefix: str = "") -> dict:
    """Кладёт в архив документы дела, опись электронного дела и контрольный лист.

    Возвращает метаданные для manifest. Файл, не прочитанный из хранилища,
    попадает в `missing` и в контрольный лист: пакет для передачи на хранение
    не должен выглядеть полным, когда он неполон.
    """
    entry = {"index": case.index, "title": case.title, "year": case.year,
             "volume": case.volume, "retention": case.retention_label,
             "documents": [], "missing": []}
    control: list[str] = []
    for idx, d in enumerate(docs, 1):
        try:
            blob = storage.get_object(d.storage_key)
        except Exception:  # noqa: BLE001
            entry["missing"].append({"id": d.id, "number": d.doc_number, "title": d.title})
            control.append(f"{d.id} {d.title}: файл не прочитан из хранилища [MISSING]")
            continue
        # Индексный префикс гарантирует уникальность имён в пакете.
        arcname = (f"{prefix}documents/{idx:03d}_"
                   f"{(d.doc_number or d.id).replace('/', '_')}_{d.original_filename}")
        zf.writestr(arcname, blob)
        actual = hashlib.sha256(blob).hexdigest()
        entry["documents"].append({
            "id": d.id, "number": d.doc_number, "title": d.title,
            "type": d.doc_type.value, "date": d.doc_date.isoformat() if d.doc_date else None,
            "file": arcname, "size": len(blob),
            "sha256_catalog": d.checksum_sha256, "sha256_actual": actual,
            "integrity": actual == d.checksum_sha256,
            "signature_status": d.signature_status.value,
            "annotation": d.annotation,
        })
        control.append(f"{arcname}: {actual} "
                       f"[{'OK' if actual == d.checksum_sha256 else 'MISMATCH'}]")
    zf.writestr(f"{prefix}control_sheet.txt",
                "Контрольный лист проверки комплектности\n" + "\n".join(control))
    try:
        zf.writestr(f"{prefix}opis.pdf", forms_svc.render_pdf("e_opis", case, docs))
    except Exception:  # noqa: BLE001
        pass
    return entry
