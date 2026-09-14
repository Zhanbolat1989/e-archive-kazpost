"""Вход по ключам доступа WebAuthn — биометрия или PIN устройства
(ТС-176 разд. 14 п. 4.2: «вход в мобильной версии по биометрии»).

Закрытый ключ не покидает защищённое хранилище телефона, а открывает его
отпечаток или лицо владельца: проверка пользователя обязательна. Сервер хранит
только открытый ключ и счётчик подписей. Ключ с проверкой пользователя — это
сразу два фактора (владение устройством и биометрия), поэтому код на email
после такого входа не запрашивается.

Ключи обнаруживаемые (resident key): при входе email не вводится, устройство
само предлагает сохранённый ключ, и ответ сервера не выдаёт, существует ли
учётная запись.

Криптографию выполняет библиотека py_webauthn (импорт — внутри функций); здесь
же — параметры вызова и правила вокруг неё, проверяемые без библиотеки.
"""
import base64
import json
from datetime import datetime, timedelta

from ..config import settings

CHALLENGE_TTL = timedelta(minutes=5)
# Отработанные вызовы старше этого срока удаляются при выдаче новых.
CLEANUP_AFTER = timedelta(days=1)
TIMEOUT_MS = 60_000

_DEVICES = (
    ("iphone", "iPhone"), ("ipad", "iPad"), ("android", "Android"),
    ("windows", "Windows"), ("macintosh", "Mac"), ("linux", "Linux"),
)


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def from_b64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def origins() -> list[str]:
    return [o.strip() for o in settings.WEBAUTHN_ORIGINS.split(",") if o.strip()]


def challenge_problem(challenge, purpose: str, now: datetime) -> str | None:
    """Почему вызов нельзя принять; None — можно."""
    if challenge is None or challenge.purpose != purpose:
        return "Запрос не найден — начните заново"
    if challenge.used_at is not None:
        return "Запрос уже использован — начните заново"
    if challenge.expires_at <= now:
        return "Время на подтверждение истекло — начните заново"
    return None


def credential_id(credential: dict) -> str:
    return str(credential.get("id") or credential.get("rawId") or "")


def transports(credential: dict) -> list[str]:
    raw = (credential.get("response") or {}).get("transports") or []
    return [t for t in raw if isinstance(t, str)][:8]


def device_name(user_agent: str) -> str:
    """Название ключа по умолчанию — по устройству, с которого он добавлен."""
    ua = (user_agent or "").lower()
    for marker, name in _DEVICES:
        if marker in ua:
            return name
    return "Устройство"


def registration_options(user, existing_ids: list[str]) -> tuple[str, dict]:
    """(вызов, параметры для navigator.credentials.create)."""
    from webauthn import generate_registration_options, options_to_json
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor,
        ResidentKeyRequirement, UserVerificationRequirement,
    )

    options = generate_registration_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=user.id.encode(),
        user_name=user.email,
        user_display_name=user.full_name or user.email,
        # Одно устройство — один ключ: повторная регистрация того же ключа отклоняется.
        exclude_credentials=[PublicKeyCredentialDescriptor(id=from_b64url(c)) for c in existing_ids],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        timeout=TIMEOUT_MS,
    )
    return b64url(options.challenge), json.loads(options_to_json(options))


def verify_registration(credential: dict, challenge: str) -> dict:
    """Проверяет ответ устройства при добавлении ключа; исключение — ключ не принят."""
    from webauthn import verify_registration_response

    verified = verify_registration_response(
        credential=json.dumps(credential),
        expected_challenge=from_b64url(challenge),
        expected_rp_id=settings.WEBAUTHN_RP_ID,
        expected_origin=origins(),
        require_user_verification=True,
    )
    return {
        "credential_id": b64url(verified.credential_id),
        "public_key": b64url(verified.credential_public_key),
        "sign_count": verified.sign_count,
        "aaguid": str(verified.aaguid or ""),
        "backed_up": bool(verified.credential_backed_up),
    }


def authentication_options() -> tuple[str, dict]:
    """(вызов, параметры для navigator.credentials.get) без списка ключей:
    устройство само предлагает обнаруживаемый ключ этого сайта."""
    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers.structs import UserVerificationRequirement

    options = generate_authentication_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        user_verification=UserVerificationRequirement.REQUIRED,
        timeout=TIMEOUT_MS,
    )
    return b64url(options.challenge), json.loads(options_to_json(options))


def verify_authentication(credential: dict, challenge: str, public_key: str,
                          sign_count: int) -> int:
    """Проверяет подпись входа; возвращает новый счётчик подписей.

    Библиотека отклоняет ответ, если счётчик не вырос, хотя аутентификатор его
    ведёт: так распознаётся скопированный ключ."""
    from webauthn import verify_authentication_response

    verified = verify_authentication_response(
        credential=json.dumps(credential),
        expected_challenge=from_b64url(challenge),
        expected_rp_id=settings.WEBAUTHN_RP_ID,
        expected_origin=origins(),
        credential_public_key=from_b64url(public_key),
        credential_current_sign_count=sign_count,
        require_user_verification=True,
    )
    return verified.new_sign_count
