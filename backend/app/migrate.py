"""Лёгкие миграции схемы под требования ТС-176.

`Base.metadata.create_all()` создаёт новые таблицы, но не добавляет колонки в
уже существующие. Здесь — идемпотентные ALTER'ы (ADD COLUMN IF NOT EXISTS),
которые безопасно выполнять при каждом старте: на чистой базе они ничего не
делают, на существующей — дотягивают схему до актуальной.
"""
import logging

from sqlalchemy import text

from .db import engine

log = logging.getLogger("migrate")

# (таблица, колонка, SQL-тип с DEFAULT)
_COLUMNS: list[tuple[str, str, str]] = [
    # Аудиторский след в формате ТС-176 (разд. 14, п. 4)
    ("audit_log", "ip_address", "VARCHAR(64) NOT NULL DEFAULT ''"),
    ("audit_log", "user_agent", "VARCHAR(512) NOT NULL DEFAULT ''"),
    ("audit_log", "action_type", "VARCHAR(16) NOT NULL DEFAULT 'UPDATE'"),
    ("audit_log", "result", "BOOLEAN NOT NULL DEFAULT TRUE"),
    ("audit_log", "archived", "BOOLEAN NOT NULL DEFAULT FALSE"),
    # Оргструктура, право подписи и блокировка учётной записи
    ("users", "department_id", "UUID REFERENCES departments(id)"),
    ("users", "position", "VARCHAR(255) NOT NULL DEFAULT ''"),
    ("users", "can_sign", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("users", "failed_attempts", "INTEGER NOT NULL DEFAULT 0"),
    ("users", "locked_at", "TIMESTAMP"),
    ("users", "is_active", "BOOLEAN NOT NULL DEFAULT TRUE"),
    # Оптимистичная блокировка карточек (п. 6.4 ТС)
    ("documents", "version", "INTEGER NOT NULL DEFAULT 1"),
    ("cases", "version", "INTEGER NOT NULL DEFAULT 1"),
    # Атрибуты индексирования, качество OCR, дубли
    ("documents", "department_id", "UUID REFERENCES departments(id)"),
    ("documents", "page_count", "INTEGER"),
    ("documents", "ocr_confidence", "NUMERIC(5,2)"),
    ("documents", "needs_review", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("documents", "review_reason", "VARCHAR(512) NOT NULL DEFAULT ''"),
    ("documents", "duplicate_of_id", "UUID REFERENCES documents(id)"),
    # Жизненный цикл номенклатуры: уже заведённые статьи считаются действующими
    ("nomenclature", "status", "VARCHAR(32) NOT NULL DEFAULT 'Действующая'"),
    ("nomenclature", "department_id", "UUID REFERENCES departments(id)"),
    ("nomenclature", "updated_at", "TIMESTAMP"),
    ("nomenclature", "version", "INTEGER NOT NULL DEFAULT 1"),
    ("cases", "annotation", "TEXT NOT NULL DEFAULT ''"),
    ("cases", "department_id", "UUID REFERENCES departments(id)"),
    # ТС-176 п. 4.5: виды документов, принимаемые в дела статьи номенклатуры
    ("nomenclature", "doc_types", "JSON NOT NULL DEFAULT '[]'"),
    # ТС-176 п. 11.6–11.7: электронные копии, сверка с подлинником, акты их уничтожения
    ("documents", "copy_status", "VARCHAR(16) NOT NULL DEFAULT ''"),
    ("documents", "copy_checked_by", "VARCHAR(255) NOT NULL DEFAULT ''"),
    ("documents", "copy_checked_at", "TIMESTAMP"),
    ("documents", "copy_note", "TEXT NOT NULL DEFAULT ''"),
    ("documents", "copy_signer", "TEXT NOT NULL DEFAULT ''"),
    ("documents", "copy_cms_key", "VARCHAR(1024) NOT NULL DEFAULT ''"),
    ("destruction_acts", "kind", "VARCHAR(16) NOT NULL DEFAULT 'retention'"),
    ("destruction_acts", "commission_protocol", "VARCHAR(128) NOT NULL DEFAULT ''"),
    # ТС-176 разд. 13: виды обращений, критичность и сроки SLA
    ("support_tickets", "kind", "VARCHAR(32) NOT NULL DEFAULT 'question'"),
    ("support_tickets", "service", "VARCHAR(32) NOT NULL DEFAULT ''"),
    ("support_tickets", "criticality", "VARCHAR(16) NOT NULL DEFAULT 'medium'"),
    ("support_tickets", "reaction_due", "TIMESTAMP"),
    ("support_tickets", "resolution_due", "TIMESTAMP"),
    ("support_tickets", "reacted_at", "TIMESTAMP"),
    ("support_tickets", "resolved_at", "TIMESTAMP"),
    ("support_tickets", "closed_at", "TIMESTAMP"),
    ("support_tickets", "assignee", "VARCHAR(255) NOT NULL DEFAULT ''"),
    ("support_tickets", "reopen_count", "INTEGER NOT NULL DEFAULT 0"),
    # ТС-176 п. 4.10: руководитель подразделения — учётная запись; шаблон
    # маршрута и основание, по которому назначен согласующий шага
    ("departments", "head_user_id", "UUID REFERENCES users(id)"),
    ("approval_requests", "template_name", "VARCHAR(255) NOT NULL DEFAULT ''"),
    ("approval_steps", "basis", "VARCHAR(255) NOT NULL DEFAULT ''"),
]

_INDEXES: list[tuple[str, str, str]] = [
    ("ix_audit_log_ip_address", "audit_log", "ip_address"),
    ("ix_audit_log_action_type", "audit_log", "action_type"),
    ("ix_audit_log_archived", "audit_log", "archived"),
    ("ix_users_department_id", "users", "department_id"),
    ("ix_documents_department_id", "documents", "department_id"),
    ("ix_documents_needs_review", "documents", "needs_review"),
    ("ix_documents_duplicate_of_id", "documents", "duplicate_of_id"),
    ("ix_nomenclature_status", "nomenclature", "status"),
    ("ix_nomenclature_department_id", "nomenclature", "department_id"),
    ("ix_documents_copy_status", "documents", "copy_status"),
]

# Неизменность аудиторского следа на уровне СУБД (ТС-176 разд. 14: «двойная
# защита от удаления информации о логировании», «неизменность аудиторского
# следа на организационном и техническом уровне»). Это вторая линия за
# приложением, где удаления журнала нет вовсе: даже прямой SQL от имени
# приложения не удалит и не исправит запись. Разрешён ровно один вид правки —
# перенос в архив (archived: false → true) без изменения остальных полей.
# ВАЖНО: будущая миграция, которой понадобится UPDATE по audit_log, должна
# учитывать этот триггер.
_AUDIT_GUARD_FN = """
CREATE OR REPLACE FUNCTION audit_log_guard() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Удаление записей аудиторского следа запрещено';
    END IF;
    IF OLD.archived OR NOT NEW.archived
       OR (to_jsonb(NEW) - 'archived') IS DISTINCT FROM (to_jsonb(OLD) - 'archived') THEN
        RAISE EXCEPTION 'Запись аудиторского следа неизменна: допускается только перенос в архив';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""

_AUDIT_TRUNCATE_FN = """
CREATE OR REPLACE FUNCTION audit_log_no_truncate() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Очистка аудиторского следа запрещена';
END;
$$ LANGUAGE plpgsql
"""

# Триггеры создаются внутри DO-блока с проверкой существования, а не парой
# DROP + CREATE: между ними журнал на мгновение оставался бы без защиты.
_AUDIT_GUARD_TRIGGER = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                   WHERE tgname = 'audit_log_guard' AND tgrelid = to_regclass('audit_log')) THEN
        CREATE TRIGGER audit_log_guard BEFORE UPDATE OR DELETE ON audit_log
            FOR EACH ROW EXECUTE FUNCTION audit_log_guard();
    END IF;
END $$
"""

_AUDIT_TRUNCATE_TRIGGER = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                   WHERE tgname = 'audit_log_no_truncate' AND tgrelid = to_regclass('audit_log')) THEN
        CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log
            FOR EACH STATEMENT EXECUTE FUNCTION audit_log_no_truncate();
    END IF;
END $$
"""

# Прочие идемпотентные операторы, выполняемые после колонок и индексов.
_DDL: list[tuple[str, str]] = [
    # Роль «аудитор ИБ» (ТС-176 разд. 14 п. 5.1). Тип создан SQLAlchemy для
    # колонок users.role и api_keys.role; на новой базе значение уже есть.
    ("значение роли auditor", "ALTER TYPE role ADD VALUE IF NOT EXISTS 'auditor'"),
    ("функция защиты журнала", _AUDIT_GUARD_FN),
    ("функция запрета очистки журнала", _AUDIT_TRUNCATE_FN),
    ("триггер защиты журнала", _AUDIT_GUARD_TRIGGER),
    ("триггер запрета очистки журнала", _AUDIT_TRUNCATE_TRIGGER),
]


def _apply(conn, sql: str, what: str) -> bool:
    """Выполняет один DDL в собственной транзакции.

    Каждый оператор коммитится отдельно: в PostgreSQL любая ошибка переводит
    транзакцию в состояние aborted, поэтому общий `engine.begin()` на весь
    список означал бы, что первый же сбой отменяет и все последующие, и все
    уже удавшиеся операторы — молча, с записью «схема синхронизирована».
    """
    try:
        with conn.begin():
            conn.execute(text(sql))
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("migrate: %s — пропущено: %s", what, exc)
        return False


def run() -> None:
    """Дотягивает схему. Ошибка отдельного ALTER не должна ронять запуск."""
    failed = 0
    with engine.connect() as conn:
        for table, column, ddl in _COLUMNS:
            if not _apply(
                conn,
                f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{column}" {ddl}',
                f"{table}.{column}",
            ):
                failed += 1
        for name, table, column in _INDEXES:
            if not _apply(
                conn,
                f'CREATE INDEX IF NOT EXISTS "{name}" ON "{table}" ("{column}")',
                f"индекс {name}",
            ):
                failed += 1
        for what, sql in _DDL:
            if not _apply(conn, sql, what):
                failed += 1
    if failed:
        log.warning("Схема БД синхронизирована частично: не выполнено %d операторов", failed)
    else:
        log.info("Схема БД синхронизирована")
