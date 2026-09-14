import enum
import uuid
from datetime import datetime, date

from sqlalchemy import (
    String, Integer, DateTime, Date, ForeignKey, Text, Enum, BigInteger, Numeric,
    JSON, UniqueConstraint,
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
    # Аудитор ИБ (ТС-176 разд. 14 п. 5.1): журналы и сессии без доступа к
    # содержимому документов.
    auditor = "auditor"


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
    # --- Жизненный цикл номенклатуры (ТЗ АГП п. 8): проект → на согласовании →
    # действующая. Строка, а не Enum: SQLAlchemy хранит у Enum имя члена, и
    # значение по умолчанию в миграции разошлось бы с тем, что пишет ORM.
    status: Mapped[str] = mapped_column(String(32), default="Действующая", index=True)
    department_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id"), nullable=True, index=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    # Виды документов, принимаемые в дела статьи (ТС-176 п. 4.5: ввод сканов
    # «согласно типам документов, определённых номенклатурой дел»). Пустой
    # список — ограничений нет.
    doc_types: Mapped[list] = mapped_column(JSON, default=list)


NOMENCLATURE_STATUSES = ("Проект", "На согласовании", "Действующая", "Архивная")


# Этапы работ по делу при оцифровке архива (ТС-176 разд. 8–11) в порядке
# выполнения. По отметкам этапов складывается объём оказанных услуг к акту.
WORK_STAGES = {
    "nto": "Научно-техническая обработка",
    "expertise": "Экспертиза ценности",
    "scanning": "Сканирование",
    "stitching": "Прошивка и восстановление дела",
    "digitization": "Оцифровка: распознавание, верификация, индексирование",
}


class CaseWorkStage(Base):
    """Отметка выполненного этапа работ по делу: кто, когда и в каком объёме.

    Одна отметка на этап дела: повторная работа правит отметку, а не удваивает
    объём в акте оказанных услуг."""
    __tablename__ = "case_work_stages"
    __table_args__ = (UniqueConstraint("case_id", "stage", name="uq_case_work_stage"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    stage: Mapped[str] = mapped_column(String(32), index=True)
    pages: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    performed_by: Mapped[str] = mapped_column(String(255), default="")
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
    # Краткое содержание дела, составленное ИИ по аннотациям документов (ТЗ АГП
    # п. 12.4: «аннотация документа или дела»).
    annotation: Mapped[str] = mapped_column(Text, default="")
    department_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id"), nullable=True, index=True
    )


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
    # retention — выделение к уничтожению по истечении срока хранения;
    # ecopy — уничтожение электронных копий без подлинника или с отрицательной
    # сверкой (ТС-176 п. 11.7), утверждается по согласованию с ЦЭК (ЭК).
    kind: Mapped[str] = mapped_column(String(16), default="retention")
    commission_protocol: Mapped[str] = mapped_column(String(128), default="")
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
    # Руководитель как учётная запись (ТС-176 п. 4.10): его подставляют шаблоны
    # маршрутов согласования. head_name/head_position — реквизиты печатных форм.
    # use_alter: таблицы users и departments ссылаются друг на друга.
    head_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", use_alter=True, name="fk_departments_head_user_id"),
        nullable=True,
    )
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
    # foreign_keys обязателен: departments.head_user_id — второй путь между таблицами.
    department: Mapped["Department | None"] = relationship(foreign_keys="User.department_id")
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


class PasskeyCredential(Base):
    """Ключ доступа WebAuthn (ТС-176 разд. 14 п. 4.2: вход в мобильной версии по
    биометрии). Закрытый ключ не покидает устройство; сервер хранит открытый
    ключ и счётчик подписей (services/passkeys.py)."""
    __tablename__ = "passkey_credentials"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    credential_id: Mapped[str] = mapped_column(String(512), unique=True, index=True)  # base64url
    public_key: Mapped[str] = mapped_column(Text)                                      # base64url, COSE
    sign_count: Mapped[int] = mapped_column(BigInteger, default=0)
    name: Mapped[str] = mapped_column(String(255), default="")
    transports: Mapped[list] = mapped_column(JSON, default=list)
    aaguid: Mapped[str] = mapped_column(String(64), default="")
    backed_up: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WebAuthnChallenge(Base):
    """Одноразовый вызов WebAuthn для регистрации ключа или входа. Хранится на
    сервере и гасится при первой попытке: подписанный ответ нельзя предъявить
    повторно."""
    __tablename__ = "webauthn_challenges"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    purpose: Mapped[str] = mapped_column(String(16))              # register | login
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    challenge: Mapped[str] = mapped_column(String(128))           # base64url
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


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
    # Шаблон, по которому построен маршрут; пусто — согласующие указаны вручную
    template_name: Mapped[str] = mapped_column(String(255), default="")
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
    # Основание назначения по шаблону, напр. «Руководитель: Бухгалтерия»
    basis: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, native_enum=False, length=32), default=ApprovalStatus.pending
    )
    comment: Mapped[str] = mapped_column(Text, default="")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ApprovalRouteTemplate(Base):
    """Шаблон маршрута согласования по оргструктуре (ТС-176 п. 4.10). Шаги —
    позиции оргструктуры {kind, value}; согласующие подставляются при запуске
    маршрута (services/routes.py)."""
    __tablename__ = "approval_route_templates"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    # document | case | nomenclature; пусто — шаблон для любого объекта
    object_type: Mapped[str] = mapped_column(String(32), default="", index=True)
    steps: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class DictionaryEntry(Base):
    """Значение редактируемого справочника (ТС-176 п. 4.9). Виды справочников —
    в services/dictionaries.py. Значения не удаляются, а выводятся из употребления."""
    __tablename__ = "dictionary_entries"
    __table_args__ = (
        UniqueConstraint("kind", "value", name="uq_dictionary_entries_kind_value"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    value: Mapped[str] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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

    # --- Электронная копия (ТС-176 п. 11.6–11.7) ---
    # Скан бумажного документа — электронная копия, а не электронный документ:
    # ЭЦП автора у него нет. Пусто — электронный документ; иначе результат
    # сверки с подлинником (см. services/ecopies.py).
    copy_status: Mapped[str] = mapped_column(String(16), default="", index=True)
    copy_checked_by: Mapped[str] = mapped_column(String(255), default="")
    copy_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    copy_note: Mapped[str] = mapped_column(Text, default="")
    # Кто удостоверил копию ЭЦП и где хранится сама подпись (CMS, под WORM)
    copy_signer: Mapped[str] = mapped_column(Text, default="")
    copy_cms_key: Mapped[str] = mapped_column(String(1024), default="")

    # --- Атрибуты индексирования (ТЗ АГП п. 3): подразделение и число страниц ---
    department_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id"), nullable=True, index=True
    )
    department: Mapped["Department | None"] = relationship()
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- Качество распознавания и дубли (ТЗ АГП п. 12.5) ---
    # Средняя уверенность OCR по документу, 0–100; None — оценка не делалась
    # (цифровой текст без распознавания).
    ocr_confidence: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    needs_review: Mapped[bool] = mapped_column(default=False, index=True)
    review_reason: Mapped[str] = mapped_column(String(512), default="")
    # Документ, дублем которого признан этот (точным или почти-дублем).
    duplicate_of_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True, index=True
    )

    # Замена документа новой версией (напр. смена собственника недвижимости):
    # оригинал в WORM неизменяем — вместо редактирования регистрируется новый
    # документ, а предыдущий помечается «замещён» (аналог ст. 6-7 Закона
    # № 310-III: при регистрации нового права предыдущее прекращается).
    replaces_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True, index=True
    )
    # foreign_keys указан явно: у документа два внешних ключа на самого себя
    # (replaces_id и duplicate_of_id), и без уточнения связь неоднозначна.
    replaces: Mapped["Document | None"] = relationship(
        remote_side=[id], foreign_keys=[replaces_id]
    )
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


# =============================================================================
# ТЗ «Азиатский Газопровод»: модули п. 8 и ИИ-агент п. 12
# =============================================================================

class ExtractedEntity(Base):
    """Реквизит, извлечённый из распознанного текста (п. 12.1): дата, номер,
    организация, персона, сумма, географическое наименование, ссылка на другой
    документ. Каждое значение привязано к документу, странице и фрагменту."""
    __tablename__ = "extracted_entities"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    value: Mapped[str] = mapped_column(String(512))
    normalized: Mapped[str] = mapped_column(String(512), default="", index=True)
    page_no: Mapped[int] = mapped_column(Integer, default=1)
    fragment: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(16), default="rule")   # rule | llm
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgentLog(Base):
    """Журнал запросов и ответов ИИ-агента для целей аудита (п. 12.6)."""
    __tablename__ = "agent_log"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    user_email: Mapped[str] = mapped_column(String(255), index=True)
    question: Mapped[str] = mapped_column(Text, default="")
    answer: Mapped[str] = mapped_column(Text, default="")
    sources: Mapped[str] = mapped_column(Text, default="[]")          # JSON
    confidence: Mapped[str] = mapped_column(String(16), default="")
    route: Mapped[str] = mapped_column(String(16), default="llm")      # quick | llm
    refused: Mapped[bool] = mapped_column(default=False, index=True)
    cancelled: Mapped[bool] = mapped_column(default=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)


REQUEST_STATUSES = ("Зарегистрирован", "В работе", "Исполнен", "Отказано")


class ArchiveRequest(Base):
    """Архивный запрос (п. 8, модуль «Архивные запросы»): обращение за
    сведениями или копиями документов с отслеживанием статуса исполнения."""
    __tablename__ = "archive_requests"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    number: Mapped[str] = mapped_column(String(64), index=True)
    reg_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    applicant: Mapped[str] = mapped_column(String(512))
    applicant_contact: Mapped[str] = mapped_column(String(255), default="")
    request_type: Mapped[str] = mapped_column(String(128), default="Тематический")
    subject: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="Зарегистрирован", index=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    executor_email: Mapped[str] = mapped_column(String(255), default="")
    response: Mapped[str] = mapped_column(Text, default="")
    completed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    department_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id"), nullable=True, index=True
    )
    created_by: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)


class ArchiveRequestItem(Base):
    """Документ или дело, использованные при исполнении запроса — основа
    отчётности по обращениям к документам."""
    __tablename__ = "archive_request_items"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    request_id: Mapped[str] = mapped_column(ForeignKey("archive_requests.id"), index=True)
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True, index=True
    )
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id"), nullable=True, index=True)


INVENTORY_KINDS = (
    "Постоянного хранения",
    "Временного хранения (свыше 10 лет)",
    "По личному составу",
    "Временного хранения (до 10 лет)",
)


class Inventory(Base):
    """Опись дел (п. 8, модуль «Описи дел»): карточка описи с перечнем дел.
    Опись формируется автоматически по категории сроков хранения."""
    __tablename__ = "inventories"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    number: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(512))
    year: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    department_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="Проект", index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    items: Mapped[list["InventoryItem"]] = relationship(
        back_populates="inventory", cascade="all, delete-orphan",
        order_by="InventoryItem.order_no",
    )


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    inventory_id: Mapped[str] = mapped_column(ForeignKey("inventories.id"), index=True)
    inventory: Mapped["Inventory"] = relationship(back_populates="items")
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    case: Mapped["Case"] = relationship()
    order_no: Mapped[int] = mapped_column(Integer, default=1)


class CommissionProtocol(Base):
    """Протокол заседания экспертной комиссии (ТС-176 п. 10.2–10.5): ЭК
    организации, ЦЭК или ЭПК уполномоченного органа. Решения по описям, актам
    и документам НТО — в CommissionDecision (правила — services/nto.py)."""
    __tablename__ = "commission_protocols"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    commission: Mapped[str] = mapped_column(String(8), index=True)      # ЭК | ЦЭК | ЭПК
    number: Mapped[str] = mapped_column(String(64), index=True)
    protocol_date: Mapped[date] = mapped_column(Date, index=True)
    agenda: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    decisions: Mapped[list["CommissionDecision"]] = relationship(
        back_populates="protocol", cascade="all, delete-orphan",
        order_by="CommissionDecision.created_at",
    )


class CommissionDecision(Base):
    """Решение комиссии по объекту: описи, акту о выделении к уничтожению,
    документу НТО или акту приёма-передачи. Ссылка на объект строкой: протокол
    остаётся в реестре, даже если объект позже удалён."""
    __tablename__ = "commission_decisions"
    __table_args__ = (
        UniqueConstraint("protocol_id", "object_type", "object_id",
                         name="uq_commission_decisions_object"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    protocol_id: Mapped[str] = mapped_column(ForeignKey("commission_protocols.id"), index=True)
    protocol: Mapped["CommissionProtocol"] = relationship(back_populates="decisions")
    object_type: Mapped[str] = mapped_column(String(32), index=True)
    object_id: Mapped[str] = mapped_column(String(64), index=True)
    object_title: Mapped[str] = mapped_column(String(512), default="")
    decision: Mapped[str] = mapped_column(String(16))
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class NtoRecord(Base):
    """Документ научно-технической обработки (ТС-176 п. 8.2): историческая
    справка, предисловие к описи, акт о завершении работ по упорядочению, акт
    о недостающих делах. Текстовые разделы — fields, перечень дел — items."""
    __tablename__ = "nto_records"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    number: Mapped[str] = mapped_column(String(64), default="", index=True)
    record_date: Mapped[date] = mapped_column(Date, default=date.today)
    title: Mapped[str] = mapped_column(String(512), default="")
    fond: Mapped[str] = mapped_column(String(128), default="")
    year_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    year_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    inventory_id: Mapped[str | None] = mapped_column(
        ForeignKey("inventories.id"), nullable=True, index=True
    )
    fields: Mapped[dict] = mapped_column(JSON, default=dict)
    items: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="Проект", index=True)
    created_by: Mapped[str] = mapped_column(String(255), default="")
    approved_by: Mapped[str] = mapped_column(String(255), default="")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class TransferAct(Base):
    """Акт приёма-передачи дел на государственное хранение (ТС-176 п. 5.3).
    Электронные дела передаются информационным пакетом с контрольными
    характеристиками; после передачи дела получают статус «Передано»."""
    __tablename__ = "transfer_acts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    number: Mapped[str] = mapped_column(String(64), index=True)
    act_date: Mapped[date] = mapped_column(Date, default=date.today)
    archive_name: Mapped[str] = mapped_column(String(512))
    fond: Mapped[str] = mapped_column(String(128), default="")
    basis: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="Проект", index=True)
    created_by: Mapped[str] = mapped_column(String(255), default="")
    transferred_by: Mapped[str] = mapped_column(String(255), default="")
    transferred_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    items: Mapped[list["TransferActItem"]] = relationship(
        back_populates="act", cascade="all, delete-orphan",
        order_by="TransferActItem.order_no",
    )


class TransferActItem(Base):
    __tablename__ = "transfer_act_items"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    act_id: Mapped[str] = mapped_column(ForeignKey("transfer_acts.id"), index=True)
    act: Mapped["TransferAct"] = relationship(back_populates="items")
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    case: Mapped["Case"] = relationship()
    order_no: Mapped[int] = mapped_column(Integer, default=1)


class Attachment(Base):
    """Электронный файл, приложенный к карточке описи, акта, запроса или
    номенклатуры (п. 8). Хранится в том же объектном хранилище, что и документы."""
    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    owner_type: Mapped[str] = mapped_column(String(32), index=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(255), default="application/octet-stream")
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    storage_key: Mapped[str] = mapped_column(String(1024))
    checksum_sha256: Mapped[str] = mapped_column(String(64), default="")
    uploaded_by: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChangeHistory(Base):
    """История изменений записей (п. 8 «Администрирование», п. 9): что, кем и
    когда изменено — по отдельным полям, со старым и новым значением."""
    __tablename__ = "change_history"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    user_email: Mapped[str] = mapped_column(String(255), index=True)
    object_type: Mapped[str] = mapped_column(String(32), index=True)
    object_id: Mapped[str] = mapped_column(String(64), index=True)
    field: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[str] = mapped_column(Text, default="")
    new_value: Mapped[str] = mapped_column(Text, default="")


class DocTypeAccess(Base):
    """Доступ роли к категории документов (п. 8: «настройка параметров доступа к
    документам в зависимости от категорий и типов документов»). Для роли без
    записей ограничений нет; с записями — видны только перечисленные группы."""
    __tablename__ = "doc_type_access"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    role: Mapped[str] = mapped_column(String(32), index=True)
    doc_group: Mapped[str] = mapped_column(String(128))


class SupportTicket(Base):
    """Обращение в службу поддержки (п. 8), инцидент со сроками SLA (ТС-176
    разд. 13), инцидент ИБ (разд. 14 п. 9) или заявка на дополнительную услугу
    из Личного кабинета (разд. 14 п. 2.9, 2.10, 6.1). Виды, уровни и статусы —
    в services/sla.py."""
    __tablename__ = "support_tickets"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_email: Mapped[str] = mapped_column(String(255), index=True)
    subject: Mapped[str] = mapped_column(String(512))
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="Новое", index=True)
    answer: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    kind: Mapped[str] = mapped_column(String(32), default="question", index=True)
    service: Mapped[str] = mapped_column(String(32), default="")
    # Уровень критичности определяет заказчик (п. 13.1.1.1.3)
    criticality: Mapped[str] = mapped_column(String(16), default="medium", index=True)
    # Сроки фиксируются при регистрации обращения
    reaction_due: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolution_due: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reacted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    assignee: Mapped[str] = mapped_column(String(255), default="")
    reopen_count: Mapped[int] = mapped_column(Integer, default=0)


class AvailabilitySample(Base):
    """Поминутная отметка доступности системы для «процента доступности»
    (ТС-176 п. 13.1.2.2). Минута без отметки считается недоступностью."""
    __tablename__ = "availability_samples"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    minute: Mapped[datetime] = mapped_column(DateTime, unique=True, index=True)
    ok: Mapped[bool] = mapped_column(default=True)


class ApiKey(Base):
    """Ключ доступа внешней информационной системы к API (п. 7, 9). Хранится
    только хэш; сам ключ показывается один раз при создании."""
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    prefix: Mapped[str] = mapped_column(String(16), index=True)
    key_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.viewer)
    created_by: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ImportJob(Base):
    """Задание массового импорта пакета документов (п. 8, модуль импорта)."""
    __tablename__ = "import_jobs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    filename: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="В обработке", index=True)
    total: Mapped[int] = mapped_column(Integer, default=0)
    created_documents: Mapped[int] = mapped_column(Integer, default=0)
    created_cases: Mapped[int] = mapped_column(Integer, default=0)
    skipped_duplicates: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[str] = mapped_column(Text, default="[]")            # JSON
    created_by: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
