"""Модуль «Описи дел»: карточки описей, автоматическое
формирование по категории сроков хранения и выгрузка в Excel.

Опись — перечень единиц хранения одной категории за год (приказ № 235):
постоянного хранения, свыше 10 лет, по личному составу, до 10 лет. Состав
описи система предлагает сама по срокам хранения дел, а архивариус правит его
вручную — автоматика здесь помощник, а не последнее слово.
"""
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    Case, CaseStatus, Document, INVENTORY_KINDS, Inventory, InventoryItem, NtoRecord,
    Role, User,
)
from ..schemas import (
    InventoryCreate, InventoryDetail, InventoryItemOut, InventoryOut, InventoryUpdate,
)
from ..security import get_current_user, require_roles
from ..services import audit, xlsx

router = APIRouter(prefix="/api/inventories", tags=["inventories"])

PERMANENT, LONG, PERSONNEL, SHORT = INVENTORY_KINDS
LONG_TERM_YEARS = 10
# Дела по личному составу хранятся 75 лет (Перечень 279-НҚ) — по этому сроку
# они и опознаются, если в заголовке дела нет прямого указания.
PERSONNEL_YEARS = 50


def _kind_of(case: Case) -> str:
    """Категория описи, к которой относится дело."""
    label = f"{case.retention_label} {case.title}".lower()
    if any(w in label for w in ("личному составу", "личного состава", "кадров")):
        return PERSONNEL
    if case.permanent:
        return PERMANENT
    years = case.retention_years or 0
    if years >= PERSONNEL_YEARS:
        return PERSONNEL
    return LONG if years > LONG_TERM_YEARS else SHORT


def _doc_counts(db: Session) -> dict:
    return dict(
        db.query(Document.case_id, func.count(Document.id))
        .filter(Document.case_id.isnot(None), Document.destroyed_at.is_(None))
        .group_by(Document.case_id).all()
    )


def _next_number(db: Session, year: int, kind: str) -> str:
    seq = db.query(Inventory).filter(Inventory.year == year,
                                     Inventory.kind == kind).count() + 1
    code = {PERMANENT: "1", LONG: "2", PERSONNEL: "3", SHORT: "4"}.get(kind, "5")
    return f"{code}-{year}/{seq:02d}"


def _out(db: Session, inv: Inventory) -> InventoryOut:
    out = InventoryOut.model_validate(inv)
    out.items_count = len(inv.items)
    return out


def _detail(db: Session, inv: Inventory) -> InventoryDetail:
    counts = _doc_counts(db)
    out = InventoryDetail.model_validate(inv)
    out.items_count = len(inv.items)
    items: list[InventoryItemOut] = []
    for it in sorted(inv.items, key=lambda x: x.order_no):
        case = db.get(Case, it.case_id)
        if case is None:
            continue
        items.append(InventoryItemOut(
            case_id=case.id, order_no=it.order_no, case_index=case.index,
            case_title=case.title, year=case.year,
            retention="Постоянно" if case.permanent else (case.retention_label or "—"),
            documents_count=int(counts.get(case.id, 0)),
        ))
    out.items = items
    return out


def _autofill(db: Session, inv: Inventory) -> int:
    """Наполняет опись делами своей категории за свой год."""
    cases = (db.query(Case)
             .filter(Case.year == inv.year, Case.status != CaseStatus.destroyed)
             .order_by(Case.index).all())
    if inv.department_id:
        cases = [c for c in cases if c.department_id == inv.department_id]
    chosen = [c for c in cases if _kind_of(c) == inv.kind]
    inv.items = [InventoryItem(case_id=c.id, order_no=i)
                 for i, c in enumerate(chosen, start=1)]
    return len(chosen)


@router.get("/meta/kinds")
def kinds(_: User = Depends(get_current_user)) -> list[str]:
    return list(INVENTORY_KINDS)


@router.get("", response_model=list[InventoryOut])
def list_inventories(year: int | None = None, kind: str | None = None,
                     db: Session = Depends(get_db),
                     _: User = Depends(get_current_user)):
    q = db.query(Inventory)
    if year:
        q = q.filter(Inventory.year == year)
    if kind:
        q = q.filter(Inventory.kind == kind)
    rows = q.order_by(Inventory.year.desc(), Inventory.number).all()
    return [_out(db, i) for i in rows]


@router.post("", response_model=InventoryDetail, status_code=201)
def create_inventory(payload: InventoryCreate, request: Request,
                     db: Session = Depends(get_db),
                     user: User = Depends(require_roles(Role.admin, Role.archivist))):
    if payload.kind not in INVENTORY_KINDS:
        raise HTTPException(status_code=400,
                            detail="Категория описи: " + "; ".join(INVENTORY_KINDS))
    inv = Inventory(
        number=payload.number.strip() or _next_number(db, payload.year, payload.kind),
        title=payload.title or f"Опись дел {payload.kind.lower()} за {payload.year} год",
        year=payload.year, kind=payload.kind, note=payload.note,
        department_id=payload.department_id, created_by=user.email,
    )
    db.add(inv)
    db.flush()
    added = _autofill(db, inv) if payload.autofill else 0
    db.commit()
    db.refresh(inv)
    audit.record(db, user, "inventory.create", "inventory", inv.id,
                 f"{inv.number}: дел {added}", request=request)
    return _detail(db, inv)


@router.get("/{inv_id}", response_model=InventoryDetail)
def get_inventory(inv_id: str, db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    inv = db.get(Inventory, inv_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Опись не найдена")
    return _detail(db, inv)


@router.patch("/{inv_id}", response_model=InventoryDetail)
def update_inventory(inv_id: str, payload: InventoryUpdate, request: Request,
                     db: Session = Depends(get_db),
                     user: User = Depends(require_roles(Role.admin, Role.archivist))):
    inv = db.get(Inventory, inv_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Опись не найдена")
    changes = payload.model_dump(exclude_none=True)
    case_ids = changes.pop("case_ids", None)
    for field, value in changes.items():
        setattr(inv, field, value)
    if case_ids is not None:
        inv.items = [InventoryItem(case_id=cid, order_no=i)
                     for i, cid in enumerate(case_ids, start=1)
                     if db.get(Case, cid) is not None]
    db.commit()
    db.refresh(inv)
    audit.record(db, user, "inventory.update", "inventory", inv.id,
                 ", ".join(changes.keys()) or "состав описи", request=request)
    return _detail(db, inv)


@router.post("/{inv_id}/refill", response_model=InventoryDetail)
def refill(inv_id: str, db: Session = Depends(get_db),
           user: User = Depends(require_roles(Role.admin, Role.archivist))):
    """Пересобрать состав описи по срокам хранения — ручные правки состава
    при этом теряются, поэтому действие отдельное и явное."""
    inv = db.get(Inventory, inv_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Опись не найдена")
    added = _autofill(db, inv)
    db.commit()
    db.refresh(inv)
    audit.record(db, user, "inventory.refill", "inventory", inv.id, f"дел {added}")
    return _detail(db, inv)


@router.delete("/{inv_id}", status_code=204)
def delete_inventory(inv_id: str, db: Session = Depends(get_db),
                     user: User = Depends(require_roles(Role.admin))):
    inv = db.get(Inventory, inv_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Опись не найдена")
    # Предисловие к описи ссылается на неё: удаление оставило бы документ НТО без описи.
    if db.query(NtoRecord.id).filter(NtoRecord.inventory_id == inv_id).first() is not None:
        raise HTTPException(status_code=409,
                            detail="К описи составлено предисловие (раздел НТО) — сначала удалите его")
    db.delete(inv)      # позиции снимаются каскадом
    db.commit()
    audit.record(db, user, "inventory.delete", "inventory", inv_id, inv.number)


@router.get("/{inv_id}/xlsx")
def export_xlsx(inv_id: str, request: Request, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    """Выгрузка описи в Excel (п. 8)."""
    inv = db.get(Inventory, inv_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Опись не найдена")
    detail = _detail(db, inv)
    rows = [[i.order_no, i.case_index, i.case_title, i.year, i.documents_count,
             i.retention] for i in detail.items]
    data = xlsx.build(
        title=inv.title,
        subtitle=(f"№ {inv.number} · {inv.kind} · сформирована "
                  f"{datetime.utcnow():%d.%m.%Y}"),
        headers=["№ п/п", "Индекс дела", "Заголовок дела", "Год",
                 "Кол-во документов", "Срок хранения"],
        rows=rows, sheet=f"Опись {inv.year}",
    )
    audit.record(db, user, "inventory.export", "inventory", inv.id,
                 f"{inv.number}: {len(rows)} дел", request=request)
    return StreamingResponse(
        io.BytesIO(data), media_type=xlsx.MEDIA_TYPE,
        headers={"Content-Disposition":
                 f'attachment; filename="{xlsx.filename("inventory_" + inv.number)}"'},
    )
