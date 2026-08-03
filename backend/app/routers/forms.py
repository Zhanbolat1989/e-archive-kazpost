import hashlib
import io
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, HTMLResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User, Role, Case, Document, DocStatus, DocType
from ..security import get_current_user, require_roles
from ..services import forms as forms_svc
from ..services import storage, search

router = APIRouter(prefix="/api/cases", tags=["forms"])

_MEDIA = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _load(case_id: str, db: Session) -> tuple[Case, list[Document]]:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Дело не найдено")
    # Внутренняя опись учитывается отдельно от документов дела — системные
    # описи (DocType.inventory) в строки форм не включаются.
    docs = (
        db.query(Document)
        .filter(Document.case_id == case_id, Document.doc_type != DocType.inventory)
        .order_by(Document.doc_date.asc().nullslast(), Document.created_at)
        .all()
    )
    return case, docs


@router.get("/{case_id}/forms/{kind}")
def get_form(
    case_id: str,
    kind: str,
    fmt: str = Query("pdf", pattern="^(pdf|docx|html)$"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if kind not in forms_svc.FORMS:
        raise HTTPException(status_code=404, detail="Неизвестная форма")
    case, docs = _load(case_id, db)
    title, _fn = forms_svc.FORMS[kind]
    if fmt == "html":
        return HTMLResponse(forms_svc.render_html(kind, case, docs))
    data = (forms_svc.render_pdf(kind, case, docs) if fmt == "pdf"
            else forms_svc.render_docx(kind, case, docs))
    # HTTP-заголовки — только latin-1: не-ASCII символы из имени убираем.
    idx = "".join(c for c in (case.index or "delo").replace("/", "-") if ord(c) < 128) or "delo"
    fname = f"{kind}_{idx}_{case.year}.{fmt}"
    return StreamingResponse(
        io.BytesIO(data),
        media_type=_MEDIA[fmt],
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/{case_id}/forms/{kind}/archive", status_code=201)
def archive_form(
    case_id: str,
    kind: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.admin, Role.archivist)),
):
    """Сформировать PDF формы и поместить её в архив (WORM) как документ дела."""
    if kind not in forms_svc.FORMS:
        raise HTTPException(status_code=404, detail="Неизвестная форма")
    case, docs = _load(case_id, db)
    title, _fn = forms_svc.FORMS[kind]
    data = forms_svc.render_pdf(kind, case, docs)

    doc_id = str(uuid.uuid4())
    fname = f"{kind}_{(case.index or 'delo').replace('/', '-')}_{case.year}.pdf"
    storage_key = f"{datetime.utcnow():%Y/%m}/{doc_id}/{fname}"
    storage.put_original(storage_key, data, "application/pdf")

    doc = Document(
        id=doc_id,
        title=f"{title} — дело {case.index or ''} {case.title}"[:500],
        description=f"Сформировано системой по делу {case.index} ({case.year})",
        doc_type=DocType.inventory,
        doc_number=f"{kind}-{case.index}-{case.year}",
        case_id=case.id,
        original_filename=fname,
        content_type="application/pdf",
        size=len(data),
        storage_key=storage_key,
        checksum_sha256=hashlib.sha256(data).hexdigest(),
        status=DocStatus.ready,
        status_detail="Готов (сформировано системой)",
        owner_id=user.id,
        permanent=case.permanent,
        retention_label=case.retention_label,
        retention_years=case.retention_years,
        retention_until=case.retention_until,
    )
    db.add(doc)
    db.commit()
    try:
        search.index_document({
            "id": doc.id, "title": doc.title, "description": doc.description,
            "ocr_text": "", "fond": "", "opis": "", "delo": case.index,
            "doc_type": doc.doc_type.value, "doc_number": doc.doc_number,
            "counterparty": "", "doc_date": None, "amount": None,
            "status": DocStatus.ready.value, "created_at": doc.created_at.isoformat(),
        })
    except Exception:  # noqa: BLE001
        pass
    return {"id": doc.id, "title": doc.title, "size": len(data)}
