"""«Процент доступности» системы (ТС-176 п. 13.1.2.2): A — минуты доступности
за отчётный период, B — все минуты периода.

Раз в минуту процесс проверяет готовность (база, поиск, хранилище — те же
проверки, что у пробы /api/health/ready) и записывает отметку. Минута без
отметки — недоступность: если сервис лежал, отметить свою доступность ему было
некому. Поэтому доступность не завышается ни при падении процесса, ни при
недоступной базе.
"""
import logging
import time as _time
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from ..db import SessionLocal
from ..models import AvailabilitySample

log = logging.getLogger("availability")


def record(ok: bool, minute: datetime | None = None) -> None:
    minute = (minute or datetime.utcnow()).replace(second=0, microsecond=0)
    db = SessionLocal()
    try:
        db.add(AvailabilitySample(minute=minute, ok=ok))
        db.commit()
    except IntegrityError:
        # Отметка за эту минуту уже есть: несколько процессов или перезапуск.
        db.rollback()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.warning("Отметка доступности за %s не записана", minute)
    finally:
        db.close()


def run_sampler(check) -> None:
    """Бесконечный цикл отметок; запускается в фоновом потоке при старте."""
    while True:
        try:
            ok = bool(check())
        except Exception:  # noqa: BLE001
            ok = False
        record(ok)
        _time.sleep(max(1, 60 - datetime.utcnow().second))


def summary(db, start: datetime, end: datetime) -> dict:
    """Минуты периода [start, end) и минуты доступности в нём. Будущее время
    периода в расчёт не входит."""
    now = datetime.utcnow().replace(second=0, microsecond=0)
    end = min(end, now)
    total = max(0, int((end - start).total_seconds() // 60))
    available = (db.query(func.count(AvailabilitySample.id))
                 .filter(AvailabilitySample.minute >= start,
                         AvailabilitySample.minute < end,
                         AvailabilitySample.ok.is_(True))
                 .scalar()) or 0
    first = db.query(func.min(AvailabilitySample.minute)).scalar()
    return {
        "total_minutes": total,
        "available_minutes": int(available),
        # Минуты до первой отметки — время до ввода системы в эксплуатацию:
        # период отчёта не должен начинаться раньше.
        "first_sample": first.isoformat() if first else None,
    }
