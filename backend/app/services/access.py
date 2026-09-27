"""Доступ к документам по категориям (модуль «Администрирование»:
«настройка параметров доступа к документам в зависимости от категорий и типов
документов»).

Правило: у роли без записей в doc_type_access ограничений нет; как только для
роли заведена хотя бы одна категория, ей видны только документы перечисленных
категорий. Администратор видит всё всегда — иначе он мог бы закрыть доступ сам
себе и не иметь способа его вернуть. Аудитор ИБ не видит ни одной категории
(ТС-176 разд. 14 п. 5.1: журналы доступны, содержимое документов — нет).
"""
from sqlalchemy.orm import Query, Session

from ..models import (
    AuditActionType, DOC_TYPE_GROUPS, DocType, DocTypeAccess, Document, Role, User,
)
from . import audit


def allowed_types(db: Session, user: User) -> set[DocType] | None:
    """Разрешённые пользователю типы документов; None — без ограничений."""
    if user is None or user.role == Role.admin:
        return None
    if user.role == Role.auditor:
        return set()
    rows = db.query(DocTypeAccess).filter(DocTypeAccess.role == user.role.value).all()
    if not rows:
        return None
    types: set[DocType] = set()
    for r in rows:
        types.update(DOC_TYPE_GROUPS.get(r.doc_group, []))
    return types


def apply(query: Query, db: Session, user: User) -> Query:
    """Сужает выборку документов до разрешённых категорий."""
    types = allowed_types(db, user)
    if types is None:
        return query
    return query.filter(Document.doc_type.in_(list(types)))


def can_see(db: Session, user: User, doc: Document, request=None) -> bool:
    """Виден ли документ пользователю.

    С переданным запросом отказ пишется в аудиторский след: обращение к
    закрытому документу — событие для ежеквартальной информации о попытках
    несанкционированного доступа (ТС-176 разд. 14 п. 8)."""
    types = allowed_types(db, user)
    visible = types is None or doc.doc_type in types
    if not visible and request is not None:
        audit.record(db, user, "access.denied", "document", doc.id,
                     "категория документа закрыта для роли", request=request,
                     action_type=AuditActionType.read, result=False)
    return visible


def allowed_type_values(db: Session, user: User) -> list[str] | None:
    """Те же разрешения в виде названий типов — для фильтра поискового индекса,
    где doc_type хранится строкой."""
    types = allowed_types(db, user)
    return None if types is None else sorted(t.value for t in types)
