# -*- coding: utf-8 -*-
"""Проверка ЭЦП через NCANode (Правила № 1187, ТС-176 разд. 14 п. 7).

Образцы ответов повторяют формат API NCANode 3.x. При смене версии сервиса
сверьте их с реальным ответом POST /cms/verify.
"""
from app.models import SignatureStatus
from app.services import ncanode, signature

SUBJECT = {
    "commonName": "ТЕСТОВ ТЕСТ",
    "iin": "900101300123",
    "bin": "110341007055",
    "organization": "Филиал АО «QAZPOST DIGITAL»",
}


def _response(valid=True, cert_valid=True, revocations=None):
    if revocations is None:
        revocations = [{"revoked": False, "by": "OCSP"}]
    return {
        "status": 200, "message": "", "valid": valid,
        "signers": [{"certificates": [{
            "valid": cert_valid, "subject": SUBJECT, "revocations": revocations,
        }]}],
    }


def test_valid_signature_with_ocsp():
    result = ncanode.interpret(_response())
    assert result.status == SignatureStatus.valid
    assert "900101300123" in result.signer_info
    assert "OCSP" in result.detail


def test_revoked_certificate_is_invalid():
    result = ncanode.interpret(_response(
        revocations=[{"revoked": True, "by": "OCSP", "reason": "keyCompromise"}]))
    assert result.status == SignatureStatus.invalid
    assert "отозван" in result.detail


def test_broken_signature_or_chain_is_invalid():
    assert ncanode.interpret(_response(valid=False)).status == SignatureStatus.invalid
    assert ncanode.interpret(_response(cert_valid=False)).status == SignatureStatus.invalid


def test_unknown_revocation_status_is_not_confirmed():
    """Без статуса отзыва подпись по Правилам не подтверждена."""
    assert ncanode.interpret(_response(revocations=[])).status == SignatureStatus.unsupported


def test_error_response_without_signers():
    result = ncanode.interpret({"status": 400, "message": "Invalid CMS"})
    assert result.status == SignatureStatus.invalid
    assert "Invalid CMS" in result.detail


def test_confirmation_policy_depends_on_verifier(monkeypatch):
    from app.config import settings

    unsupported = signature.VerifyResult(SignatureStatus.unsupported, "", "")
    monkeypatch.setattr(settings, "SIGNATURE_VERIFIER", "ncanode")
    assert signature.is_confirmed(unsupported) is False
    monkeypatch.setattr(settings, "SIGNATURE_VERIFIER", "local")
    assert signature.is_confirmed(unsupported) is True
