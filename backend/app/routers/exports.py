"""XML-выгрузка архива и резервное копирование (п. 14.1 ТС-176)."""
import io

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Case, User, Role
from ..security import get_current_user, require_roles
from ..services import audit, storage, xmlexport

router = APIRouter(prefix="/api/export", tags=["export"])


def _xml_response(data: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(data), media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/case/{case_id}.xml")
def export_case_xml(case_id: str, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Дело не найдено")
    data = xmlexport.build(db, case)
    audit.record(db, user, "export.xml", "case", case_id,
                 f"XML-выгрузка дела {case.index}", request=request)
    # Имя файла в заголовке — только безопасные ASCII-символы: кириллица ломает
    # HTTP-заголовок, а кавычки и переводы строк (тоже ASCII) сделали бы его
    # синтаксически некорректным и запрос упал бы на уровне протокола.
    safe = "".join(
        c for c in (case.index or case_id) if c.isascii() and (c.isalnum() or c in "-_.")
    ) or "case"
    return _xml_response(data, f"case_{safe}.xml")


@router.get("/package.zip")
def export_package(request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.admin))):
    """Резервная копия архива одним пакетом: manifest.xml + файлы документов
    (резервное копирование и восстановление).

    Файлы кладутся под своими ключами хранения — теми же, что записаны в
    манифесте, поэтому пакет принимается обратно модулем импорта без правки:
    восстановление — это импорт собственной выгрузки.
    """
    import zipfile

    from ..models import Document

    docs = db.query(Document).filter(Document.destroyed_at.is_(None)).all()
    buf = io.BytesIO()
    missing: list[str] = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.xml", xmlexport.build(db))
        for doc in docs:
            try:
                zf.writestr(doc.storage_key, storage.get_object(doc.storage_key))
            except Exception:  # noqa: BLE001
                # Пропавший объект не должен обрывать выгрузку всего архива:
                # перечисляем такие документы в самом пакете.
                missing.append(f"{doc.id}\t{doc.title}\t{doc.storage_key}")
        if missing:
            zf.writestr("missing_files.txt",
                        "Файлы недоступны в хранилище:\n" + "\n".join(missing))
    audit.record(db, user, "export.package", "archive", "",
                 f"пакет архива: документов {len(docs)}, без файлов {len(missing)}",
                 request=request)
    return StreamingResponse(
        io.BytesIO(buf.getvalue()), media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="earchive_backup.zip"'},
    )


@router.get("/archive.xml")
def export_archive_xml(request: Request, db: Session = Depends(get_db),
                       user: User = Depends(require_roles(Role.admin))):
    """Полная выгрузка архива — механизм миграции и резервной копии данных
    (п. 14.1.4–14.1.5: передача данных заказчику в формате XML)."""
    data = xmlexport.build(db)
    audit.record(db, user, "export.xml", "archive", "",
                 f"полная XML-выгрузка архива ({len(data)} байт)", request=request)
    return _xml_response(data, "earchive_backup.xml")
