import logging

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .config import settings
from .db import Base, engine, SessionLocal
from .models import User, Role
from .security import hash_password
import threading

from . import edition, migrate
from .services import storage, search, embeddings, llm, reranker
from .routers import (
    auth, documents, search as search_router, signatures, stats,
    nomenclature, cases, forms, lifecycle, issues,
    audit as audit_router, enterprise, reports, approvals, exports,
    requests as requests_router, inventories, attachments, imports, support, admin,
    scanning, ecopies, dictionaries as dictionaries_router, nto as nto_router,
    passkeys as passkeys_router,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")

app = FastAPI(title=settings.PROJECT_NAME, version="0.1.0")

# Открытый список origin'ов вместе с allow_credentials — небезопасное и, по
# спецификации CORS, недействующее сочетание: браузер отклоняет «*» для запросов
# с учётными данными. В production список задаётся явно через CORS_ORIGINS.
_origins = settings.cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=(_origins != ["*"]),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(search_router.router)
app.include_router(signatures.router)
app.include_router(stats.router)
app.include_router(nomenclature.router)
app.include_router(cases.router)
app.include_router(forms.router)
app.include_router(lifecycle.router)
app.include_router(issues.router)
# Модули по ТС-176: аудиторский след, «Предприятие», отчёты, согласование, XML
app.include_router(audit_router.router)
app.include_router(enterprise.router)
app.include_router(reports.router)
app.include_router(approvals.router)
app.include_router(exports.router)
# Модули по ТЗ «Азиатский Газопровод»: архивные запросы, описи дел, вложения,
# импорт пакетов оцифровки, обращения в поддержку, администрирование
app.include_router(requests_router.router)
app.include_router(inventories.router)
app.include_router(attachments.router)
app.include_router(imports.router)
app.include_router(support.router)
app.include_router(admin.router)
# Модуль «Сканирование» по ТС-176 п. 4.5 и учёт работ оцифровки
app.include_router(scanning.router)
# Электронные копии: сверка с подлинником, удостоверение ЭЦП, акты уничтожения (п. 11.6–11.7)
app.include_router(ecopies.router)
# Редактируемые справочники (п. 4.9)
app.include_router(dictionaries_router.router)
# НТО, протоколы ЭК/ЦЭК/ЭПК, передача дел в госархив (п. 5.3, 8.2, 10.2–10.5)
app.include_router(nto_router.router)
# Вход по ключам доступа WebAuthn — биометрия в мобильной версии (разд. 14 п. 4.2)
app.include_router(passkeys_router.router)


def _bootstrap_admin() -> None:
    db = SessionLocal()
    try:
        exists = db.query(User).filter(User.email == settings.FIRST_ADMIN_EMAIL).first()
        if not exists:
            db.add(
                User(
                    email=settings.FIRST_ADMIN_EMAIL,
                    full_name="Администратор",
                    role=Role.admin,
                    hashed_password=hash_password(settings.FIRST_ADMIN_PASSWORD),
                )
            )
            db.commit()
            log.info("Bootstrap admin created: %s", settings.FIRST_ADMIN_EMAIL)
    finally:
        db.close()


def _check_secrets() -> None:
    """Не даёт запустить промышленный контур с демонстрационными секретами.

    В dev — предупреждение в журнале: локальная работа не должна требовать
    настройки. В production — отказ стартовать: система с общеизвестным ключом
    подписи или паролем администратора не защищает архив ни от кого.
    """
    problems = settings.unsafe_defaults()
    if not problems:
        return
    listed = "; ".join(problems)
    if settings.ENVIRONMENT == "production":
        raise RuntimeError(
            "Небезопасная конфигурация, запуск остановлен: " + listed
        )
    log.warning("НЕБЕЗОПАСНЫЕ ЗНАЧЕНИЯ ПО УМОЛЧАНИЮ (допустимо только "
                "для локальной работы): %s", listed)


@app.on_event("startup")
def on_startup() -> None:
    _check_secrets()
    Base.metadata.create_all(bind=engine)
    # Новые колонки в существующих таблицах create_all не добавляет — дотягиваем
    # схему отдельно (идемпотентно, безопасно при каждом старте).
    try:
        migrate.run()
    except Exception:  # noqa: BLE001
        log.exception("Миграция схемы не выполнена")
    _bootstrap_admin()
    # Начальные значения справочников (ТС-176 п. 4.9) — только в пустые.
    from .services import dictionaries
    db = SessionLocal()
    try:
        dictionaries.seed(db)
    except Exception:  # noqa: BLE001
        log.exception("Справочники не заполнены начальными значениями")
    finally:
        db.close()
    # Установка обновлений и изменение параметров — события аудиторского следа
    # (ТС-176 разд. 14 п. 6): сверяем состояние с последним снимком в журнале.
    from .services import system_state
    system_state.record_startup()
    try:
        storage.ensure_bucket()
    except Exception:  # noqa: BLE001
        log.exception("MinIO bucket init failed (will retry lazily)")
    try:
        search.ensure_index()
    except Exception:  # noqa: BLE001
        log.exception("OpenSearch index init failed (will retry lazily)")
    try:
        embeddings.warmup()
        log.info("Embedding model ready")
    except Exception:  # noqa: BLE001
        log.exception("Embedding warmup failed (will load lazily)")

    # Pull the LLM in the background — it can take minutes and must not block
    # startup or health checks. The chat endpoint reports readiness meanwhile.
    def _pull_llm():
        try:
            llm.ensure_model()
        except Exception:  # noqa: BLE001
            log.exception("Ollama model pull failed (will retry on demand)")

    threading.Thread(target=_pull_llm, daemon=True).start()
    threading.Thread(target=_reindex_missing, daemon=True).start()
    # Кросс-энкодер грузится ~1 мин при первом обращении — прогреваем заранее,
    # чтобы этого не ждал первый же поисковый запрос пользователя.
    threading.Thread(target=reranker.warmup, daemon=True).start()


def _reindex_missing() -> None:
    """Досоздаёт в поисковом индексе документы, которых там нет.

    Сверяем состав индекса с базой, а не просто «пуст ли индекс»: индексация
    может оборваться на середине (схема сменилась, том потерян, процесс убит
    по памяти на длинном документе), и тогда часть документов молча выпадает
    из поиска. Индекс — производные данные, источник истины в БД и хранилище,
    поэтому досборка безопасна и идемпотентна.
    """
    from .models import Document, DocStatus
    from .ingest import _index_payload

    db = SessionLocal()
    try:
        docs = (db.query(Document)
                .filter(Document.status == DocStatus.ready,
                        Document.destroyed_at.is_(None))
                .all())
        if not docs:
            return
        present = search.indexed_doc_ids()
        if present is None:
            # Состав индекса неизвестен (OpenSearch ещё не поднялся). Считать в
            # этом случае, что не проиндексировано ничего, нельзя: каждый такой
            # старт заново пересчитывал бы эмбеддинги всего архива.
            log.warning("Состав поискового индекса недоступен — досборку пропускаю")
            return
        missing = [d for d in docs if d.id not in present]
        if not missing:
            return
        log.info("В индексе нет %d из %d документов — досоздаю",
                 len(missing), len(docs))
        search.reindex_all([_index_payload(d) for d in missing])
    except Exception:  # noqa: BLE001
        log.exception("Переиндексация не выполнена")
    finally:
        db.close()


@app.get("/api/meta/edition")
def edition_profile() -> dict:
    """Профиль редакции для интерфейса. Публичный: страница входа оформляется
    по редакции, а токена у неё ещё нет. Секретов профиль не содержит."""
    return edition.profile()


@app.get("/api/health")
def health() -> dict:
    """Живость процесса. Отвечает всегда — по этой пробе оркестратор понимает,
    что процесс не завис, и не должен перезапускать сервис из-за недоступности
    внешней зависимости."""
    return {"status": "ok", "service": settings.PROJECT_NAME}


@app.get("/api/health/ready")
def readiness(response: Response) -> dict:
    """Готовность обслуживать запросы: проверяются зависимости, без которых
    приём и поиск документов не работают. Прежняя проба отвечала «ok» даже при
    лежащей базе, и внешне сервис выглядел исправным.

    Модель ИИ в готовность не входит намеренно: пока она грузится, архив
    полностью работоспособен, а вопросы к ассистенту отвечаются по базе.
    """
    checks = _readiness_checks()
    ready = all(checks.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"ready": ready, "checks": checks, "llm_ready": llm.is_ready()}


def _readiness_checks() -> dict[str, bool]:
    """Зависимости, без которых приём и поиск документов не работают."""
    checks: dict[str, bool] = {}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["postgres"] = True
    except Exception:  # noqa: BLE001
        checks["postgres"] = False
    try:
        checks["opensearch"] = bool(search.ping())
    except Exception:  # noqa: BLE001
        checks["opensearch"] = False
    try:
        checks["storage"] = bool(storage.ping())
    except Exception:  # noqa: BLE001
        checks["storage"] = False
    return checks


@app.on_event("startup")
def start_availability_sampler() -> None:
    """Поминутные отметки доступности для SLA (ТС-176 п. 13.1.2.2). Проверка —
    та же, что у пробы готовности: система доступна, когда работают приём и
    поиск документов."""
    from .services import availability

    threading.Thread(
        target=availability.run_sampler,
        args=(lambda: all(_readiness_checks().values()),),
        daemon=True,
    ).start()
