from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "e-archive"
    SECRET_KEY: str = "change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    ALGORITHM: str = "HS256"

    POSTGRES_USER: str = "earchive"
    POSTGRES_PASSWORD: str = "earchive"
    POSTGRES_DB: str = "earchive"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432

    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ROOT_USER: str = "minioadmin"
    MINIO_ROOT_PASSWORD: str = "minioadmin123"
    MINIO_BUCKET: str = "archive"
    MINIO_SECURE: bool = False
    MINIO_RETENTION_DAYS: int = 3650

    OPENSEARCH_HOST: str = "opensearch"
    OPENSEARCH_PORT: int = 9200
    OPENSEARCH_INDEX: str = "documents"

    CLAMAV_HOST: str = "clamav"
    CLAMAV_PORT: int = 3310

    EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    EMBEDDING_DIM: int = 384

    # ---- OCR ----
    # unlimited — VLM baidu/Unlimited-OCR через OpenAI-совместимый сервер
    #             (vLLM/SGLang, нужен GPU); tesseract — классический движок.
    # По умолчанию tesseract: работает на любой машине без GPU. Unlimited-OCR
    # (VLM baidu/Unlimited-OCR) — опция для машины помощнее: OCR_ENGINE=unlimited
    # + `docker compose --profile ocr up -d ocr`.
    # Literal, а не str: опечатка в .env роняет запуск, а не молча меняет движок.
    OCR_ENGINE: Literal["unlimited", "tesseract"] = "tesseract"
    OCR_LANGUAGES: str = "rus+kaz+eng"        # только для tesseract
    OCR_SERVICE_URL: str = "http://ocr:10000/v1"
    OCR_MODEL: str = "Unlimited-OCR"
    OCR_TIMEOUT: int = 300
    OCR_MAX_TOKENS: int = 32768               # = контекст модели, см. --max-model-len
    OCR_DPI: int = 200
    OCR_MAX_PAGES: int = 30
    # Если VLM-сервер недоступен (не поднят / нет VRAM) — не терять приём
    # документа, а распознать классическим движком.
    OCR_FALLBACK_TESSERACT: bool = True

    # ---- LLM (Ollama, local RAG) ----
    OLLAMA_HOST: str = "ollama"
    OLLAMA_PORT: int = 11434
    OLLAMA_MODEL: str = "qwen2.5:7b"
    RAG_TOP_K: int = 4
    RAG_CONTEXT_CHARS: int = 2000
    # Autonomous tool-calling loop — reliable only with capable models (7b+).
    # For small local models keep off: retrieval-augmented answering is used.
    AGENT_TOOL_LOOP: bool = False

    # ---- Информационная безопасность (ТС-176, раздел 14) ----
    # п. 4.4: учётная запись блокируется после трёх неверных вводов пароля
    LOGIN_MAX_ATTEMPTS: int = 3
    # п. 3: второй фактор — код на email при входе с нового устройства
    # либо при наличии второй одновременной сессии
    TWOFA_ENABLED: bool = True
    TWOFA_CODE_TTL_MINUTES: int = 10
    TWOFA_MAX_ATTEMPTS: int = 3
    # п. 2 требований к аудиту: ≥3 мес. оперативного доступа, ≥1 года архивного
    AUDIT_OPERATIONAL_DAYS: int = 90
    AUDIT_ARCHIVE_DAYS: int = 365

    # ---- SMTP для кодов второго фактора ----
    # Если хост не задан, код второго фактора пишется в журнал сервера
    # (режим разработки) — почта наружу не отправляется.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "e-archive <no-reply@earchive.kz>"
    SMTP_TLS: bool = True

    FIRST_ADMIN_EMAIL: str = "admin@earchive.kz"
    FIRST_ADMIN_PASSWORD: str = "admin12345"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
