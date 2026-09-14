"""Редактируемые справочники (ТС-176 п. 4.9). Виды справочников и правила —
в services/dictionaries.py."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import DictionaryEntry, Role, User
from ..schemas import DictionaryEntryIn, DictionaryEntryOut, DictionaryEntryUpdate
from ..security import get_current_user, require_roles
from ..services import audit, dictionaries

router = APIRouter(prefix="/api/dictionaries", tags=["dictionaries"])

_DUPLICATE = "Такое значение в справочнике уже есть"


def _value(raw: str) -> str:
    value = raw.strip()
    if not value:
        raise HTTPException(status_code=400, detail="Значение не может быть пустым")
    return value


def _is_duplicate(db: Session, kind: str, value: str, exclude_id: str | None = None) -> bool:
    q = db.query(DictionaryEntry.id).filter(DictionaryEntry.kind == kind,
                                            DictionaryEntry.value == value)
    if exclude_id:
        q = q.filter(DictionaryEntry.id != exclude_id)
    return q.first() is not None


def _commit(db: Session) -> None:
    # Проверка на повтор выше даёт понятный ответ; уникальный индекс ловит
    # одновременное добавление одного значения двумя администраторами.
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=_DUPLICATE) from exc


@router.get("")
def list_dictionaries(db: Session = Depends(get_db),
                      _: User = Depends(get_current_user)) -> list[dict]:
    """Все справочники со значениями, включая выведенные из употребления:
    формы берут действующие, раздел администрирования показывает все."""
    rows = (db.query(DictionaryEntry)
            .order_by(DictionaryEntry.sort_order, DictionaryEntry.value).all())
    entries: dict[str, list[DictionaryEntryOut]] = {k: [] for k in dictionaries.KINDS}
    for r in rows:
        if r.kind in entries:
            entries[r.kind].append(DictionaryEntryOut.model_validate(r))
    return [
        {"kind": kind, "label": spec["label"], "hint": spec["hint"],
         "strict": spec["strict"], "entries": entries[kind]}
        for kind, spec in dictionaries.KINDS.items()
    ]


@router.post("/{kind}", response_model=DictionaryEntryOut, status_code=201)
def add_entry(kind: str, payload: DictionaryEntryIn, request: Request,
              db: Session = Depends(get_db),
              user: User = Depends(require_roles(Role.admin))):
    try:
        dictionaries.check_kind(kind)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    value = _value(payload.value)
    if _is_duplicate(db, kind, value):
        raise HTTPException(status_code=409, detail=_DUPLICATE)
    entry = DictionaryEntry(kind=kind, value=value, sort_order=payload.sort_order)
    db.add(entry)
    _commit(db)
    db.refresh(entry)
    audit.record(db, user, "dictionary.add", "dictionary", entry.id,
                 f"{dictionaries.KINDS[kind]['label']}: {value}", request=request)
    return entry


@router.patch("/entries/{entry_id}", response_model=DictionaryEntryOut)
def update_entry(entry_id: str, payload: DictionaryEntryUpdate, request: Request,
                 db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.admin))):
    """Переименование, порядок и вывод из употребления. Удаления нет: значение
    уже может стоять в заведённых записях."""
    entry = db.get(DictionaryEntry, entry_id)
    if entry is None or entry.kind not in dictionaries.KINDS:
        raise HTTPException(status_code=404, detail="Значение справочника не найдено")
    changes = payload.model_dump(exclude_none=True)
    if "value" in changes:
        changes["value"] = _value(changes["value"])
        if _is_duplicate(db, entry.kind, changes["value"], exclude_id=entry.id):
            raise HTTPException(status_code=409, detail=_DUPLICATE)
    described = "; ".join(f"{field}: {getattr(entry, field)} → {value}"
                          for field, value in changes.items())
    for field, value in changes.items():
        setattr(entry, field, value)
    _commit(db)
    db.refresh(entry)
    audit.record(db, user, "dictionary.update", "dictionary", entry.id,
                 f"{dictionaries.KINDS[entry.kind]['label']}: {described}", request=request)
    return entry
