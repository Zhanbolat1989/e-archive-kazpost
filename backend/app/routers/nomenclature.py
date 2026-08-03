from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..autonumber import next_nomenclature_index
from ..db import get_db
from ..models import User, Role, NomenclatureItem, Case
from ..schemas import NomenclatureCreate, NomenclatureOut
from ..security import get_current_user, require_roles

router = APIRouter(prefix="/api/nomenclature", tags=["nomenclature"])


@router.get("", response_model=list[NomenclatureOut])
def list_items(
    year: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(NomenclatureItem)
    if year:
        q = q.filter(NomenclatureItem.year == year)
    return q.order_by(NomenclatureItem.year.desc(), NomenclatureItem.index).all()


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
