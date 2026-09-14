"""Выгрузка архива в XML (п. 14.1.4–14.1.5 ТС-176).

ТЗ требует передавать данные «в виде выгрузки файла в формате XML с сохранением
бизнес целостности документа, ЭЦП документа, маршрут документа, цепочки
документов, привязка к номенклатуре дел». Здесь формируется именно такой
документ: дела с их документами, статусы ЭЦП и подписанты, цепочки замены
(replaces/superseded), маршруты согласования и привязка к статьям номенклатуры.
"""
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, tostring

from sqlalchemy.orm import Session

from ..models import (
    ApprovalRequest, Case, Document, NomenclatureItem, Organization, RegCard,
)

SCHEMA_VERSION = "1.0"


def _t(el: Element, name: str, value) -> None:
    """Дочерний элемент с текстом — пустые значения не засоряют выгрузку."""
    if value in (None, ""):
        return
    SubElement(el, name).text = str(value)


def _iso(value) -> str:
    return value.isoformat() if value is not None else ""


def _document_el(parent: Element, db: Session, doc: Document) -> None:
    d = SubElement(parent, "document", {"id": doc.id})
    _t(d, "title", doc.title)
    _t(d, "description", doc.description)
    _t(d, "doc_type", doc.doc_type.value if doc.doc_type else "")
    _t(d, "doc_number", doc.doc_number)
    _t(d, "doc_date", _iso(doc.doc_date))
    _t(d, "counterparty", doc.counterparty)
    if doc.amount is not None:
        _t(d, "amount", doc.amount)
        _t(d, "currency", doc.currency)
    _t(d, "fond", doc.fond)
    _t(d, "opis", doc.opis)
    _t(d, "delo", doc.delo)
    _t(d, "status", doc.status.value if doc.status else "")
    _t(d, "annotation", doc.annotation)
    _t(d, "created_at", _iso(doc.created_at))

    # Файл и контрольная характеристика — целостность выгруженного документа
    f = SubElement(d, "file")
    _t(f, "name", doc.original_filename)
    _t(f, "content_type", doc.content_type)
    _t(f, "size", doc.size)
    _t(f, "sha256", doc.checksum_sha256)
    _t(f, "storage_key", doc.storage_key)
    if doc.pdfa_key:
        _t(f, "pdfa_key", doc.pdfa_key)
    # Электронная копия (ТС-176 п. 11.6). Подпись удостоверения в выгрузку не
    # входит, поэтому при приёме пакета копия снова проходит сверку.
    if doc.copy_status:
        _t(d, "copy_status", doc.copy_status)

    # ЭЦП документа
    sig = SubElement(d, "signature")
    _t(sig, "status", doc.signature_status.value if doc.signature_status else "none")
    _t(sig, "signer", doc.signer_info)

    # Срок хранения и привязка к номенклатуре
    ret = SubElement(d, "retention")
    _t(ret, "label", "Постоянно" if doc.permanent else doc.retention_label)
    _t(ret, "years", doc.retention_years)
    _t(ret, "permanent", "true" if doc.permanent else "false")
    _t(ret, "until", _iso(doc.retention_until))
    _t(ret, "destroyed_at", _iso(doc.destroyed_at))

    # Цепочка версий документа (замена при изменении, напр. смена собственника)
    if doc.replaces_id or doc.superseded_at:
        ch = SubElement(d, "chain")
        _t(ch, "replaces_id", doc.replaces_id)
        _t(ch, "superseded_at", _iso(doc.superseded_at))

    # ЭРКК (регистрационно-контрольная карточка)
    card = db.query(RegCard).filter(RegCard.document_id == doc.id).first()
    if card is not None:
        rc = SubElement(d, "regcard")
        _t(rc, "reg_number", card.reg_number)
        _t(rc, "reg_date", _iso(card.reg_date))
        _t(rc, "executor", card.executor)

    if doc.cadastral_number or doc.real_estate_address:
        re_el = SubElement(d, "real_estate")
        _t(re_el, "cadastral_number", doc.cadastral_number)
        _t(re_el, "address", doc.real_estate_address)
        _t(re_el, "area", doc.real_estate_area)

    # Маршрут согласования карточки
    for req in db.query(ApprovalRequest).filter(
        ApprovalRequest.object_type == "document", ApprovalRequest.object_id == doc.id
    ).all():
        _approval_el(d, req)


def _approval_el(parent: Element, req: ApprovalRequest) -> None:
    a = SubElement(parent, "approval", {"id": req.id})
    _t(a, "status", req.status.value if req.status else "")
    _t(a, "created_by", req.created_by)
    _t(a, "created_at", _iso(req.created_at))
    _t(a, "closed_at", _iso(req.closed_at))
    for st in sorted(req.steps, key=lambda s: s.order_no):
        s = SubElement(a, "step", {"order": str(st.order_no)})
        _t(s, "approver", st.approver_email)
        _t(s, "approver_name", st.approver_name)
        _t(s, "status", st.status.value if st.status else "")
        _t(s, "comment", st.comment)
        _t(s, "decided_at", _iso(st.decided_at))


def _case_el(parent: Element, db: Session, case: Case) -> None:
    c = SubElement(parent, "case", {"id": case.id})
    _t(c, "index", case.index)
    _t(c, "title", case.title)
    _t(c, "year", case.year)
    _t(c, "volume", case.volume)
    _t(c, "status", case.status.value if case.status else "")
    _t(c, "date_from", _iso(case.date_from))
    _t(c, "date_to", _iso(case.date_to))
    ret = SubElement(c, "retention")
    _t(ret, "label", "Постоянно" if case.permanent else case.retention_label)
    _t(ret, "years", case.retention_years)
    _t(ret, "permanent", "true" if case.permanent else "false")
    _t(ret, "until", _iso(case.retention_until))
    if case.nomenclature_id:
        nom = db.get(NomenclatureItem, case.nomenclature_id)
        if nom is not None:
            n = SubElement(c, "nomenclature_ref", {"id": nom.id})
            _t(n, "index", nom.index)
            _t(n, "title", nom.title)
            _t(n, "article", nom.article)

    docs_el = SubElement(c, "documents")
    docs = (
        db.query(Document)
        .filter(Document.case_id == case.id)
        .order_by(Document.doc_date.asc().nullslast(), Document.created_at.asc())
        .all()
    )
    for doc in docs:
        _document_el(docs_el, db, doc)

    for req in db.query(ApprovalRequest).filter(
        ApprovalRequest.object_type == "case", ApprovalRequest.object_id == case.id
    ).all():
        _approval_el(c, req)


def build(db: Session, case: Case | None = None) -> bytes:
    """XML одного дела либо всего архива (если case не задан)."""
    root = Element("earchive", {
        "schema": SCHEMA_VERSION,
        "generated_at": datetime.utcnow().isoformat(),
        "scope": "case" if case is not None else "archive",
    })

    org = db.query(Organization).first()
    if org is not None:
        o = SubElement(root, "organization")
        _t(o, "name", org.name)
        _t(o, "bin", org.bin)
        _t(o, "address", org.address)
        _t(o, "head_name", org.head_name)
        _t(o, "head_position", org.head_position)

    if case is None:
        nom_el = SubElement(root, "nomenclature")
        for item in db.query(NomenclatureItem).order_by(
            NomenclatureItem.year.desc(), NomenclatureItem.index
        ).all():
            n = SubElement(nom_el, "item", {"id": item.id})
            _t(n, "index", item.index)
            _t(n, "title", item.title)
            _t(n, "year", item.year)
            _t(n, "article", item.article)
            _t(n, "retention_label",
               "Постоянно" if item.permanent else item.retention_label)

    cases_el = SubElement(root, "cases")
    cases = [case] if case is not None else db.query(Case).order_by(
        Case.year.desc(), Case.index
    ).all()
    for c in cases:
        _case_el(cases_el, db, c)

    if case is None:
        # Документы вне дел тоже должны попасть в выгрузку, иначе архив
        # выгрузился бы неполным.
        loose = db.query(Document).filter(Document.case_id.is_(None)).all()
        if loose:
            loose_el = SubElement(root, "documents_without_case")
            for doc in loose:
                _document_el(loose_el, db, doc)

    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(root, encoding="utf-8")
