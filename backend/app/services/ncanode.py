"""Проверка ЭЦП через NCANode по Правилам проверки подлинности ЭЦП (приказ
Министра по инвестициям и развитию РК от 9 декабря 2015 года № 1187).

Правила требуют подтвердить принадлежность и действительность открытого ключа
и регистрационного свидетельства: цепочку сертификатов до корневого НУЦ РК,
срок действия и отсутствие отзыва. Подписанты заказчика используют сертификаты
НУЦ по ГОСТ 34.10-2015, которые библиотека cryptography не проверяет, поэтому
проверка вынесена в NCANode — открытый сервис на криптопровайдере НУЦ РК,
развёрнутый в контуре заказчика (docker-compose.kazpost.yml).

Адаптер рассчитан на API NCANode 3.x (POST /cms/verify). Разбор ответа терпим
к отсутствующим полям; при смене версии NCANode формат сверяется тестом
tests/test_ncanode.py на ответе развёрнутого сервиса.
"""
import base64
import json
import logging
import urllib.error
import urllib.request

from ..config import settings
from ..models import SignatureStatus
from .signature import VerifyResult

log = logging.getLogger("ncanode")


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        settings.NCANODE_URL.rstrip("/") + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=settings.NCANODE_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _identity(subject: dict) -> str:
    parts = []
    for label, key in (("ФИО", "commonName"), ("Организация", "organization"),
                       ("ИИН", "iin"), ("БИН", "bin")):
        if subject.get(key):
            parts.append(f"{label}: {subject[key]}")
    return "; ".join(parts) or "неизвестный владелец"


def interpret(response: dict) -> VerifyResult:
    """Ответ NCANode → результат проверки.

    Действительной подпись признаётся, только если NCANode подтвердил и саму
    подпись, и цепочку сертификатов, и получил статус отзыва: подпись, отзыв
    сертификата которой проверить не удалось, по Правилам не подтверждена."""
    signers = response.get("signers") or []
    certs = (signers[0].get("certificates") or []) if signers else []
    cert = certs[0] if certs else {}
    identity = _identity(cert.get("subject") or {})

    if not signers:
        return VerifyResult(SignatureStatus.invalid, identity,
                            f"NCANode: {response.get('message') or 'подпись не разобрана'}")
    if not certs:
        return VerifyResult(SignatureStatus.invalid, identity, "В подписи нет сертификата")

    revocations = [r for c in certs for r in (c.get("revocations") or [])]
    revoked = [r for r in revocations if r.get("revoked")]
    if revoked:
        r = revoked[0]
        reason = f", причина: {r['reason']}" if r.get("reason") else ""
        return VerifyResult(SignatureStatus.invalid, identity,
                            f"Сертификат отозван (проверено по {r.get('by') or 'OCSP/CRL'}{reason})")
    if not response.get("valid") or any(c.get("valid") is False for c in certs):
        return VerifyResult(SignatureStatus.invalid, identity,
                            response.get("message")
                            or "Подпись, срок действия или цепочка сертификатов недействительны")
    if not revocations:
        return VerifyResult(SignatureStatus.unsupported, identity,
                            "Подпись и цепочка корректны, но статус отзыва сертификата не получен")
    by = ", ".join(sorted({r.get("by") for r in revocations if r.get("by")})) or "OCSP/CRL"
    return VerifyResult(SignatureStatus.valid, identity,
                        "Подпись действительна: цепочка до корневого сертификата НУЦ РК "
                        f"подтверждена, отзыв проверен по {by}")


def verify_cms(cms_base64: str, content: bytes | None = None) -> VerifyResult:
    """content — подписанные данные для откреплённой подписи; для
    прикреплённой не передаётся."""
    methods = [m.strip() for m in settings.SIGNATURE_REVOCATION_CHECK.split(",") if m.strip()]
    body: dict = {"cms": cms_base64, "revocationCheck": methods}
    if content is not None:
        body["data"] = base64.b64encode(content).decode("ascii")
    try:
        response = _post("/cms/verify", body)
    except urllib.error.HTTPError as exc:
        # Отказ в проверке NCANode возвращает телом с описанием — разбираем его.
        try:
            response = json.loads(exc.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return VerifyResult(SignatureStatus.unsupported, "",
                                f"Сервис проверки ЭЦП ответил ошибкой {exc.code}")
    except Exception as exc:  # noqa: BLE001
        log.warning("NCANode недоступен: %s", exc)
        return VerifyResult(SignatureStatus.unsupported, "",
                            "Сервис проверки ЭЦП (NCANode) недоступен — подпись не проверена")
    return interpret(response)
