"""Администрирование по ТЗ АГП п. 8–9: история изменений записей, доступ к
документам по категориям, ключи доступа внешних систем и журнал ИИ-агента.

Учётные записи, сессии и аудиторский след остаются в своих модулях (auth,
audit) — здесь только то, чего требует ТЗ «Азиатского Газопровода» сверх них.
"""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    AgentLog, ChangeHistory, DOC_TYPE_GROUPS, DocTypeAccess, Role, User,
)
from ..schemas import (
    AgentLogOut, ApiKeyCreate, ApiKeyCreated, ApiKeyOut, DocTypeAccessIn,
    DocTypeAccessOut,
)
from ..models import ApiKey
from ..security import generate_api_key, require_roles
from ..services import audit

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------- История изменений записей ----------
@router.get("/changes")
def changes(object_type: str | None = None, object_id: str | None = None,
            user_email: str | None = None, limit: int = 200,
            db: Session = Depends(get_db),
            _: User = Depends(require_roles(Role.admin))) -> list[dict]:
    q = db.query(ChangeHistory)
    if object_type:
        q = q.filter(ChangeHistory.object_type == object_type)
    if object_id:
        q = q.filter(ChangeHistory.object_id == object_id)
    if user_email:
        q = q.filter(ChangeHistory.user_email == user_email)
    rows = q.order_by(ChangeHistory.ts.desc()).limit(min(limit, 1000)).all()
    return [{"id": r.id, "ts": r.ts.isoformat(), "user_email": r.user_email,
             "object_type": r.object_type, "object_id": r.object_id,
             "field": r.field, "old_value": r.old_value, "new_value": r.new_value}
            for r in rows]


# ---------- Доступ к документам по категориям ----------
@router.get("/doc-access", response_model=list[DocTypeAccessOut])
def doc_access(db: Session = Depends(get_db),
               _: User = Depends(require_roles(Role.admin))):
    """Настройки доступа по ролям. Роль без записей видит все категории."""
    rows = db.query(DocTypeAccess).all()
    by_role: dict[str, list[str]] = {}
    for r in rows:
        by_role.setdefault(r.role, []).append(r.doc_group)
    return [DocTypeAccessOut(role=role, doc_groups=sorted(groups))
            for role, groups in sorted(by_role.items())]


@router.get("/doc-access/groups")
def groups(_: User = Depends(require_roles(Role.admin))) -> list[str]:
    return list(DOC_TYPE_GROUPS)


@router.put("/doc-access", response_model=DocTypeAccessOut)
def set_doc_access(payload: DocTypeAccessIn, request: Request,
                   db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.admin))):
    """Заменяет перечень категорий, доступных роли. Пустой перечень снимает
    ограничения: иначе «ничего не выбрано» означало бы полностью закрытый
    доступ, и роль молча лишилась бы всех документов."""
    unknown = [g for g in payload.doc_groups if g not in DOC_TYPE_GROUPS]
    if unknown:
        raise HTTPException(status_code=400,
                            detail="Неизвестные категории: " + ", ".join(unknown))
    if payload.role == Role.admin:
        raise HTTPException(status_code=400,
                            detail="Администратору доступны все категории — "
                                   "иначе он мог бы закрыть доступ сам себе")
    role = payload.role.value
    db.query(DocTypeAccess).filter(DocTypeAccess.role == role).delete(
        synchronize_session=False)
    for g in payload.doc_groups:
        db.add(DocTypeAccess(role=role, doc_group=g))
    db.commit()
    audit.security(db, user, "access.doc_types",
                   f"{role}: " + (", ".join(payload.doc_groups) or "без ограничений"),
                   request=request)
    return DocTypeAccessOut(role=role, doc_groups=payload.doc_groups)


# ---------- Ключи доступа внешних систем ----------
@router.get("/api-keys", response_model=list[ApiKeyOut])
def list_keys(db: Session = Depends(get_db),
              _: User = Depends(require_roles(Role.admin))):
    return db.query(ApiKey).order_by(ApiKey.created_at.desc()).all()


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=201)
def create_key(payload: ApiKeyCreate, request: Request,
               db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.admin))):
    """Создаёт ключ интеграции. Сам ключ возвращается один раз: в базе хранится
    только его хэш, и восстановить значение позже невозможно."""
    if payload.role == Role.admin:
        raise HTTPException(status_code=400,
                            detail="Ключу нельзя выдать права администратора: "
                                   "интеграция читает и пополняет архив, но не "
                                   "управляет доступом")
    key, prefix, key_hash = generate_api_key()
    row = ApiKey(name=payload.name, prefix=prefix, key_hash=key_hash,
                 role=payload.role, created_by=user.email)
    db.add(row)
    db.commit()
    db.refresh(row)
    audit.security(db, user, "apikey.create", f"{row.name} ({row.role.value})",
                   request=request, object_type="apikey", object_id=row.id)
    # Ключа в строке базы нет (только хэш), поэтому ответ собирается из строки
    # и значения ключа: model_validate(row) отверг бы запись без поля key.
    return ApiKeyCreated(**ApiKeyOut.model_validate(row).model_dump(), key=key)


@router.delete("/api-keys/{key_id}", status_code=204)
def revoke_key(key_id: str, request: Request, db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.admin))):
    """Ключ отзывается, а не удаляется: записи аудита ссылаются на него, и
    история обращений внешней системы должна оставаться читаемой."""
    row = db.get(ApiKey, key_id)
    if not row:
        raise HTTPException(status_code=404, detail="Ключ не найден")
    if row.revoked_at is None:
        row.revoked_at = datetime.utcnow()
        db.commit()
    audit.security(db, user, "apikey.revoke", row.name, request=request,
                   object_type="apikey", object_id=row.id)


# ---------- Журнал ИИ-агента (п. 12.6) ----------
@router.get("/agent-log", response_model=list[AgentLogOut])
def agent_log(user_email: str | None = None, refused: bool | None = None,
              limit: int = 100, db: Session = Depends(get_db),
              _: User = Depends(require_roles(Role.admin))):
    """Запросы к ассистенту и его ответы — для проверки обоснованности выводов."""
    q = db.query(AgentLog)
    if user_email:
        q = q.filter(AgentLog.user_email == user_email)
    if refused is not None:
        q = q.filter(AgentLog.refused.is_(refused))
    rows = q.order_by(AgentLog.ts.desc()).limit(min(limit, 500)).all()
    out = []
    for r in rows:
        # Источники хранятся строкой JSON — разбираем их до проверки схемой,
        # иначе она отвергает запись целиком.
        try:
            sources = json.loads(r.sources or "[]")
        except ValueError:
            sources = []
        out.append(AgentLogOut(
            id=r.id, ts=r.ts, user_email=r.user_email, question=r.question,
            answer=r.answer, confidence=r.confidence, route=r.route,
            refused=r.refused, cancelled=r.cancelled, duration_ms=r.duration_ms,
            sources=sources,
        ))
    return out


@router.get("/agent-log/stats")
def agent_stats(db: Session = Depends(get_db),
                _: User = Depends(require_roles(Role.admin))) -> dict:
    rows = db.query(AgentLog).all()
    if not rows:
        return {"total": 0, "refused": 0, "cancelled": 0, "avg_ms": 0,
                "by_confidence": {}, "by_route": {}}
    by_conf: dict[str, int] = {}
    by_route: dict[str, int] = {}
    for r in rows:
        by_conf[r.confidence or "—"] = by_conf.get(r.confidence or "—", 0) + 1
        by_route[r.route or "—"] = by_route.get(r.route or "—", 0) + 1
    return {
        "total": len(rows),
        "refused": sum(1 for r in rows if r.refused),
        "cancelled": sum(1 for r in rows if r.cancelled),
        "avg_ms": int(sum(r.duration_ms for r in rows) / len(rows)),
        "by_confidence": by_conf,
        "by_route": by_route,
    }
