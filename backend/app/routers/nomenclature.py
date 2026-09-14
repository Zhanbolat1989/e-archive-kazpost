import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..autonumber import next_nomenclature_index
from ..db import get_db
from ..models import (
    ApprovalRequest, ApprovalStatus, Case, Department, NOMENCLATURE_STATUSES,
    NomenclatureItem, Role, User,
)
from ..schemas import NomenclatureCreate, NomenclatureOut, NomenclatureUpdate
from ..security import get_current_user, require_roles
from ..services import audit, history, xlsx

router = APIRouter(prefix="/api/nomenclature", tags=["nomenclature"])

DRAFT, ON_APPROVAL, ACTIVE, ARCHIVED = NOMENCLATURE_STATUSES
# Статью можно править, пока она не введена в действие: у действующей статьи
# меняется только статус (в архивные), иначе сроки хранения заведённых по ней
# дел разошлись бы с номенклатурой, по которой их формировали.
EDITABLE = (DRAFT, ON_APPROVAL)


@router.get("", response_model=list[NomenclatureOut])
def list_items(
    year: int | None = None,
    status: str | None = None,
    department_id: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(NomenclatureItem)
    if year:
        q = q.filter(NomenclatureItem.year == year)
    if status:
        q = q.filter(NomenclatureItem.status == status)
    if department_id:
        q = q.filter(NomenclatureItem.department_id == department_id)
    return q.order_by(NomenclatureItem.year.desc(), NomenclatureItem.index).all()


@router.get("/meta/statuses")
def statuses(_: User = Depends(get_current_user)) -> list[str]:
    return list(NOMENCLATURE_STATUSES)


@router.post("", response_model=NomenclatureOut, status_code=201)
def create_item(
    payload: NomenclatureCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.admin, Role.archivist)),
):
    data = payload.model_dump()
    if not data["index"].strip():
        data["index"] = next_nomenclature_index(db, data["year"])
    item = NomenclatureItem(**data)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/{item_id}", response_model=NomenclatureOut)
def update_item(
    item_id: str, payload: NomenclatureUpdate, request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.admin, Role.archivist)),
):
    item = db.get(NomenclatureItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Статья номенклатуры не найдена")
    changes = payload.model_dump(exclude_none=True)
    client_version = changes.pop("version", None)
    # Виды документов правятся в любом статусе: они управляют вводом сканов
    # (ТС-176 п. 4.5) и не меняют сроков хранения уже заведённых дел.
    if item.status not in EDITABLE and set(changes) - {"doc_types"}:
        raise HTTPException(
            status_code=409,
            detail=f"Статья в статусе «{item.status}» не редактируется — "
                   "заведите статью следующего года или переведите в архивные",
        )
    if client_version is not None and int(client_version) != (item.version or 1):
        raise HTTPException(status_code=409,
                            detail="Статью уже изменил другой пользователь — "
                                   "обновите её и повторите")
    before = history.snapshot(item, list(changes))
    for field, value in changes.items():
        setattr(item, field, value)
    item.version = (item.version or 1) + 1
    db.commit()
    history.record(db, user, "nomenclature", item.id, before, changes)
    audit.record(db, user, "nomenclature.update", "nomenclature", item.id,
                 ", ".join(changes.keys()), request=request)
    db.refresh(item)
    return item


@router.post("/{item_id}/status", response_model=NomenclatureOut)
def set_status(
    item_id: str, status: str, request: Request, db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.admin, Role.archivist)),
):
    """Перевод статьи по жизненному циклу: проект → на согласовании →
    действующая → архивная (ТЗ АГП п. 8)."""
    item = db.get(NomenclatureItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Статья номенклатуры не найдена")
    if status not in NOMENCLATURE_STATUSES:
        raise HTTPException(status_code=400,
                            detail="Статус: " + ", ".join(NOMENCLATURE_STATUSES))
    if status == ACTIVE and item.status in EDITABLE:
        # Ввести в действие можно только согласованную статью: смысл этапа
        # согласования в том, что его нельзя обойти одним нажатием — ни из
        # «на согласовании», ни прямо из проекта.
        approved = (db.query(ApprovalRequest)
                    .filter(ApprovalRequest.object_type == "nomenclature",
                            ApprovalRequest.object_id == item_id,
                            ApprovalRequest.status == ApprovalStatus.approved)
                    .first())
        if approved is None:
            raise HTTPException(
                status_code=409,
                detail="Статья не согласована — отправьте её на согласование "
                       "и дождитесь решения согласующих",
            )
    before = {"status": item.status}
    item.status = status
    db.commit()
    history.record(db, user, "nomenclature", item.id, before, {"status": status})
    audit.record(db, user, "nomenclature.status", "nomenclature", item.id,
                 f"{before['status']} → {status}", request=request)
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=204)
def delete_item(
    item_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.admin)),
):
    item = db.get(NomenclatureItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Статья номенклатуры не найдена")
    # По статье уже заведены дела: удаление оставило бы их без срока хранения,
    # а на уровне БД просто падало бы внешним ключом.
    used = db.query(Case).filter(Case.nomenclature_id == item_id).count()
    if used:
        raise HTTPException(
            status_code=409,
            detail=f"По статье заведено дел: {used}. Удаление невозможно.",
        )
    db.delete(item)
    db.commit()


@router.get("/summary/xlsx")
def summary_xlsx(request: Request, year: int | None = None,
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """Сводная номенклатура дел организации в Excel (ТЗ АГП п. 8).

    Сводная — значит по всем подразделениям сразу, с числом заведённых дел по
    каждой статье: именно так её сдают на согласование.
    """
    year = year or datetime.utcnow().year
    items = (db.query(NomenclatureItem)
             .filter(NomenclatureItem.year == year)
             .order_by(NomenclatureItem.index).all())
    if not items:
        raise HTTPException(status_code=404,
                            detail=f"Номенклатура за {year} год не заведена")
    case_counts = dict(
        db.query(Case.nomenclature_id, func.count(Case.id))
        .filter(Case.nomenclature_id.isnot(None))
        .group_by(Case.nomenclature_id).all()
    )
    departments = {d.id: d.name for d in db.query(Department).all()}
    rows = [
        [i.index, i.title, departments.get(i.department_id, "—"),
         "Постоянно" if i.permanent else (i.retention_label or "—"),
         i.article or "—", int(case_counts.get(i.id, 0)), i.status, i.note]
        for i in items
    ]
    data = xlsx.build(
        title=f"Сводная номенклатура дел на {year} год",
        subtitle=f"Сформирована {datetime.utcnow():%d.%m.%Y}, статей: {len(rows)}",
        headers=["Индекс дела", "Заголовок дела", "Подразделение", "Срок хранения",
                 "Статья по Перечню", "Заведено дел", "Статус", "Примечание"],
        rows=rows, sheet=f"Номенклатура {year}",
    )
    audit.record(db, user, "nomenclature.export", "nomenclature", str(year),
                 f"сводная номенклатура: статей {len(rows)}", request=request)
    return StreamingResponse(
        io.BytesIO(data), media_type=xlsx.MEDIA_TYPE,
        headers={"Content-Disposition":
                 f'attachment; filename="{xlsx.filename(f"nomenclature_{year}")}"'},
    )
