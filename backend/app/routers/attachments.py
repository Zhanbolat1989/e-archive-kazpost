"""Вложения к карточкам реестров («прикрепление электронных
файлов» к описям, актам на уничтожение, архивным запросам и номенклатуре).

Файлы хранятся там же, где оригиналы документов, но без WORM-блокировки:
вложение — рабочий материал карточки (скан подписанного акта, письмо
заявителя), его можно заменить, в отличие от принятого на хранение документа.
"""
import hashlib
import io
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    ArchiveRequest, Attachment, CommissionProtocol, DestructionAct, Inventory,
    NomenclatureItem, NtoRecord, Role, TransferAct, User,
)
from ..schemas import AttachmentOut
from ..security import get_current_user, require_roles
from ..services import audit, storage

router = APIRouter(prefix="/api/attachments", tags=["attachments"])

MAX_SIZE = 50 * 1024 * 1024

# Типы карточек, к которым можно прикрепить файл, и их модели: произвольный
# owner_type принимать нельзя — вложения повисли бы на несуществующих объектах.
OWNERS = {
    "inventory": Inventory,
    "destruction_act": DestructionAct,
    "archive_request": ArchiveRequest,
    "nomenclature": NomenclatureItem,
    # ТС-176 п. 5.3, 8.2, 10: скан подписанного протокола, акта НТО, акта передачи
    "commission_protocol": CommissionProtocol,
    "nto_record": NtoRecord,
    "transfer_act": TransferAct,
}


def _check_owner(db: Session, owner_type: str, owner_id: str) -> None:
    model = OWNERS.get(owner_type)
    if model is None:
        raise HTTPException(status_code=400,
                            detail="Тип карточки: " + ", ".join(OWNERS))
    if db.get(model, owner_id) is None:
        raise HTTPException(status_code=404, detail="Карточка не найдена")


@router.get("", response_model=list[AttachmentOut])
def list_attachments(owner_type: str, owner_id: str,
                     db: Session = Depends(get_db),
                     _: User = Depends(get_current_user)):
    return (db.query(Attachment)
            .filter(Attachment.owner_type == owner_type,
                    Attachment.owner_id == owner_id)
            .order_by(Attachment.created_at.desc()).all())


@router.post("", response_model=AttachmentOut, status_code=201)
def upload_attachment(request: Request, owner_type: str, owner_id: str,
                      file: UploadFile = File(...),
                      db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.admin, Role.archivist))):
    _check_owner(db, owner_type, owner_id)
    data = file.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Пустой файл")
    if len(data) > MAX_SIZE:
        raise HTTPException(status_code=413,
                            detail=f"Файл больше {MAX_SIZE // (1024 * 1024)} МБ")
    key = f"attachments/{owner_type}/{owner_id}/{uuid.uuid4()}/{file.filename}"
    storage.put_object(key, data, file.content_type or "application/octet-stream")
    att = Attachment(
        owner_type=owner_type, owner_id=owner_id, filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        size=len(data), storage_key=key,
        checksum_sha256=hashlib.sha256(data).hexdigest(),
        uploaded_by=user.email,
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    audit.record(db, user, "attachment.upload", owner_type, owner_id,
                 file.filename, request=request)
    return att


@router.get("/{att_id}/download")
def download_attachment(att_id: str, db: Session = Depends(get_db),
                        _: User = Depends(get_current_user)):
    att = db.get(Attachment, att_id)
    if not att:
        raise HTTPException(status_code=404, detail="Вложение не найдено")
    data = storage.get_object(att.storage_key)
    # Имя файла в заголовке — ASCII: кириллица ломает HTTP-заголовок.
    safe = "".join(c for c in att.filename if c.isascii()) or "attachment"
    return StreamingResponse(
        io.BytesIO(data), media_type=att.content_type,
        headers={"Content-Disposition": f'attachment; filename="{safe}"'},
    )


@router.delete("/{att_id}", status_code=204)
def delete_attachment(att_id: str, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.admin, Role.archivist))):
    att = db.get(Attachment, att_id)
    if not att:
        raise HTTPException(status_code=404, detail="Вложение не найдено")
    # Запись снимаем всегда, объект в хранилище удаляем следом: осиротевший
    # объект безвреден, а «неудаляемое» вложение в карточке — нет.
    db.delete(att)
    db.commit()
    storage.delete_object(att.storage_key)
    audit.record(db, user, "attachment.delete", att.owner_type, att.owner_id,
                 att.filename, request=request)
