# -*- coding: utf-8 -*-
"""Электронные копии (ТС-176 п. 11.6–11.7): переходы состояний и привязка
удостоверяющей ЭЦП к конкретному файлу копии."""
import base64
import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from app.models import SignatureStatus
from app.services import ecopies, signature


# ------------------------------------------------------------------ состояния
def test_only_unchecked_copy_can_be_certified():
    ecopies.check_certify(ecopies.PENDING)
    for status in (ecopies.CERTIFIED, ecopies.MISMATCH, ecopies.NO_ORIGINAL, ""):
        with pytest.raises(ValueError):
            ecopies.check_certify(status)


def test_certified_copy_is_not_overturned_or_unmarked():
    with pytest.raises(ValueError):
        ecopies.check_reconcile(ecopies.CERTIFIED, ecopies.MISMATCH)
    with pytest.raises(ValueError):
        ecopies.check_unmark(ecopies.CERTIFIED)


def test_reconcile_records_only_negative_results():
    ecopies.check_reconcile(ecopies.PENDING, ecopies.NO_ORIGINAL)
    ecopies.check_reconcile(ecopies.MISMATCH, ecopies.NO_ORIGINAL)
    with pytest.raises(ValueError):
        ecopies.check_reconcile(ecopies.PENDING, ecopies.CERTIFIED)
    with pytest.raises(ValueError):
        ecopies.check_reconcile("", ecopies.MISMATCH)   # не копия


def test_only_rejected_copies_go_to_destruction_act():
    for status in ecopies.DESTROYABLE:
        ecopies.check_destroyable(status)
    for status in (ecopies.PENDING, ecopies.CERTIFIED):
        with pytest.raises(ValueError):
            ecopies.check_destroyable(status)


# ------------------------------------------------------ привязка подписи к файлу
def _attached_cms(content: bytes, digest_of: bytes | None = None) -> str:
    """CMS с вложенным содержимым и подписанными атрибутами — как у NCALayer.
    digest_of — что попадает в messageDigest (для подделки: не то, что вложено)."""
    from asn1crypto import algos, cms
    from asn1crypto import x509 as ax509
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ТЕСТОВ ТЕСТ")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(1)
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=1))
            .sign(key, hashes.SHA256()))
    acert = ax509.Certificate.load(cert.public_bytes(serialization.Encoding.DER))

    digest = hashlib.sha256(content if digest_of is None else digest_of).digest()
    attrs = cms.CMSAttributes([
        cms.CMSAttribute({"type": "content_type", "values": ["data"]}),
        cms.CMSAttribute({"type": "message_digest", "values": [digest]}),
    ])
    sig = key.sign(attrs.dump(), padding.PKCS1v15(), hashes.SHA256())
    signer = cms.SignerInfo({
        "version": "v1",
        "sid": cms.SignerIdentifier({"issuer_and_serial_number": cms.IssuerAndSerialNumber({
            "issuer": acert.issuer, "serial_number": acert.serial_number,
        })}),
        "digest_algorithm": algos.DigestAlgorithm({"algorithm": "sha256"}),
        "signed_attrs": attrs,
        "signature_algorithm": algos.SignedDigestAlgorithm({"algorithm": "sha256_rsa"}),
        "signature": sig,
    })
    signed_data = cms.SignedData({
        "version": "v1",
        "digest_algorithms": [algos.DigestAlgorithm({"algorithm": "sha256"})],
        "encap_content_info": {"content_type": "data", "content": content},
        "certificates": [acert],
        "signer_infos": [signer],
    })
    info = cms.ContentInfo({"content_type": "signed_data", "content": signed_data})
    return base64.b64encode(info.dump()).decode()


CHECKSUM = hashlib.sha256(b"scan of paper page").hexdigest().encode()


def test_signature_over_this_copy_is_accepted():
    cms_b64 = _attached_cms(CHECKSUM)
    assert signature.verify_cms(cms_b64).status == SignatureStatus.valid
    assert signature.content_matches(cms_b64, CHECKSUM) == (True, "")


def test_signature_over_another_file_is_rejected():
    other = hashlib.sha256(b"another scan").hexdigest().encode()
    ok, why = signature.content_matches(_attached_cms(other), CHECKSUM)
    assert not ok and "другое содержимое" in why


def test_swapped_content_with_valid_signature_is_rejected():
    """Подпись корректна, но вложенное содержимое подменено: verify_cms такую
    подпись пропускает, и именно поэтому нужна content_matches."""
    forged = _attached_cms(CHECKSUM, digest_of=b"what was really signed")
    assert signature.verify_cms(forged).status == SignatureStatus.valid
    ok, why = signature.content_matches(forged, CHECKSUM)
    assert not ok and "дайджест" in why


def test_garbage_is_not_a_signature():
    ok, why = signature.content_matches("не base64!!", CHECKSUM)
    assert not ok and why
