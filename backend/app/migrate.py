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
]

_INDEXES: list[tuple[str, str, str]] = [
    ("ix_audit_log_ip_address", "audit_log", "ip_address"),
    ("ix_audit_log_action_type", "audit_log", "action_type"),
    ("ix_audit_log_archived", "audit_log", "archived"),
    ("ix_users_department_id", "users", "department_id"),
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
    if failed:
        log.warning("Схема БД синхронизирована частично: не выполнено %d операторов", failed)
    else:
        log.info("Схема БД синхронизирована")
