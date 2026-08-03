import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import Base, engine, SessionLocal
from .models import User, Role
from .security import hash_password
import threading

from .services import storage, search, embeddings, llm
from .routers import (
    auth, documents, search as search_router, signatures, stats,
    nomenclature, cases, forms, lifecycle, issues,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")

app = FastAPI(title=settings.PROJECT_NAME, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    _bootstrap_admin()
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


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": settings.PROJECT_NAME}
