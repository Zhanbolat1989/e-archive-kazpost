"""Научно-техническая обработка, экспертные комиссии и передача дел в
госархив (ТС-176 п. 5.3, 8.2, 10.2–10.5).

Правила — services/nto.py, печатные формы — services/nto_forms.py, пакеты
электронных дел — services/packages.py.
"""
import io
import json
import tempfile
import zipfile
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    ActStatus, Case, CaseStatus, CaseWorkStage, CommissionDecision, CommissionProtocol,
    Department, DestructionAct, DestructionActItem, Document, Inventory, NtoRecord,
    Organization, Role, TransferAct, TransferActItem, User,
)
from ..schemas import (
    CommissionDecisionIn, CommissionProtocolIn, CommissionProtocolOut, NtoRecordIn,
    NtoRecordOut, TransferActIn, TransferActOut, TransferItemOut,
)
from ..security import get_current_user, require_roles
from ..services import audit, nto_forms, packages
from ..services import nto as rules
from ..services.forms import ORG_NAME

router = APIRouter(prefix="/api/nto", tags=["nto"])

_editors = require_roles(Role.admin, Role.archivist)
_admins = require_roles(Role.admin)

# Объекты, по которым комиссия принимает решение.
_OBJECTS = {
    "inventory": Inventory,
    "destruction_act": DestructionAct,
    "nto": NtoRecord,
    "transfer": TransferAct,
}


def _org_name(db: Session) -> str:
    org = db.query(Organization).order_by(Organization.updated_at.desc()).first()
    return org.name if org is not None and org.name else ORG_NAME


def _next_number(db: Session, column, prefix: str, year: int) -> str:
    seq = db.query(func.count(column)).filter(column.like(f"{prefix}-{year}/%")).scalar() + 1
    return f"{prefix}-{year}/{seq:02d}"


def _get(db: Session, model, obj_id: str, what: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{what} не найден")
    return obj


def _author(user: User) -> str:
    return user.full_name or user.email


def _file_response(data: bytes, media_type: str, filename: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(data), media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _problems(problems: list[str]) -> str:
    more = f" и ещё {len(problems) - 3}" if len(problems) > 3 else ""
    return "Не подлежат передаче: " + "; ".join(problems[:3]) + more


@router.get("/meta")
def nto_meta(_: User = Depends(get_current_user)) -> dict:
    return {
        "commissions": [{"key": k, "label": v} for k, v in rules.COMMISSIONS.items()],
        "decisions": [{"key": k, "label": v} for k, v in rules.DECISIONS.items()],
        "objects": [{"key": k, "label": v} for k, v in rules.PROTOCOL_OBJECTS.items()],
        "kinds": [
            {"key": k, "label": spec["label"], "needs_inventory": spec["needs_inventory"],
             "has_items": spec["has_items"],
             "fields": [{"key": f, "label": label} for f, label in spec["fields"]]}
            for k, spec in rules.NTO_KINDS.items()
        ],
    }


# ---- Протоколы экспертных комиссий ----

def _object_title(object_type: str, obj) -> str:
    if object_type == "inventory":
        return f"Опись № {obj.number}: {obj.title}"
    if object_type == "destruction_act":
        return f"Акт о выделении к уничтожению № {obj.number}"
    if object_type == "nto":
        return f"{rules.NTO_KINDS[obj.kind]['label']} № {obj.number}"
    return f"Акт приёма-передачи № {obj.number}"


def _decision_rows(db: Session, object_type: str, object_id: str):
    return (db.query(CommissionDecision, CommissionProtocol)
            .join(CommissionProtocol, CommissionProtocol.id == CommissionDecision.protocol_id)
            .filter(CommissionDecision.object_type == object_type,
                    CommissionDecision.object_id == object_id)
            .order_by(CommissionProtocol.protocol_date, CommissionProtocol.number)
            .all())


def _decision_labels(db: Session, object_type: str, object_id: str) -> list[str]:
    return [rules.decision_label(d.decision, p.commission, p.number, p.protocol_date)
            + (f" — {d.comment}" if d.comment else "")
            for d, p in _decision_rows(db, object_type, object_id)]


def _protocol_fields(db: Session, payload: CommissionProtocolIn,
                     exclude_id: str | None = None) -> dict:
    if payload.commission not in rules.COMMISSIONS:
        raise HTTPException(status_code=400,
                            detail="Комиссия: " + ", ".join(rules.COMMISSIONS))
    number = payload.number.strip()
    if not number:
        raise HTTPException(status_code=400, detail="Укажите номер протокола")
    year = payload.protocol_date.year
    dup = db.query(CommissionProtocol.id).filter(
        CommissionProtocol.commission == payload.commission,
        CommissionProtocol.number == number,
        CommissionProtocol.protocol_date.between(date(year, 1, 1), date(year, 12, 31)),
    )
    if exclude_id:
        dup = dup.filter(CommissionProtocol.id != exclude_id)
    if dup.first() is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Протокол {payload.commission} № {number} за {year} год уже зарегистрирован",
        )
    return {"commission": payload.commission, "number": number,
            "protocol_date": payload.protocol_date, "agenda": payload.agenda.strip(),
            "note": payload.note.strip()}


@router.get("/protocols", response_model=list[CommissionProtocolOut])
def list_protocols(commission: str | None = None, db: Session = Depends(get_db),
                   _: User = Depends(get_current_user)):
    q = db.query(CommissionProtocol)
    if commission:
        q = q.filter(CommissionProtocol.commission == commission)
    return q.order_by(CommissionProtocol.protocol_date.desc(),
                      CommissionProtocol.number.desc()).all()


@router.post("/protocols", response_model=CommissionProtocolOut, status_code=201)
def create_protocol(payload: CommissionProtocolIn, request: Request,
                    db: Session = Depends(get_db), user: User = Depends(_editors)):
    protocol = CommissionProtocol(**_protocol_fields(db, payload), created_by=_author(user))
    db.add(protocol)
    db.commit()
    db.refresh(protocol)
    audit.record(db, user, "commission_protocol.create", "commission_protocol", protocol.id,
                 rules.protocol_label(protocol.commission, protocol.number,
                                      protocol.protocol_date), request=request)
    return protocol


@router.put("/protocols/{protocol_id}", response_model=CommissionProtocolOut)
def update_protocol(protocol_id: str, payload: CommissionProtocolIn, request: Request,
                    db: Session = Depends(get_db), user: User = Depends(_editors)):
    protocol = _get(db, CommissionProtocol, protocol_id, "Протокол")
    for field, value in _protocol_fields(db, payload, exclude_id=protocol.id).items():
        setattr(protocol, field, value)
    db.commit()
    db.refresh(protocol)
    audit.record(db, user, "commission_protocol.update", "commission_protocol", protocol.id,
                 rules.protocol_label(protocol.commission, protocol.number,
                                      protocol.protocol_date), request=request)
    return protocol


@router.delete("/protocols/{protocol_id}", status_code=204)
def delete_protocol(protocol_id: str, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(_admins)):
    protocol = _get(db, CommissionProtocol, protocol_id, "Протокол")
    if protocol.decisions:
        raise HTTPException(status_code=409,
                            detail="В протоколе есть решения — сначала удалите их")
    label = rules.protocol_label(protocol.commission, protocol.number, protocol.protocol_date)
    db.delete(protocol)
    db.commit()
    audit.record(db, user, "commission_protocol.delete", "commission_protocol", protocol_id,
                 label, request=request)


def _apply_decision(protocol: CommissionProtocol, row: CommissionDecision, obj) -> str:
    """Переносит решение на карточку объекта; возвращает, что изменилось."""
    if row.object_type == "inventory":
        obj.status = rules.inventory_status(protocol.commission, row.decision)
        return f"статус описи: {obj.status}"
    if (row.object_type == "destruction_act" and row.decision in rules.POSITIVE
            and obj.status != ActStatus.approved and not obj.commission_protocol):
        # Утверждённый акт не меняется, а вписанный вручную протокол не затирается.
        obj.commission_protocol = rules.protocol_label(
            protocol.commission, protocol.number, protocol.protocol_date)[:128]
        return f"в акт вписан протокол {obj.commission_protocol}"
    return ""


@router.post("/protocols/{protocol_id}/decisions", response_model=CommissionProtocolOut,
             status_code=201)
def add_decision(protocol_id: str, payload: CommissionDecisionIn, request: Request,
                 db: Session = Depends(get_db), user: User = Depends(_editors)):
    protocol = _get(db, CommissionProtocol, protocol_id, "Протокол")
    model = _OBJECTS.get(payload.object_type)
    if model is None:
        raise HTTPException(status_code=400,
                            detail="Объект решения: " + ", ".join(rules.PROTOCOL_OBJECTS))
    if payload.decision not in rules.DECISIONS:
        raise HTTPException(status_code=400,
                            detail="Решение: " + ", ".join(rules.DECISIONS))
    obj = db.get(model, payload.object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Объект решения не найден")
    exists = (db.query(CommissionDecision.id)
              .filter(CommissionDecision.protocol_id == protocol.id,
                      CommissionDecision.object_type == payload.object_type,
                      CommissionDecision.object_id == payload.object_id)
              .first())
    if exists is not None:
        raise HTTPException(status_code=409,
                            detail="По этому объекту в протоколе уже есть решение")
    row = CommissionDecision(
        protocol_id=protocol.id, object_type=payload.object_type,
        object_id=payload.object_id, object_title=_object_title(payload.object_type, obj)[:512],
        decision=payload.decision, comment=payload.comment.strip(),
    )
    db.add(row)
    effect = _apply_decision(protocol, row, obj)
    db.commit()
    db.refresh(protocol)
    audit.record(db, user, "commission_decision.add", payload.object_type, payload.object_id,
                 rules.decision_label(row.decision, protocol.commission, protocol.number,
                                      protocol.protocol_date)
                 + (f"; {effect}" if effect else ""), request=request)
    return protocol


@router.delete("/protocols/{protocol_id}/decisions/{decision_id}",
               response_model=CommissionProtocolOut)
def delete_decision(protocol_id: str, decision_id: str, request: Request,
                    db: Session = Depends(get_db), user: User = Depends(_admins)):
    """Удаление ошибочно внесённого решения. Статус описи и протокол в акте,
    перенесённые решением, не откатываются: их правят в карточке объекта."""
    protocol = _get(db, CommissionProtocol, protocol_id, "Протокол")
    row = db.get(CommissionDecision, decision_id)
    if row is None or row.protocol_id != protocol.id:
        raise HTTPException(status_code=404, detail="Решение не найдено")
    detail = f"{row.object_title}: {rules.DECISIONS.get(row.decision, row.decision)}"
    db.delete(row)
    db.commit()
    db.refresh(protocol)
    audit.record(db, user, "commission_decision.delete", row.object_type, row.object_id,
                 detail, request=request)
    return protocol


@router.get("/decisions")
def object_decisions(object_type: str, object_id: str, db: Session = Depends(get_db),
                     _: User = Depends(get_current_user)) -> list[dict]:
    """Решения комиссий по одному объекту — для карточек описи и акта."""
    return [
        {"id": d.id, "decision": d.decision,
         "decision_label": rules.DECISIONS.get(d.decision, d.decision),
         "comment": d.comment, "protocol_id": p.id,
         "protocol": rules.protocol_label(p.commission, p.number, p.protocol_date)}
        for d, p in _decision_rows(db, object_type, object_id)
    ]


# ---- Документы НТО ----

def _record_values(db: Session, payload: NtoRecordIn, current: NtoRecord | None = None) -> dict:
    spec = rules.NTO_KINDS.get(payload.kind)
    if spec is None:
        raise HTTPException(status_code=400,
                            detail="Вид документа НТО: " + ", ".join(rules.NTO_KINDS))
    if current is not None and current.kind != payload.kind:
        raise HTTPException(status_code=400,
                            detail="Вид документа НТО не меняется — создайте новый документ")
    inventory = db.get(Inventory, payload.inventory_id) if payload.inventory_id else None
    if payload.inventory_id and inventory is None:
        raise HTTPException(status_code=400, detail="Опись не найдена")
    if spec["needs_inventory"] and inventory is None:
        raise HTTPException(status_code=400,
                            detail="Выберите опись, к которой составлено предисловие")
    try:
        rules.check_years(payload.year_from, payload.year_to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    fond = payload.fond.strip()
    title = payload.title.strip() or rules.default_title(
        payload.kind, inventory.number if inventory else None, fond,
        payload.year_from, payload.year_to)
    return {
        "kind": payload.kind,
        "record_date": payload.record_date or (current.record_date if current else date.today()),
        "title": title[:512],
        "fond": fond,
        "year_from": payload.year_from,
        "year_to": payload.year_to,
        "inventory_id": inventory.id if inventory else None,
        "fields": rules.clean_fields(payload.kind, payload.fields),
        "items": [i.model_dump() for i in payload.items] if spec["has_items"] else [],
    }


def _editable_record(db: Session, record_id: str) -> NtoRecord:
    rec = _get(db, NtoRecord, record_id, "Документ НТО")
    if rec.status == rules.APPROVED:
        raise HTTPException(status_code=409, detail="Документ утверждён — изменить его нельзя")
    return rec


@router.get("/records", response_model=list[NtoRecordOut])
def list_records(kind: str | None = None, db: Session = Depends(get_db),
                 _: User = Depends(get_current_user)):
    q = db.query(NtoRecord)
    if kind:
        q = q.filter(NtoRecord.kind == kind)
    return q.order_by(NtoRecord.record_date.desc(), NtoRecord.number.desc()).all()


@router.post("/records", response_model=NtoRecordOut, status_code=201)
def create_record(payload: NtoRecordIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(_editors)):
    values = _record_values(db, payload)
    number = payload.number.strip() or _next_number(
        db, NtoRecord.number, rules.NTO_KINDS[payload.kind]["prefix"], values["record_date"].year)
    rec = NtoRecord(**values, number=number, created_by=_author(user))
    db.add(rec)
    db.commit()
    db.refresh(rec)
    audit.record(db, user, "nto.create", "nto", rec.id, f"{rec.number}: {rec.title}",
                 request=request)
    return rec


@router.put("/records/{record_id}", response_model=NtoRecordOut)
def update_record(record_id: str, payload: NtoRecordIn, request: Request,
                  db: Session = Depends(get_db), user: User = Depends(_editors)):
    rec = _editable_record(db, record_id)
    values = _record_values(db, payload, rec)
    values["number"] = payload.number.strip() or rec.number
    for field, value in values.items():
        setattr(rec, field, value)
    db.commit()
    db.refresh(rec)
    audit.record(db, user, "nto.update", "nto", rec.id, f"{rec.number}: {rec.title}",
                 request=request)
    return rec


@router.post("/records/{record_id}/approve", response_model=NtoRecordOut)
def approve_record(record_id: str, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(_admins)):
    rec = _editable_record(db, record_id)
    try:
        rules.check_approvable(rec.kind, rec.items or [])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    rec.status = rules.APPROVED
    rec.approved_by = _author(user)
    rec.approved_at = datetime.utcnow()
    db.commit()
    db.refresh(rec)
    audit.record(db, user, "nto.approve", "nto", rec.id, f"{rec.number}: {rec.title}",
                 request=request)
    return rec


@router.delete("/records/{record_id}", status_code=204)
def delete_record(record_id: str, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(_admins)):
    rec = _editable_record(db, record_id)
    label = f"{rec.number}: {rec.title}"
    db.delete(rec)
    db.commit()
    audit.record(db, user, "nto.delete", "nto", record_id, label, request=request)


def _in_years(query, column, rec: NtoRecord):
    if rec.year_from:
        query = query.filter(column >= rec.year_from)
    if rec.year_to:
        query = query.filter(column <= rec.year_to)
    return query


def _render_record(db: Session, rec: NtoRecord) -> str:
    org = _org_name(db)
    decisions = _decision_labels(db, "nto", rec.id)
    if rec.kind == "history_note":
        departments = [d.name for d in
                       db.query(Department).order_by(Department.index, Department.name)]
        cases = _in_years(db.query(Case).filter(Case.status != CaseStatus.destroyed),
                          Case.year, rec)
        year_min, year_max = cases.with_entities(func.min(Case.year), func.max(Case.year)).one()
        stats = {"cases": cases.count(),
                 "permanent": cases.filter(Case.permanent.is_(True)).count(),
                 "year_min": year_min, "year_max": year_max}
        return nto_forms.history_note_html(rec, org, departments, stats, decisions)
    if rec.kind == "inventory_preface":
        inventory = db.get(Inventory, rec.inventory_id) if rec.inventory_id else None
        years = [it.case.year for it in inventory.items] if inventory else []
        stats = {"cases": len(years), "year_min": min(years, default=None),
                 "year_max": max(years, default=None)}
        return nto_forms.inventory_preface_html(rec, org, inventory, stats, decisions)
    if rec.kind == "arrangement_act":
        inventories = [
            {"number": i.number, "title": i.title, "kind": i.kind, "year": i.year,
             "cases": len(i.items)}
            for i in _in_years(db.query(Inventory), Inventory.year, rec)
            .order_by(Inventory.year, Inventory.number)
        ]
        cases, pages = _in_years(
            db.query(func.count(CaseWorkStage.id), func.coalesce(func.sum(CaseWorkStage.pages), 0))
            .join(Case, Case.id == CaseWorkStage.case_id)
            .filter(CaseWorkStage.stage == "nto"),
            Case.year, rec,
        ).one()
        acts = (db.query(DestructionAct.number, DestructionAct.act_date,
                         func.count(DestructionActItem.id))
                .join(DestructionActItem, DestructionActItem.act_id == DestructionAct.id)
                .filter(DestructionAct.status == ActStatus.approved,
                        DestructionAct.kind == "retention"))
        if rec.year_from:
            acts = acts.filter(DestructionAct.act_date >= date(rec.year_from, 1, 1))
        if rec.year_to:
            acts = acts.filter(DestructionAct.act_date <= date(rec.year_to, 12, 31))
        destroyed = [{"number": n, "date": d, "documents": int(c)} for n, d, c in
                     acts.group_by(DestructionAct.id, DestructionAct.number, DestructionAct.act_date)
                     .order_by(DestructionAct.act_date).all()]
        return nto_forms.arrangement_act_html(
            rec, org, inventories, {"cases": int(cases), "pages": int(pages)}, destroyed, decisions)
    return nto_forms.missing_act_html(rec, org, decisions)


@router.get("/records/{record_id}/form")
def record_form(record_id: str, fmt: str = Query("pdf", pattern="^(pdf|html)$"),
                db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rec = _get(db, NtoRecord, record_id, "Документ НТО")
    html = _render_record(db, rec)
    if fmt == "html":
        return HTMLResponse(html)
    return _file_response(nto_forms.to_pdf(html), "application/pdf",
                          f"{rec.kind}_{rules.ascii_name(rec.number, 'nto')}.pdf")


# ---- Передача дел на государственное хранение ----

def _transfer_out(db: Session, act: TransferAct) -> TransferActOut:
    ids = [it.case_id for it in act.items]
    counts = (dict(db.query(Document.case_id, func.count(Document.id))
                   .filter(Document.case_id.in_(ids), Document.destroyed_at.is_(None))
                   .group_by(Document.case_id).all())
              if ids else {})
    items = [
        TransferItemOut(
            case_id=it.case_id, order_no=it.order_no, case_index=it.case.index,
            case_title=it.case.title, year=it.case.year, volume=it.case.volume,
            documents_count=int(counts.get(it.case_id, 0)),
            retention="Постоянно" if it.case.permanent else (it.case.retention_label or ""),
        )
        for it in act.items
    ]
    return TransferActOut(
        id=act.id, number=act.number, act_date=act.act_date, archive_name=act.archive_name,
        fond=act.fond, basis=act.basis, note=act.note, status=act.status,
        created_by=act.created_by, transferred_by=act.transferred_by,
        transferred_at=act.transferred_at, created_at=act.created_at, items=items,
    )


def _transfer_cases(db: Session, case_ids: list[str], act_id: str | None = None) -> list[Case]:
    ids = list(dict.fromkeys(case_ids))
    if not ids:
        raise HTTPException(status_code=400, detail="Выберите дела для передачи")
    found = {c.id: c for c in db.query(Case).filter(Case.id.in_(ids)).all()}
    if len(found) != len(ids):
        raise HTTPException(status_code=400, detail="Часть дел не найдена")
    cases = [found[i] for i in ids]
    problems = rules.transfer_problems(cases)
    if problems:
        raise HTTPException(status_code=400, detail=_problems(problems))
    # Дело не может ждать передачи по двум актам сразу.
    busy = (db.query(TransferAct.number)
            .join(TransferActItem, TransferActItem.act_id == TransferAct.id)
            .filter(TransferActItem.case_id.in_(ids), TransferAct.status == rules.DRAFT))
    if act_id:
        busy = busy.filter(TransferAct.id != act_id)
    row = busy.first()
    if row is not None:
        raise HTTPException(status_code=409,
                            detail=f"Часть дел уже включена в проект акта {row[0]}")
    return cases


def _draft_transfer(db: Session, act_id: str) -> TransferAct:
    act = _get(db, TransferAct, act_id, "Акт приёма-передачи")
    if act.status != rules.DRAFT:
        raise HTTPException(status_code=409,
                            detail="Дела по акту уже переданы — акт не меняется")
    return act


def _transfer_fields(payload: TransferActIn) -> dict:
    archive_name = payload.archive_name.strip()
    if not archive_name:
        raise HTTPException(status_code=400, detail="Укажите принимающий государственный архив")
    return {"archive_name": archive_name, "fond": payload.fond.strip(),
            "basis": payload.basis.strip(), "note": payload.note.strip()}


@router.get("/transfers", response_model=list[TransferActOut])
def list_transfers(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    acts = (db.query(TransferAct)
            .order_by(TransferAct.act_date.desc(), TransferAct.number.desc()).all())
    return [_transfer_out(db, a) for a in acts]


@router.post("/transfers", response_model=TransferActOut, status_code=201)
def create_transfer(payload: TransferActIn, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(_editors)):
    fields = _transfer_fields(payload)
    cases = _transfer_cases(db, payload.case_ids)
    act_date = payload.act_date or date.today()
    act = TransferAct(
        **fields, act_date=act_date, created_by=_author(user),
        number=payload.number.strip() or _next_number(db, TransferAct.number, "АПП",
                                                      act_date.year),
    )
    act.items = [TransferActItem(case_id=c.id, order_no=i) for i, c in enumerate(cases, start=1)]
    db.add(act)
    db.commit()
    db.refresh(act)
    audit.record(db, user, "transfer.create", "transfer", act.id,
                 f"{act.number}: дел {len(cases)}", request=request)
    return _transfer_out(db, act)


@router.put("/transfers/{act_id}", response_model=TransferActOut)
def update_transfer(act_id: str, payload: TransferActIn, request: Request,
                    db: Session = Depends(get_db), user: User = Depends(_editors)):
    act = _draft_transfer(db, act_id)
    fields = _transfer_fields(payload)
    cases = _transfer_cases(db, payload.case_ids, act.id)
    for field, value in fields.items():
        setattr(act, field, value)
    act.number = payload.number.strip() or act.number
    act.act_date = payload.act_date or act.act_date
    act.items = [TransferActItem(case_id=c.id, order_no=i) for i, c in enumerate(cases, start=1)]
    db.commit()
    db.refresh(act)
    audit.record(db, user, "transfer.update", "transfer", act.id,
                 f"{act.number}: дел {len(cases)}", request=request)
    return _transfer_out(db, act)


@router.delete("/transfers/{act_id}", status_code=204)
def delete_transfer(act_id: str, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(_admins)):
    act = _draft_transfer(db, act_id)
    number = act.number
    db.delete(act)
    db.commit()
    audit.record(db, user, "transfer.delete", "transfer", act_id, number, request=request)


def _transfer_html(db: Session, act: TransferAct) -> str:
    out = _transfer_out(db, act)
    return nto_forms.transfer_act_html(act, _org_name(db), [i.model_dump() for i in out.items],
                                       _decision_labels(db, "transfer", act.id))


@router.get("/transfers/{act_id}/form")
def transfer_form(act_id: str, fmt: str = Query("pdf", pattern="^(pdf|html)$"),
                  db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    act = _get(db, TransferAct, act_id, "Акт приёма-передачи")
    html = _transfer_html(db, act)
    if fmt == "html":
        return HTMLResponse(html)
    return _file_response(nto_forms.to_pdf(html), "application/pdf",
                          f"transfer_{rules.ascii_name(act.number, 'act')}.pdf")


@router.get("/transfers/{act_id}/package")
def transfer_package(act_id: str, request: Request, db: Session = Depends(get_db),
                     user: User = Depends(_editors)):
    """Пакет для передачи на государственное хранение: акт, информационные
    пакеты всех дел (файлы, контрольные характеристики, опись электронного
    дела) и общий manifest.

    Пакет собирается во временный файл, а не в память: сотни дел по сотне
    листов не должны держаться в оперативной памяти целиком."""
    act = _get(db, TransferAct, act_id, "Акт приёма-передачи")
    spool = tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024)
    cases_manifest = []
    missing = 0
    with zipfile.ZipFile(spool, "w", zipfile.ZIP_DEFLATED) as zf:
        for it in act.items:
            docs = (db.query(Document)
                    .filter(Document.case_id == it.case_id, Document.destroyed_at.is_(None))
                    .order_by(Document.doc_date.asc().nullslast(), Document.created_at)
                    .all())
            folder = f"cases/{it.order_no:03d}_{rules.ascii_name(it.case.index, 'case')}/"
            entry = packages.add_case(zf, it.case, docs, prefix=folder)
            missing += len(entry["missing"])
            cases_manifest.append({"order_no": it.order_no, "folder": folder, **entry})
        html = _transfer_html(db, act)
        try:
            zf.writestr("act.pdf", nto_forms.to_pdf(html))
        except Exception:  # noqa: BLE001
            zf.writestr("act.html", html)
        zf.writestr("manifest.json", json.dumps({
            "act": {"number": act.number, "date": act.act_date.isoformat(),
                    "from": _org_name(db), "to": act.archive_name, "fond": act.fond,
                    "status": act.status, "exported_at": datetime.utcnow().isoformat(),
                    "exported_by": user.email},
            "cases": cases_manifest,
        }, ensure_ascii=False, indent=2))
    audit.record(db, user, "transfer.package", "transfer", act.id,
                 f"{act.number}: дел {len(cases_manifest)}, не прочитано файлов {missing}",
                 request=request)
    spool.seek(0)

    def chunks():
        try:
            while block := spool.read(1024 * 1024):
                yield block
        finally:
            spool.close()

    return StreamingResponse(
        chunks(), media_type="application/zip",
        headers={"Content-Disposition":
                 f'attachment; filename="transfer_{rules.ascii_name(act.number, "act")}.zip"'},
    )


@router.post("/transfers/{act_id}/complete", response_model=TransferActOut)
def complete_transfer(act_id: str, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(_admins)):
    """Дела приняты госархивом: акт закрывается, дела получают статус «Передано»."""
    act = _draft_transfer(db, act_id)
    cases = [it.case for it in act.items]
    if not cases:
        raise HTTPException(status_code=409, detail="В акте нет дел")
    problems = rules.transfer_problems(cases)
    if problems:
        raise HTTPException(status_code=409, detail=_problems(problems))
    for case in cases:
        case.status = CaseStatus.transferred
        case.version = (case.version or 1) + 1
    act.status = rules.TRANSFER_DONE
    act.transferred_by = _author(user)
    act.transferred_at = datetime.utcnow()
    db.commit()
    db.refresh(act)
    audit.record(db, user, "transfer.complete", "transfer", act.id,
                 f"{act.number}: передано дел {len(cases)} в {act.archive_name}",
                 request=request)
    return _transfer_out(db, act)
