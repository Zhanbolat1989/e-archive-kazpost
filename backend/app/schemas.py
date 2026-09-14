from datetime import datetime, date
from typing import Annotated, Optional
from pydantic import AfterValidator, BaseModel, EmailStr, Field

from .models import (
    Role, DocStatus, SignatureStatus, DocType, CaseStatus, ActStatus, IssueStatus,
)


# ---- Auth ----
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginResponse(BaseModel):
    """Ответ на вход: либо токен, либо требование второго фактора (п. 3.3 ТС)."""
    access_token: Optional[str] = None
    token_type: str = "bearer"
    twofa_required: bool = False
    challenge_id: Optional[str] = None
    # email — код отправлен письмом; server_log — SMTP не настроен, код в журнале
    delivery: Optional[str] = None


class TwoFactorVerify(BaseModel):
    challenge_id: str
    code: str


# ---- Ключи доступа WebAuthn (ТС-176 разд. 14 п. 4.2) ----
class PasskeyOut(BaseModel):
    id: str
    name: str
    created_at: datetime
    last_used_at: Optional[datetime] = None
    backed_up: bool = False

    class Config:
        from_attributes = True


class PasskeyRegister(BaseModel):
    challenge_id: str
    credential: dict                     # PublicKeyCredential в JSON (base64url)
    name: str = Field(default="", max_length=255)


class PasskeyLogin(BaseModel):
    challenge_id: str
    credential: dict


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str = ""
    role: Role = Role.archivist
    position: str = ""
    department_id: Optional[str] = None
    can_sign: bool = False


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[Role] = None
    position: Optional[str] = None
    department_id: Optional[str] = None
    can_sign: Optional[bool] = None
    is_active: Optional[bool] = None


class ProfileUpdate(BaseModel):
    """Личный кабинет (п. 4.7 ТС): пользователь правит только свои данные."""
    full_name: Optional[str] = None
    position: Optional[str] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: Role
    position: str = ""
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    can_sign: bool = False
    is_active: bool = True
    locked: bool = False

    class Config:
        from_attributes = True


class OrganizationIn(BaseModel):
    """Модуль «Предприятие» (п. 4.8 ТС)."""
    name: str
    short_name: str = ""
    bin: str = ""
    address: str = ""
    phone: str = ""
    email: str = ""
    head_name: str = ""
    head_position: str = ""


class OrganizationOut(OrganizationIn):
    id: str
    updated_at: datetime

    class Config:
        from_attributes = True


class DepartmentIn(BaseModel):
    name: str
    index: str = ""
    parent_id: Optional[str] = None
    head_name: str = ""
    head_position: str = ""
    # Руководитель как учётная запись: его подставляют маршруты согласования
    # (п. 4.10 ТС). ФИО и должность выше — реквизиты для печатных форм.
    head_user_id: Optional[str] = None


class DepartmentOut(DepartmentIn):
    id: str
    users_count: int = 0
    head_user_email: str = ""

    class Config:
        from_attributes = True


class ApprovalStepIn(BaseModel):
    approver_email: str
    order_no: int = 1


class ApprovalCreate(BaseModel):
    """Маршрут согласования карточки дела, документа или статьи номенклатуры
    (п. 4.10 ТС): по шаблону оргструктуры либо перечнем согласующих."""
    object_type: str            # document | case | nomenclature
    object_id: str
    steps: list[ApprovalStepIn] = []
    template_id: Optional[str] = None


class ApprovalPlanStep(BaseModel):
    """Согласующий, подставленный по шаблону, — до запуска маршрута."""
    order_no: int
    approver_email: str
    approver_name: str
    basis: str = ""


class RouteStep(BaseModel):
    kind: str                   # head | parent_head | department_head | user
    value: str = ""             # id подразделения или email сотрудника


class RouteTemplateIn(BaseModel):
    """Шаблон маршрута согласования по оргструктуре (п. 4.10 ТС)."""
    name: str = Field(min_length=1, max_length=255)
    object_type: str = ""       # пусто — для любого объекта
    steps: list[RouteStep]
    is_active: bool = True


class RouteTemplateOut(RouteTemplateIn):
    id: str

    class Config:
        from_attributes = True


class DictionaryEntryIn(BaseModel):
    """Значение редактируемого справочника (п. 4.9 ТС)."""
    value: str = Field(min_length=1, max_length=255)
    sort_order: int = 0


class DictionaryEntryUpdate(BaseModel):
    value: Optional[str] = Field(default=None, min_length=1, max_length=255)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class DictionaryEntryOut(BaseModel):
    id: str
    value: str
    sort_order: int
    is_active: bool

    class Config:
        from_attributes = True


class ApprovalDecision(BaseModel):
    approve: bool
    comment: str = ""


class ApprovalStepOut(BaseModel):
    id: str
    order_no: int
    approver_email: str
    approver_name: str
    basis: str = ""             # основание назначения: «Руководитель: …»
    status: str
    comment: str
    decided_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ApprovalOut(BaseModel):
    id: str
    object_type: str
    object_id: str
    title: str
    template_name: str = ""
    status: str
    created_by: str
    created_at: datetime
    closed_at: Optional[datetime] = None
    steps: list[ApprovalStepOut] = []

    class Config:
        from_attributes = True


class AuditOut(BaseModel):
    """Запись аудиторского следа в формате раздела 14 ТС."""
    id: str
    ts: datetime
    user_email: str
    action: str
    action_type: str
    object_type: str
    object_id: str
    detail: str
    ip_address: str
    user_agent: str
    result: bool
    archived: bool

    class Config:
        from_attributes = True


class SessionOut(BaseModel):
    """Текущая сессия пользователя (п. 4.9 ТС)."""
    id: str
    user_email: Optional[str] = None
    ip_address: str
    user_agent: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    current: bool = False

    class Config:
        from_attributes = True


# ---- Documents ----
class DocumentOut(BaseModel):
    id: str
    title: str
    description: str
    fond: str
    opis: str
    delo: str
    doc_type: DocType
    doc_number: str
    counterparty: str
    doc_date: Optional[date]
    amount: Optional[float]
    currency: str
    original_filename: str
    content_type: str
    size: int
    checksum_sha256: str
    status: DocStatus
    status_detail: str
    signature_status: SignatureStatus
    signer_info: str
    case_id: Optional[str] = None
    retention_label: str = ""
    retention_until: Optional[date] = None
    permanent: bool = False
    destroyed_at: Optional[date] = None
    cadastral_number: str = ""
    real_estate_address: str = ""
    real_estate_area: Optional[float] = None
    replaces_id: Optional[str] = None
    superseded_at: Optional[date] = None
    version: int = 1
    # Атрибуты индексирования и контроль качества (ТЗ АГП п. 3, п. 12.5)
    department_id: Optional[str] = None
    page_count: Optional[int] = None
    # Непустой ключ означает, что для документа есть PDF/A с текстовым слоем
    pdfa_key: str = ""
    ocr_confidence: Optional[float] = None
    needs_review: bool = False
    review_reason: str = ""
    duplicate_of_id: Optional[str] = None
    # Электронная копия и результат сверки с подлинником (ТС-176 п. 11.6–11.7)
    copy_status: str = ""
    copy_checked_by: str = ""
    copy_checked_at: Optional[datetime] = None
    copy_note: str = ""
    copy_signer: str = ""
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DocumentDetail(DocumentOut):
    ocr_text: str
    annotation: str = ""


class DocumentHistoryItem(BaseModel):
    id: str
    title: str
    doc_number: str
    doc_date: Optional[date]
    created_at: datetime
    superseded_at: Optional[date]
    is_current: bool

    class Config:
        from_attributes = True


class DocumentHistory(BaseModel):
    cadastral_number: str
    chain: list[DocumentHistoryItem]


# ---- Nomenclature & Cases ----
def _known_doc_types(values: list[str]) -> list[str]:
    """Виды документов статьи номенклатуры: только из справочника, без повторов."""
    known = {dt.value for dt in DocType}
    unknown = [v for v in values if v not in known]
    if unknown:
        raise ValueError("Неизвестные виды документов: " + ", ".join(unknown))
    return list(dict.fromkeys(values))


DocTypeList = Annotated[list[str], AfterValidator(_known_doc_types)]


class NomenclatureCreate(BaseModel):
    index: str = ""  # пусто → присваивается автоматически (01-01, 01-02, …)
    title: str
    year: int
    article: str = ""
    retention_label: str = ""
    retention_years: Optional[int] = None
    permanent: bool = False
    note: str = ""
    department_id: Optional[str] = None
    # Виды документов, принимаемые в дела статьи (ТС-176 п. 4.5); пусто — любые.
    doc_types: DocTypeList = []


class NomenclatureUpdate(BaseModel):
    index: Optional[str] = None
    title: Optional[str] = None
    article: Optional[str] = None
    retention_label: Optional[str] = None
    retention_years: Optional[int] = None
    permanent: Optional[bool] = None
    note: Optional[str] = None
    department_id: Optional[str] = None
    doc_types: Optional[DocTypeList] = None
    version: Optional[int] = None


class NomenclatureOut(NomenclatureCreate):
    id: str
    status: str = "Действующая"
    version: int = 1
    # На выходе без проверки по справочнику: вид, переименованный после
    # сохранения статьи, не должен ронять выдачу всей номенклатуры.
    doc_types: list[str] = []

    class Config:
        from_attributes = True


# ---- Сканирование (ТС-176 п. 4.5) и учёт работ оцифровки ----
class ScanCaseCreate(BaseModel):
    nomenclature_id: str
    # Пусто — следующий том по порядку
    volume: Optional[int] = Field(default=None, ge=1)
    title: str = ""
    department_id: Optional[str] = None


class WorkStageUpdate(BaseModel):
    done: bool = True
    # Пусто — объём по страницам принятых документов дела
    pages: Optional[int] = Field(default=None, ge=0)
    completed_at: Optional[date] = None
    note: str = ""


class WorkStageOut(BaseModel):
    stage: str
    label: str
    done: bool
    pages: int = 0
    completed_at: Optional[date] = None
    performed_by: str = ""
    note: str = ""


class CaseCreate(BaseModel):
    title: str
    index: str = ""
    nomenclature_id: Optional[str] = None
    volume: int = 1
    year: Optional[int] = None
    note: str = ""


class CaseUpdate(BaseModel):
    title: Optional[str] = None
    index: Optional[str] = None
    status: Optional[CaseStatus] = None
    note: Optional[str] = None


class CaseOut(BaseModel):
    id: str
    index: str
    title: str
    volume: int
    year: int
    date_from: Optional[date]
    date_to: Optional[date]
    status: CaseStatus
    retention_label: str
    retention_years: Optional[int]
    permanent: bool
    retention_until: Optional[date]
    note: str
    documents_count: int = 0
    # Аннотация дела, составленная ИИ (ТЗ АГП п. 12.4)
    annotation: str = ""
    department_id: Optional[str] = None

    class Config:
        from_attributes = True


class CaseDetail(CaseOut):
    documents: list[DocumentOut] = []


# ---- ЭРКК (регистрационно-контрольная карточка) ----
class RegCardOut(BaseModel):
    id: str
    document_id: str
    reg_number: str
    reg_date: date
    executor: str
    resolution: str
    on_control: bool
    due_date: Optional[date]
    executed_at: Optional[date]

    class Config:
        from_attributes = True


class RegCardUpdate(BaseModel):
    executor: Optional[str] = None
    resolution: Optional[str] = None
    on_control: Optional[bool] = None
    due_date: Optional[date] = None
    executed_at: Optional[date] = None


# ---- Акты о выделении к уничтожению ----
class DestructionActCreate(BaseModel):
    document_ids: list[str]
    is_electronic: bool = True
    note: str = ""


class DestructionActUpdate(BaseModel):
    commission_protocol: Optional[str] = None
    note: Optional[str] = None


class DestructionActOut(BaseModel):
    id: str
    number: str
    act_date: date
    is_electronic: bool
    status: ActStatus
    note: str
    created_by: str
    approved_by: str
    items_count: int = 0
    # retention — по истечении срока хранения; ecopy — электронные копии (ТС-176 п. 11.7)
    kind: str = "retention"
    commission_protocol: str = ""

    class Config:
        from_attributes = True


class DestructionActDetail(DestructionActOut):
    documents: list[DocumentOut] = []


# ---- Электронные копии (ТС-176 п. 11.6–11.7) ----
class CopyMark(BaseModel):
    is_copy: bool


class CopyCertify(BaseModel):
    # base64 CMS от NCALayer над контрольной характеристикой файла копии
    cms_base64: str
    note: str = ""


class CopyReconcile(BaseModel):
    result: str          # mismatch | no_original
    note: str = ""


class EcopyActCreate(BaseModel):
    document_ids: list[str] = Field(min_length=1)
    commission_protocol: str = ""
    note: str = ""


# ---- Выдача дел ----
class IssueCreate(BaseModel):
    case_id: str
    requested_by: str
    purpose: str = ""
    due_date: Optional[date] = None


class IssueOut(BaseModel):
    id: str
    case_id: str
    requested_by: str
    purpose: str
    status: IssueStatus
    order_date: date
    issue_date: Optional[date]
    due_date: Optional[date]
    returned_at: Optional[date]
    created_by: str
    case_index: str = ""
    case_title: str = ""
    overdue: bool = False

    class Config:
        from_attributes = True


# ---- Аудит ----
class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    fond: Optional[str] = None
    opis: Optional[str] = None
    delo: Optional[str] = None
    doc_type: Optional[DocType] = None
    doc_number: Optional[str] = None
    counterparty: Optional[str] = None
    doc_date: Optional[date] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    cadastral_number: Optional[str] = None
    real_estate_address: Optional[str] = None
    real_estate_area: Optional[float] = None
    department_id: Optional[str] = None
    page_count: Optional[int] = None
    # Снять отметку «требует проверки» после ручной сверки распознавания.
    needs_review: Optional[bool] = None
    # Версия карточки, которую редактировал клиент (оптимистичная блокировка,
    # п. 6.4 ТС). Если не передана, проверка конфликта не выполняется.
    version: Optional[int] = None


# ---- Search ----
class SearchHit(BaseModel):
    id: str
    title: str
    fond: str
    opis: str
    delo: str
    score: float
    highlight: str = ""
    status: str = ""


class SearchResponse(BaseModel):
    query: str
    mode: str
    total: int
    hits: list[SearchHit]


# ---- RAG chat ----
class ChatRequest(BaseModel):
    question: str


class ChatSource(BaseModel):
    id: str
    title: str
    fond: str = ""
    opis: str = ""
    delo: str = ""
    score: float = 0.0
    # Страница и цитата, на которых основан ответ (ТЗ АГП п. 12.3: ссылка на
    # документ, страницу и фрагмент). None — источник выбран по метаданным
    # (перечень, подсчёт), и конкретной страницы у него нет.
    page_no: Optional[int] = None
    fragment: str = ""


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource]
    model_ready: bool = True


# ---- AI agent (tool-calling) ----
class AgentMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class AgentRequest(BaseModel):
    messages: list[AgentMessage]
    # Идентификатор запроса, по которому клиент может остановить генерацию.
    request_id: Optional[str] = None


class CancelRequest(BaseModel):
    request_id: str


class AgentStep(BaseModel):
    tool: str
    input: str = ""
    summary: str = ""


class AgentResponse(BaseModel):
    answer: str
    sources: list[ChatSource]
    steps: list[AgentStep] = []
    model_ready: bool = True
    cancelled: bool = False
    # Уверенность в ответе по итогам сверки чисел с текстом документов:
    # high | medium | low. None — ответ получен путём, где сверка не делалась
    # (например, детерминированный подсчёт по базе).
    confidence: Optional[str] = None


# ---- Signature ----
class SignatureVerifyRequest(BaseModel):
    # base64 CMS/CAdES signature produced by NCALayer
    cms_base64: str
    document_id: Optional[str] = None


class SignatureVerifyResponse(BaseModel):
    status: SignatureStatus
    signer_info: str
    detail: str = ""


# =============================================================================
# ТЗ «Азиатский Газопровод»: модули п. 8
# =============================================================================

# ---- Архивные запросы ----
class ArchiveRequestCreate(BaseModel):
    applicant: str
    applicant_contact: str = ""
    request_type: str = "Тематический"
    subject: str = ""
    number: str = ""                    # пусто → присваивается автоматически
    reg_date: Optional[date] = None
    due_date: Optional[date] = None
    executor_email: str = ""
    department_id: Optional[str] = None
    document_ids: list[str] = []
    case_ids: list[str] = []


class ArchiveRequestUpdate(BaseModel):
    applicant: Optional[str] = None
    applicant_contact: Optional[str] = None
    request_type: Optional[str] = None
    subject: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[date] = None
    executor_email: Optional[str] = None
    response: Optional[str] = None
    department_id: Optional[str] = None
    document_ids: Optional[list[str]] = None
    case_ids: Optional[list[str]] = None
    version: Optional[int] = None


class ArchiveRequestOut(BaseModel):
    id: str
    number: str
    reg_date: date
    applicant: str
    applicant_contact: str
    request_type: str
    subject: str
    status: str
    due_date: Optional[date] = None
    executor_email: str
    response: str
    completed_at: Optional[date] = None
    department_id: Optional[str] = None
    created_by: str
    created_at: datetime
    version: int = 1
    overdue: bool = False
    documents_count: int = 0

    class Config:
        from_attributes = True


# ---- Описи дел ----
class InventoryCreate(BaseModel):
    title: str = ""
    year: int
    kind: str
    number: str = ""
    department_id: Optional[str] = None
    note: str = ""
    # Наполнить опись делами автоматически по категории срока хранения
    autofill: bool = True


class InventoryUpdate(BaseModel):
    title: Optional[str] = None
    number: Optional[str] = None
    note: Optional[str] = None
    status: Optional[str] = None
    case_ids: Optional[list[str]] = None


class InventoryItemOut(BaseModel):
    case_id: str
    order_no: int
    case_index: str = ""
    case_title: str = ""
    year: Optional[int] = None
    retention: str = ""
    documents_count: int = 0


class InventoryOut(BaseModel):
    id: str
    number: str
    title: str
    year: int
    kind: str
    status: str
    note: str
    department_id: Optional[str] = None
    created_by: str
    created_at: datetime
    items_count: int = 0

    class Config:
        from_attributes = True


class InventoryDetail(InventoryOut):
    items: list[InventoryItemOut] = []


# ---- НТО, экспертные комиссии, передача в госархив (ТС-176 п. 5.3, 8.2, 10.2–10.5) ----
class CommissionProtocolIn(BaseModel):
    commission: str                     # ЭК | ЦЭК | ЭПК
    number: str = Field(min_length=1, max_length=64)
    protocol_date: date
    agenda: str = ""
    note: str = ""


class CommissionDecisionIn(BaseModel):
    object_type: str                    # inventory | destruction_act | nto | transfer
    object_id: str
    decision: str                       # approved | agreed | revision | rejected
    comment: str = ""


class CommissionDecisionOut(BaseModel):
    id: str
    object_type: str
    object_id: str
    object_title: str
    decision: str
    comment: str

    class Config:
        from_attributes = True


class CommissionProtocolOut(CommissionProtocolIn):
    id: str
    created_by: str
    created_at: datetime
    decisions: list[CommissionDecisionOut] = []

    class Config:
        from_attributes = True


class MissingCaseItem(BaseModel):
    """Строка акта о недостающих делах."""
    case_index: str = ""
    title: str = Field(min_length=1, max_length=512)
    years: str = ""
    note: str = ""


class NtoRecordIn(BaseModel):
    kind: str
    number: str = ""
    record_date: Optional[date] = None
    title: str = ""
    fond: str = ""
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    inventory_id: Optional[str] = None
    fields: dict[str, str] = {}
    items: list[MissingCaseItem] = []


class NtoRecordOut(NtoRecordIn):
    id: str
    record_date: date
    status: str
    created_by: str
    approved_by: str
    approved_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TransferActIn(BaseModel):
    number: str = ""
    act_date: Optional[date] = None
    archive_name: str = Field(min_length=1, max_length=512)
    fond: str = ""
    basis: str = ""
    note: str = ""
    case_ids: list[str] = []


class TransferItemOut(BaseModel):
    case_id: str
    order_no: int
    case_index: str = ""
    case_title: str = ""
    year: Optional[int] = None
    volume: int = 1
    documents_count: int = 0
    retention: str = ""


class TransferActOut(BaseModel):
    id: str
    number: str
    act_date: date
    archive_name: str
    fond: str
    basis: str
    note: str
    status: str
    created_by: str
    transferred_by: str
    transferred_at: Optional[datetime] = None
    created_at: datetime
    items: list[TransferItemOut] = []


# ---- Вложения к карточкам (описи, акты, запросы, номенклатура) ----
class AttachmentOut(BaseModel):
    id: str
    owner_type: str
    owner_id: str
    filename: str
    content_type: str
    size: int
    uploaded_by: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Обращения в поддержку ----
class SupportTicketCreate(BaseModel):
    subject: str
    body: str = ""
    # Виды, услуги и уровни — services/sla.py (ТС-176 разд. 13)
    kind: str = "question"
    service: str = ""
    criticality: str = "medium"


class SupportTicketAnswer(BaseModel):
    answer: str
    # False — промежуточный ответ: обращение остаётся в работе
    resolve: bool = True
    # Прежний формат запроса; статус теперь определяется действием
    status: Optional[str] = None


class SupportTicketReopen(BaseModel):
    reason: str = ""


class SupportTicketOut(BaseModel):
    id: str
    user_email: str
    subject: str
    body: str
    status: str
    answer: str
    created_at: datetime
    answered_at: Optional[datetime] = None
    kind: str = "question"
    service: str = ""
    criticality: str = "medium"
    reaction_due: Optional[datetime] = None
    resolution_due: Optional[datetime] = None
    reacted_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    assignee: str = ""
    reopen_count: int = 0
    overdue: bool = False

    class Config:
        from_attributes = True


# ---- Доступ по категориям документов ----
class DocTypeAccessIn(BaseModel):
    role: Role
    doc_groups: list[str]


class DocTypeAccessOut(BaseModel):
    role: str
    doc_groups: list[str]


# ---- Ключи доступа внешних систем (API) ----
class ApiKeyCreate(BaseModel):
    name: str
    role: Role = Role.viewer


class ApiKeyOut(BaseModel):
    id: str
    name: str
    prefix: str
    role: Role
    created_by: str
    created_at: datetime
    last_used_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ApiKeyCreated(ApiKeyOut):
    # Полный ключ показывается один раз при создании: в базе только хэш.
    key: str


# ---- Импорт пакетов оцифровки ----
class ImportJobOut(BaseModel):
    id: str
    filename: str
    status: str
    total: int
    created_documents: int
    created_cases: int
    skipped_duplicates: int
    errors: list[str] = []
    created_by: str
    created_at: datetime
    finished_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---- Журнал ИИ-агента (п. 12.6) ----
class AgentLogOut(BaseModel):
    id: str
    ts: datetime
    user_email: str
    question: str
    answer: str
    confidence: str
    route: str
    refused: bool
    cancelled: bool
    duration_ms: int
    sources: list[dict] = []

    class Config:
        from_attributes = True
