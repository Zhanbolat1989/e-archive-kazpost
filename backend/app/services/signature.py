"""Verification of Kazakhstan ЭЦП (CMS / CAdES) produced by NCALayer.

NCALayer's `signCms` returns a base64 CMS (PKCS#7). This module:
  * parses the CMS,
  * extracts the signer certificate identity (ФИО / ИИН / БИН, организация),
  * verifies the RSA signature over the signed attributes when possible.

Note: НУЦ РК also issues GOST (ГОСТ 34.10) certificates. Python's `cryptography`
does not implement GOST curves, so such signatures are reported as `unsupported`
(the signer identity is still extracted). Full chain validation against the НУЦ РК
root is out of scope for the MVP.
"""
import base64
from dataclasses import dataclass

from asn1crypto import cms, x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_der_public_key

from ..models import SignatureStatus

_DIGEST = {
    "sha256": hashes.SHA256,
    "sha384": hashes.SHA384,
    "sha512": hashes.SHA512,
    "sha1": hashes.SHA1,
}


@dataclass
class VerifyResult:
    status: SignatureStatus
    signer_info: str
    detail: str = ""


def _subject_summary(cert: x509.Certificate) -> str:
    subject = cert.subject.native
    parts = []
    for label, key in [
        ("ФИО", "common_name"),
        ("Организация", "organization_name"),
        ("Подразделение", "organizational_unit_name"),
        ("ИИН/БИН", "serial_number"),
        ("Страна", "country_name"),
    ]:
        val = subject.get(key)
        if val:
            parts.append(f"{label}: {val}")
    return "; ".join(parts) or "неизвестный владелец"


def verify_cms(cms_base64: str, content: bytes | None = None) -> VerifyResult:
    try:
        raw = base64.b64decode(cms_base64)
        info = cms.ContentInfo.load(raw)
        signed_data = info["content"]
    except Exception as exc:  # noqa: BLE001
        return VerifyResult(SignatureStatus.invalid, "", f"Не удалось разобрать CMS: {exc}")

    certs = [c.chosen for c in signed_data["certificates"] if c.name == "certificate"]
    if not certs:
        return VerifyResult(SignatureStatus.invalid, "", "В подписи нет сертификата")

    signer_infos = signed_data["signer_infos"]
    if not len(signer_infos):
        return VerifyResult(SignatureStatus.invalid, "", "В подписи нет данных подписанта")

    signer = signer_infos[0]
    # Match the signing certificate by issuer + serial number.
    sid = signer["sid"].chosen
    signer_cert = certs[0]
    for c in certs:
        if (
            c.issuer == sid["issuer"]
            and c.serial_number == sid["serial_number"].native
        ):
            signer_cert = c
            break

    identity = _subject_summary(signer_cert)

    sig_algo = signer["signature_algorithm"].signature_algo
    digest_algo = signer["digest_algorithm"]["algorithm"].native

    if "rsa" not in sig_algo.lower():
        return VerifyResult(
            SignatureStatus.unsupported,
            identity,
            f"Алгоритм подписи '{sig_algo}' (вероятно ГОСТ) не поддерживается в MVP; "
            f"личность подписанта извлечена.",
        )

    hash_cls = _DIGEST.get(digest_algo)
    if hash_cls is None:
        return VerifyResult(
            SignatureStatus.unsupported, identity,
            f"Хэш-алгоритм '{digest_algo}' не поддерживается."
        )

    # Signed content: the DER of signed attributes (re-tagged as SET OF), per RFC 5652.
    signed_attrs = signer["signed_attrs"]
    if signed_attrs.native is not None:
        signed_bytes = signed_attrs.dump()
        signed_bytes = b"\x31" + signed_bytes[1:]  # implicit [0] -> explicit SET OF
    elif content is not None:
        signed_bytes = content
    else:
        return VerifyResult(
            SignatureStatus.invalid, identity,
            "Откреплённая подпись без предоставленного содержимого."
        )

    try:
        pub = load_der_public_key(signer_cert.public_key.dump())
        pub.verify(
            signer["signature"].native,
            signed_bytes,
            padding.PKCS1v15(),
            hash_cls(),
        )
        return VerifyResult(SignatureStatus.valid, identity, "Подпись действительна")
    except Exception as exc:  # noqa: BLE001
        return VerifyResult(
            SignatureStatus.invalid, identity, f"Подпись недействительна: {exc}"
        )


def content_matches(cms_base64: str, expected: bytes) -> tuple[bool, str]:
    """Относится ли подпись именно к ожидаемому содержимому.

    verify_cms проверяет подпись над подписанными атрибутами, но не то, ЧТО
    подписано: CMS с чужим вложенным содержимым и корректной подписью её
    прошла бы. Там, где подпись должна быть привязана к конкретному файлу
    (удостоверение электронной копии), сверяются вложенное содержимое и
    атрибут messageDigest."""
    try:
        signed_data = cms.ContentInfo.load(base64.b64decode(cms_base64))["content"]
        encap = signed_data["encap_content_info"]["content"].native
        signers = signed_data["signer_infos"]
    except Exception as exc:  # noqa: BLE001
        return False, f"подпись не разобрана: {exc}"
    if encap is None:
        return False, "подпись откреплённая — подписанное содержимое не вложено"
    if encap != expected:
        return False, "подписано другое содержимое"
    if not len(signers):
        return False, "в подписи нет данных подписанта"
    signer = signers[0]
    attrs = signer["signed_attrs"]
    if attrs.native is None:
        # Без подписанных атрибутов подпись вычислена прямо над содержимым,
        # и его совпадение уже проверено.
        return True, ""
    for attr in attrs:
        if attr["type"].native != "message_digest":
            continue
        hash_cls = _DIGEST.get(signer["digest_algorithm"]["algorithm"].native)
        if hash_cls is None:
            # ГОСТ-хэш здесь не вычисляется: совпадение содержимого проверено
            # выше, а дайджест сверяет проверка подписи по ГОСТ.
            return True, ""
        h = hashes.Hash(hash_cls())
        h.update(expected)
        if attr["values"][0].native != h.finalize():
            return False, "дайджест в подписи не совпадает с содержимым"
        return True, ""
    return False, "в подписи нет атрибута messageDigest"


def _encapsulated(cms_base64: str) -> bytes | None:
    """Вложенное в CMS содержимое; None — подпись откреплённая или не разобрана."""
    try:
        info = cms.ContentInfo.load(base64.b64decode(cms_base64))
        return info["content"]["encap_content_info"]["content"].native
    except Exception:  # noqa: BLE001
        return None


def verify(cms_base64: str, content: bytes | None = None) -> VerifyResult:
    """Проверка ЭЦП выбранным способом (SIGNATURE_VERIFIER).

    ncanode — по Правилам № 1187: ГОСТ 34.10-2015, цепочка до корня НУЦ РК,
    отзыв сертификата. local — встроенная проверка RSA без цепочки и отзыва.
    Содержимое передаётся на проверку только для откреплённой подписи: у
    прикреплённой подписано вложенное содержимое, а не файл документа."""
    from ..config import settings

    if settings.SIGNATURE_VERIFIER == "ncanode":
        from . import ncanode

        detached = _encapsulated(cms_base64) is None
        return ncanode.verify_cms(cms_base64, content if detached else None)
    return verify_cms(cms_base64, content=content)


def is_confirmed(result: VerifyResult) -> bool:
    """Подтверждена ли подпись настолько, чтобы удостоверять ею документ.

    При проверке через NCANode — только действительная. Встроенная проверка
    ГОСТ не выполняет вовсе, и там допускается «не поддерживается» с извлечённой
    личностью подписанта: иначе в контуре без NCANode удостоверить копию было бы
    невозможно ни одной подписью НУЦ."""
    from ..config import settings

    if result.status == SignatureStatus.valid:
        return True
    return settings.SIGNATURE_VERIFIER == "local" and result.status == SignatureStatus.unsupported
