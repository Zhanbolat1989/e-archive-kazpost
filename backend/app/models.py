import enum
import uuid
from datetime import datetime, date

from sqlalchemy import (
    String, Integer, DateTime, Date, ForeignKey, Text, Enum, BigInteger, Numeric,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Role(str, enum.Enum):
    admin = "admin"          # полный доступ
    archivist = "archivist"  # приём, описание, выдача
    viewer = "viewer"        # только чтение/поиск


class DocStatus(str, enum.Enum):
    uploaded = "uploaded"
    scanning = "scanning"
    infected = "infected"
    processing = "processing"  # OCR + индексация
    ready = "ready"
    failed = "failed"


class SignatureStatus(str, enum.Enum):
    none = "none"
    valid = "valid"
    invalid = "invalid"
    unsupported = "unsupported"


class DocType(str, enum.Enum):
    # Финансово-договорные
    contract = "Договор"
    invoice = "Счёт-фактура"
    act = "Акт"
    payment = "Платёжное поручение"
    waybill = "Накладная"
    expense_report = "Авансовый отчёт"
    accounting_note = "Бухгалтерская справка"
    tax_report = "Налоговая отчётность"
    bank_statement = "Банковская выписка"
    estimate = "Смета"
    # Кадровые (HR)
    employment_contract = "Трудовой договор"
    personnel_order = "Кадровый приказ"
    statement = "Заявление"
    personal_file = "Личное дело"
    staffing = "Штатное расписание"
    timesheet = "Табель учёта рабочего времени"
    reference = "Справка"
    # Канцелярия / делопроизводство
    order = "Приказ"
    decree = "Распоряжение"
    protocol = "Протокол"
    memo = "Служебная записка"
    incoming = "Входящее письмо"
    outgoing = "Исходящее письмо"
    regulation = "Положение"
    letter = "Письмо"
    inventory = "Опись"
    # Недвижимое имущество (кадастр) — Закон РК № 310-III «О государственной
    # регистрации прав на недвижимое имущество»
    title_deed = "Правоустанавливающий документ"
    cadastral_passport = "Кадастровый паспорт"
    rights_certificate = "Справка о зарегистрированных правах"
    land_act = "Акт на земельный участок"
    mortgage_contract = "Договор ипотеки"
    registry_extract = "Выписка из реестра недвижимости"
    other = "Прочее"


# Grouping for the UI dropdown (value → category label).
DOC_TYPE_GROUPS = {
    "Финансы и договоры": [
        DocType.contract, DocType.invoice, DocType.act, DocType.payment,
        DocType.waybill, DocType.expense_report, DocType.accounting_note,
        DocType.tax_report, DocType.bank_statement, DocType.estimate,
    ],
    "Кадры (HR)": [
        DocType.employment_contract, DocType.personnel_order, DocType.statement,
        DocType.personal_file, DocType.staffing, DocType.timesheet, DocType.reference,
    ],
    "Канцелярия": [
        DocType.order, DocType.decree, DocType.protocol, DocType.memo,
        DocType.incoming, DocType.outgoing, DocType.regulation, DocType.letter,
        DocType.inventory, DocType.other,
    ],
    "Недвижимость": [
        DocType.title_deed, DocType.cadastral_passport, DocType.rights_certificate,
        DocType.land_act, DocType.mortgage_contract, DocType.registry_extract,
    ],
}

# Типы, для которых оформление объекта (кадастровый номер, адрес, площадь)
# осмысленно и отображается в интерфейсе.
REAL_ESTATE_TYPES = frozenset(DOC_TYPE_GROUPS["Недвижимость"])


class CaseStatus(str, enum.Enum):
    forming = "Формируется"
    closed = "Закрыто"
    transferred = "Передано"
    destroyed = "Уничтожено"


class NomenclatureItem(Base):
    """Статья номенклатуры дел организации (индекс, заголовок, срок хранения,
    статья по Перечню 279-НҚ)."""
    __tablename__ = "nomenclature"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    index: Mapped[str] = mapped_column(String(64), index=True)   # напр. «01-05»
    title: Mapped[str] = mapped_column(String(512))
    year: Mapped[int] = mapped_column(Integer, index=True)
    # Статья Перечня типовых документов (279-НҚ), задаётся архивариусом
    article: Mapped[str] = mapped_column(String(64), default="")
    retention_label: Mapped[str] = mapped_column(String(128), default="")
    retention_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    permanent: Mapped[bool] = mapped_column(default=False)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Case(Base):
    """Дело (единица хранения): группирует документы, несёт срок хранения."""
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    nomenclature_id: Mapped[str | None] = mapped_column(
        ForeignKey("nomenclature.id"), nullable=True
    )
    nomenclature: Mapped["NomenclatureItem | None"] = relationship()
    index: Mapped[str] = mapped_column(String(64), index=True)   # индекс дела
    title: Mapped[str] = mapped_column(String(512))
    volume: Mapped[int] = mapped_column(Integer, default=1)      # номер тома
    year: Mapped[int] = mapped_column(Integer, index=True)
    date_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[CaseStatus] = mapped_column(
        Enum(CaseStatus, native_enum=False, length=32),
        default=CaseStatus.forming, index=True,
    )
    retention_label: Mapped[str] = mapped_column(String(128), default="")
    retention_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    permanent: Mapped[bool] = mapped_column(default=False)
    # Дата, до которой дело хранится (конец года закрытия + срок)
    retention_until: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # Оптимистичная блокировка карточки дела (п. 6.4 ТС): одновременная работа
    # разрешена, но правка поверх чужой версии отклоняется с 409.
    version: Mapped[int] = mapped_column(Integer, default=1)


class ActStatus(str, enum.Enum):
    draft = "Проект"
    approved = "Утверждён"


class RegCard(Base):
    """ЭРКК — электронная регистрационно-контрольная карточка (приказ № 236).
    Рег. номер = индекс дела по номенклатуре + порядковый номер."""
    __tablename__ = "reg_cards"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id"), unique=True, index=True
    )
    reg_number: Mapped[str] = mapped_column(String(128), index=True)
    reg_date: Mapped[date] = mapped_column(Date, default=date.today)
    executor: Mapped[str] = mapped_column(String(255), default="")
    resolution: Mapped[str] = mapped_column(Text, default="")
    on_control: Mapped[bool] = mapped_column(default=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    executed_at: Mapped[date | None] = mapped_column(Date, nullable=True)


class DestructionAct(Base):
    """Акт о выделении к уничтожению документов (прил. 14/15 приказа № 235)."""
    __tablename__ = "destruction_acts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    number: Mapped[str] = mapped_column(String(64), index=True)
    act_date: Mapped[date] = mapped_column(Date, default=date.today)
    is_electronic: Mapped[bool] = mapped_column(default=True)
    status: Mapped[ActStatus] = mapped_column(
        Enum(ActStatus, native_enum=False, length=32), default=ActStatus.draft
    )
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(255), default="")
    approved_by: Mapped[str] = mapped_column(String(255), default="")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    items: Mapped[list["DestructionActItem"]] = relationship(
        back_populates="act", cascade="all, delete-orphan"
    )


class DestructionActItem(Base):
    __tablename__ = "destruction_act_items"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    act_id: Mapped[str] = mapped_column(ForeignKey("destruction_acts.id"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    act: Mapped["DestructionAct"] = relationship(back_populates="items")
    document: Mapped["Document"] = relationship()


class IssueStatus(str, enum.Enum):
    requested = "Заказ"
    issued = "Выдано"
    returned = "Возвращено"


class IssueRecord(Base):
    """Выдача дела во временное пользование (заказ → акт выдачи → возврат;
    прил. 20–23 приказа № 235)."""
    __tablename__ = "issue_records"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    case: Mapped["Case"] = relationship()
    requested_by: Mapped[str] = mapped_column(String(255))      # кому выдано
    purpose: Mapped[str] = mapped_column(Text, default="")      # цель использования
    status: Mapped[IssueStatus] = mapped_column(
        Enum(IssueStatus, native_enum=False, length=32),
        default=IssueStatus.requested, index=True,
    )
    order_date: Mapped[date] = mapped_column(Date, default=date.today)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    returned_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), default="")


class AuditActionType(str, enum.Enum):
    """Тип совершённого действия для аудиторского следа (ТС-176, разд. 14, п. 4.5)."""
    create = "CREATE"
    read = "READ"
    update = "UPDATE"
    delete = "DELETE"
    login = "LOGIN"
    logout = "LOGOUT"
    security = "SECURITY"     # изменение прав, ролей, настроек безопасности


class AuditLog(Base):
    """Аудиторский след (ТС-176 разд. 14; «цифровой архив» приказа № 236).

    Формат записи по ТЗ: логин пользователя, дата и время, IP/рабочая станция,
    объект действия, тип действия и результат. Записи никогда не удаляются —
    по истечении срока оперативного доступа они лишь помечаются archived=True
    (оперативный доступ ≥ 3 мес., архивный ≥ 1 год).
    """
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    user_email: Mapped[str] = mapped_column(String(255), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    object_type: Mapped[str] = mapped_column(String(64), default="")
    object_id: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    # --- поля, требуемые форматом аудиторского следа (разд. 14, п. 4) ---
    ip_address: Mapped[str] = mapped_column(String(64), default="", index=True)
    user_agent: Mapped[str] = mapped_column(String(512), default="")
    action_type: Mapped[str] = mapped_column(String(16), default="UPDATE", index=True)
    result: Mapped[bool] = mapped_column(default=True, index=True)
    archived: Mapped[bool] = mapped_column(default=False, index=True)


class Organization(Base):
    """Модуль «Предприятие» (п. 4.8 ТС): сведения о заказчике и подписантах."""
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(512))
    short_name: Mapped[str] = mapped_column(String(255), default="")
    bin: Mapped[str] = mapped_column(String(12), default="")
    address: Mapped[str] = mapped_column(String(512), default="")
    phone: Mapped[str] = mapped_column(String(64), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    head_name: Mapped[str] = mapped_column(String(255), default="")
    head_position: Mapped[str] = mapped_column(String(255), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Department(Base):
    """Структурное подразделение организации (оргструктура, п. 4.8/4.10 ТС).
    Дерево: parent_id ссылается на вышестоящее подразделение."""
    __tablename__ = "departments"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(512))
    index: Mapped[str] = mapped_column(String(64), default="", index=True)
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id"), nullable=True, index=True
    )
    head_name: Mapped[str] = mapped_column(String(255), default="")
    head_position: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.archivist)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # --- оргструктура и право подписи (п. 4.8 ТС) ---
    department_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id"), nullable=True, index=True
    )
    department: Mapped["Department | None"] = relationship()
    position: Mapped[str] = mapped_column(String(255), default="")
    can_sign: Mapped[bool] = mapped_column(default=False)
    # --- п. 4.4 разд. 14: блокировка учётной записи после трёх неверных вводов ---
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)


class UserSession(Base):
    """Сессия пользователя: п. 4.9 ТС («отображать и управлять текущими
    сессиями») и п. 3.2 разд. 14 (метаданные входа: браузер, IP, время)."""
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    user: Mapped["User"] = relationship()
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class LoginChallenge(Base):
    """Второй фактор входа (п. 3.3 разд. 14 ТС): проверочный код, высылаемый
    на email пользователя при входе с нового устройства или при второй сессии."""
    __tablename__ = "login_challenges"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(512), default="")


class ApprovalStatus(str, enum.Enum):
    pending = "На согласовании"
    approved = "Согласовано"
    rejected = "Отклонено"


class ApprovalRequest(Base):
    """Маршрут согласования карточки дела/документа (п. 4.10 ТС): шаги
    согласования выстраиваются по оргструктуре заказчика."""
    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    object_type: Mapped[str] = mapped_column(String(32), index=True)   # document | case
    object_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, native_enum=False, length=32),
        default=ApprovalStatus.pending, index=True,
    )
    created_by: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    steps: Mapped[list["ApprovalStep"]] = relationship(
        back_populates="request", cascade="all, delete-orphan",
        order_by="ApprovalStep.order_no",
    )


class ApprovalStep(Base):
    """Шаг маршрута согласования: согласующий и его решение."""
    __tablename__ = "approval_steps"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    request_id: Mapped[str] = mapped_column(ForeignKey("approval_requests.id"), index=True)
    request: Mapped["ApprovalRequest"] = relationship(back_populates="steps")
    order_no: Mapped[int] = mapped_column(Integer, default=1)
    approver_email: Mapped[str] = mapped_column(String(255), index=True)
    approver_name: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, native_enum=False, length=32), default=ApprovalStatus.pending
    )
    comment: Mapped[str] = mapped_column(Text, default="")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str] = mapped_column(Text, default="")

    # Archival taxonomy (РК): фонд / опись / дело
    fond: Mapped[str] = mapped_column(String(128), default="", index=True)
    opis: Mapped[str] = mapped_column(String(128), default="", index=True)
    delo: Mapped[str] = mapped_column(String(128), default="", index=True)

    # Corporate document metadata (for metadata-aware search)
    # native_enum=False stores the label as VARCHAR, so new DocType members need
    # no DB migration.
    doc_type: Mapped[DocType] = mapped_column(
        Enum(DocType, native_enum=False, length=64), default=DocType.other, index=True
    )
    doc_number: Mapped[str] = mapped_column(String(128), default="", index=True)
    counterparty: Mapped[str] = mapped_column(String(512), default="", index=True)
    doc_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="KZT")

    # Недвижимое имущество: идентификационные характеристики объекта из
    # регистрационного листа правового кадастра (ст. 1 п. 12 Закона № 310-III).
    # counterparty используется как «правообладатель» для документов этой группы.
    cadastral_number: Mapped[str] = mapped_column(String(64), default="", index=True)
    real_estate_address: Mapped[str] = mapped_column(String(512), default="")
    real_estate_area: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    original_filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(255), default="application/octet-stream")
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    storage_key: Mapped[str] = mapped_column(String(1024), default="")
    checksum_sha256: Mapped[str] = mapped_column(String(64), default="", index=True)

    status: Mapped[DocStatus] = mapped_column(Enum(DocStatus), default=DocStatus.uploaded, index=True)
    status_detail: Mapped[str] = mapped_column(Text, default="")
    ocr_text: Mapped[str] = mapped_column(Text, default="")
    # Auto-generated archival annotation / опись (LLM analysis of the content).
    annotation: Mapped[str] = mapped_column(Text, default="")

    signature_status: Mapped[SignatureStatus] = mapped_column(
        Enum(SignatureStatus), default=SignatureStatus.none
    )
    signer_info: Mapped[str] = mapped_column(Text, default="")

    # Привязка к делу (единице хранения) и срок хранения документа
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id"), nullable=True, index=True)
    case: Mapped["Case | None"] = relationship()
    retention_label: Mapped[str] = mapped_column(String(128), default="")
    retention_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    permanent: Mapped[bool] = mapped_column(default=False)
    retention_until: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    # Жизненный цикл: дата уничтожения (по утверждённому акту) и PDF/A-копия
    destroyed_at: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    pdfa_key: Mapped[str] = mapped_column(String(1024), default="")

    # Замена документа новой версией (напр. смена собственника недвижимости):
    # оригинал в WORM неизменяем — вместо редактирования регистрируется новый
    # документ, а предыдущий помечается «замещён» (аналог ст. 6-7 Закона
    # № 310-III: при регистрации нового права предыдущее прекращается).
    replaces_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True, index=True
    )
    replaces: Mapped["Document | None"] = relationship(remote_side=[id])
    superseded_at: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    # Оптимистичная блокировка карточки документа (п. 6.4 ТС): одновременная
    # работа разрешена, но правка поверх чужой версии отклоняется с 409.
    version: Mapped[int] = mapped_column(Integer, default=1)

    # ЭРКК заводится на каждый документ и без него не имеет смысла — снимается
    # вместе с ним, иначе снятие документа с учёта падает на внешнем ключе.
    reg_card: Mapped["RegCard | None"] = relationship(
        "RegCard",
        foreign_keys="RegCard.document_id",
        cascade="all, delete-orphan",
        uselist=False,
    )

    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    owner: Mapped["User"] = relationship()

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
