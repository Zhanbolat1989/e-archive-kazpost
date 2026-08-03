from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User, Role, Document
from ..schemas import SignatureVerifyRequest, SignatureVerifyResponse
from ..security import require_roles
from ..services import signature, storage

router = APIRouter(prefix="/api/signatures", tags=["signatures"])


@router.post("/verify", response_model=SignatureVerifyResponse)
def verify_signature(
    payload: SignatureVerifyRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.admin, Role.archivist)),
):
    """Verify a Kazakhstan ЭЦП (CMS from NCALayer). If document_id is given and the
    signature is detached, the stored original is used as the signed content."""
    content = None
    if payload.document_id:
        doc = db.get(Document, payload.document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Документ не найден")
        try:
            content = storage.get_object(doc.storage_key)
        except Exception:  # noqa: BLE001
            content = None

    result = signature.verify_cms(payload.cms_base64, content=content)

    if payload.document_id:
        doc = db.get(Document, payload.document_id)
        if doc:
            doc.signature_status = result.status
            doc.signer_info = result.signer_info
            db.commit()

    return SignatureVerifyResponse(
        status=result.status, signer_info=result.signer_info, detail=result.detail
    )
