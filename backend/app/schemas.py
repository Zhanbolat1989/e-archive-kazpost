from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, EmailStr

from .models import (
    Role, DocStatus, SignatureStatus, DocType, CaseStatus, ActStatus, IssueStatus,
)


# ---- Auth ----
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str = ""
    role: Role = Role.archivist


class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: Role

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
class NomenclatureCreate(BaseModel):
    index: str = ""  # пусто → присваивается автоматически (01-01, 01-02, …)
    title: str
    year: int
    article: str = ""
    retention_label: str = ""
    retention_years: Optional[int] = None
    permanent: bool = False
    note: str = ""


class NomenclatureOut(NomenclatureCreate):
    id: str

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


class DestructionActDetail(DestructionActOut):
    documents: list[DocumentOut] = []


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
class AuditOut(BaseModel):
    id: str
    ts: datetime
    user_email: str
    action: str
    object_type: str
    object_id: str
    detail: str

    class Config:
        from_attributes = True


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


class AgentStep(BaseModel):
    tool: str
    input: str = ""
    summary: str = ""


class AgentResponse(BaseModel):
    answer: str
    sources: list[ChatSource]
    steps: list[AgentStep] = []
    model_ready: bool = True


# ---- Signature ----
class SignatureVerifyRequest(BaseModel):
    # base64 CMS/CAdES signature produced by NCALayer
    cms_base64: str
    document_id: Optional[str] = None


class SignatureVerifyResponse(BaseModel):
    status: SignatureStatus
    signer_info: str
    detail: str = ""
