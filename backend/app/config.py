from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "e-archive"
    # Версия приложения. Её смена при старте фиксируется в аудиторском следе как
    # установка обновления (ТС-176 разд. 14 п. 6); задаётся при сборке образа.
    APP_VERSION: str = "0.1.0"
    # Ключ подписи токенов. Значение по умолчанию намеренно нерабочее: с общим
    # известным ключом любой желающий подписывает себе токен администратора.
    # На старте значение проверяется (см. validate_secrets) — в промышленном
    # режиме сервис не поднимется, пока ключ не задан.
    SECRET_KEY: str = "change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    ALGORITHM: str = "HS256"
    # dev — разрешены значения по умолчанию и открытый CORS (локальная работа);
    # production — небезопасные значения останавливают запуск.
    ENVIRONMENT: Literal["dev", "production"] = "dev"
    # Origin'ы, которым разрешён доступ к API из браузера. Через запятую.
    # Пустое значение в режиме dev означает «любой».
    CORS_ORIGINS: str = ""
    # Редакция под заказчика (см. app/edition.py): название, оформление и состав
    # меню. base — общая; kazpost — АО «Казпочта» по ТС-176.
    EDITION: Literal["base", "kazpost"] = "base"
    # Разделы, которые не показывать в этом развёртывании, через запятую
    # (например, search — если в контуре нет сервера языковой модели).
    EDITION_DISABLED_MODULES: str = ""

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

    # ---- Переранжирование результатов поиска (cross-encoder) ----
    # Кросс-энкодер читает пару «запрос + фрагмент» вместе и исправляет ошибки
    # первых двух этапов поиска. Модель мультиязычная, работает на CPU.
    RERANK_ENABLED: bool = True
    RERANK_MODEL: str = "jinaai/jina-reranker-v2-base-multilingual"
    # Сколько фрагментов переранжировать: больше — точнее, но дольше
    # (ориентир: ~2,5 с на 15 фрагментов при CPU-инференсе).
    RERANK_CANDIDATES: int = 20

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
    # Предел распознаваемых страниц на документ. Страницы растрируются по одной,
    # поэтому память от числа страниц не зависит; прежний предел в 30 страниц
    # молча оставлял без текста всё дело после 30-го листа.
    OCR_MAX_PAGES: int = 500
    # Документ с уверенностью распознавания ниже порога попадает в перечень
    # требующих ручной проверки (ТЗ АГП п. 12.5).
    OCR_REVIEW_CONFIDENCE: float = 70.0
    # Сходство текстов (Жаккар по 5-словным фрагментам), начиная с которого
    # документ считается почти-дублем: повторный скан того же листа.
    NEAR_DUPLICATE_THRESHOLD: float = 0.85
    # Более слабое сходство дублем не считается, но выносится на ручную
    # проверку: так пересканированный с правкой лист не теряется молча.
    SIMILAR_REVIEW_THRESHOLD: float = 0.7
    # Приводить к PDF/A с текстовым слоем все распознанные документы, а не только
    # постоянного хранения: результатом оцифровки ТЗ называет именно PDF/A (п. 3).
    PDFA_FOR_ALL: bool = True
    # Если VLM-сервер недоступен (не поднят / нет VRAM) — не терять приём
    # документа, а распознать классическим движком.
    OCR_FALLBACK_TESSERACT: bool = True

    # ---- LLM (Ollama, local RAG) ----
    OLLAMA_HOST: str = "ollama"
    OLLAMA_PORT: int = 11434
    OLLAMA_MODEL: str = "qwen2.5:7b"
    # Документов в контексте ответа. Единица поиска — чанк, поэтому документов
    # можно брать больше: контекст не раздувается целыми делами.
    RAG_TOP_K: int = 6
    RAG_CONTEXT_CHARS: int = 2000
    # Порог релевантности относительно лучшего попадания: хвост слабых
    # совпадений только зашумляет контекст.
    RAG_MIN_SCORE_RATIO: float = 0.35
    # Переформулировать уточняющий вопрос («а на какой срок?») в самостоятельный
    # запрос по истории диалога — иначе местоимения ищутся буквально.
    RAG_QUERY_REWRITE: bool = True
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
    # Доверять ли заголовку X-Forwarded-For при записи IP в аудит. Включать
    # ТОЛЬКО если перед backend стоит обратный прокси, который этот заголовок
    # перезаписывает. Иначе адрес в журнале подделывается одним заголовком в
    # запросе, а по ТС-176 это обязательное поле аудиторского следа.
    TRUST_PROXY_HEADERS: bool = False

    # ---- SLA технической поддержки (ТС-176 разд. 13) ----
    # Сроки высокого, среднего и низкого уровней критичности считаются в рабочее
    # время: будни с SLA_WORKDAY_START до SLA_WORKDAY_END по местному времени.
    SLA_UTC_OFFSET_HOURS: int = 5
    SLA_WORKDAY_START: int = 9
    SLA_WORKDAY_END: int = 18
    # Кому сообщать об инцидентах ИБ (разд. 14 п. 9), через запятую; пусто —
    # всем активным администраторам.
    SECURITY_INCIDENT_EMAILS: str = ""

    # ---- Проверка ЭЦП (ТС-176 разд. 14 п. 7, Правила № 1187) ----
    # local — встроенная проверка RSA без цепочки и отзыва (подписи ГОСТ помечаются
    # «не поддерживается»); ncanode — проверка через NCANode: ГОСТ 34.10-2015,
    # цепочка до корневых сертификатов НУЦ РК, отзыв по OCSP/CRL.
    SIGNATURE_VERIFIER: Literal["local", "ncanode"] = "local"
    NCANODE_URL: str = "http://ncanode:14579"
    NCANODE_TIMEOUT: int = 15
    SIGNATURE_REVOCATION_CHECK: str = "OCSP"

    # ---- Вход по ключам доступа WebAuthn (ТС-176 разд. 14 п. 4.2) ----
    # Биометрия или PIN телефона вместо пароля. RP ID — домен, на котором
    # открывается система, без схемы и порта: ключ, созданный для одного домена,
    # на другом не работает. ORIGINS — адреса страницы входа через запятую.
    # Браузер разрешает WebAuthn только по HTTPS (или на localhost).
    WEBAUTHN_ENABLED: bool = False
    WEBAUTHN_RP_ID: str = "localhost"
    WEBAUTHN_RP_NAME: str = "Электронный архив"
    WEBAUTHN_ORIGINS: str = "http://localhost:5173,http://localhost:8080"

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

    @property
    def cors_origins(self) -> list[str]:
        """Список разрешённых origin'ов. В dev при пустой настройке — «любой»,
        что удобно локально; в production пустой список означает, что браузерные
        запросы с других origin'ов не принимаются вовсе."""
        listed = [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]
        if listed:
            return listed
        return ["*"] if self.ENVIRONMENT == "dev" else []

    def unsafe_defaults(self) -> list[str]:
        """Небезопасные значения, оставшиеся от шаблона конфигурации."""
        problems = []
        if self.SECRET_KEY.strip() in ("", "change-me", "change-me-to-a-long-random-string"):
            problems.append("SECRET_KEY не задан — токены доступа подделываются")
        elif len(self.SECRET_KEY) < 32:
            problems.append("SECRET_KEY короче 32 символов")
        if self.FIRST_ADMIN_PASSWORD == "admin12345":
            problems.append("FIRST_ADMIN_PASSWORD оставлен демонстрационным")
        if self.POSTGRES_PASSWORD in ("earchive", "postgres"):
            problems.append("POSTGRES_PASSWORD оставлен демонстрационным")
        if self.MINIO_ROOT_PASSWORD == "minioadmin123":
            problems.append("MINIO_ROOT_PASSWORD оставлен демонстрационным")
        # Проверяем именно заданное значение, а не результат cors_origins:
        # в production «*» получается только если оператор указал его явно —
        # при пустой настройке список и так пуст.
        if self.ENVIRONMENT == "production" and "*" in self.CORS_ORIGINS:
            problems.append("CORS_ORIGINS содержит «*» — разрешён любой источник")
        # Ключ доступа привязан к домену: с RP ID localhost вход по биометрии в
        # контуре не заработает ни у кого, и узнали бы об этом только пользователи.
        if self.ENVIRONMENT == "production" and self.WEBAUTHN_ENABLED:
            if self.WEBAUTHN_RP_ID.strip() in ("", "localhost"):
                problems.append("WEBAUTHN_RP_ID не задан — ключи доступа привязаны к localhost")
            if not self.WEBAUTHN_ORIGINS.strip() or "localhost" in self.WEBAUTHN_ORIGINS:
                problems.append("WEBAUTHN_ORIGINS не задан — укажите адрес страницы входа")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
