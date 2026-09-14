"""Вход по ключам доступа WebAuthn — биометрия или PIN устройства
(ТС-176 разд. 14 п. 4.2). Правила и вызовы библиотеки — services/passkeys.py.

Ключ добавляется в Личном кабинете после входа по паролю; вход по ключу
подчиняется тем же правилам, что и по паролю: отключённая или заблокированная
учётная запись не входит, каждая попытка пишется в аудиторский след.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import PasskeyCredential, User, WebAuthnChallenge
from ..schemas import PasskeyLogin, PasskeyOut, PasskeyRegister, Token
from ..security import get_current_user, open_session
from ..services import audit, passkeys

router = APIRouter(prefix="/api/auth/passkeys", tags=["auth"])


def _enabled() -> None:
    if not settings.WEBAUTHN_ENABLED:
        raise HTTPException(status_code=404, detail="Вход по ключам доступа не включён")


def _new_challenge(db: Session, purpose: str, challenge: str,
                   user_id: str | None = None) -> WebAuthnChallenge:
    now = datetime.utcnow()
    (db.query(WebAuthnChallenge)
     .filter(WebAuthnChallenge.expires_at < now - passkeys.CLEANUP_AFTER)
     .delete(synchronize_session=False))
    ch = WebAuthnChallenge(purpose=purpose, user_id=user_id, challenge=challenge,
                           expires_at=now + passkeys.CHALLENGE_TTL)
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return ch


def _take_challenge(db: Session, challenge_id: str, purpose: str) -> WebAuthnChallenge:
    """Вызов гасится при первой же попытке, удачной или нет."""
    ch = db.get(WebAuthnChallenge, challenge_id)
    now = datetime.utcnow()
    problem = passkeys.challenge_problem(ch, purpose, now)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    ch.used_at = now
    db.commit()
    return ch


def _credential_ids(db: Session, user_id: str) -> list[str]:
    return [c for (c,) in db.query(PasskeyCredential.credential_id)
            .filter(PasskeyCredential.user_id == user_id)]


@router.get("/status")
def passkeys_status() -> dict:
    """Публично: странице входа нужно знать, показывать ли кнопку."""
    return {"enabled": settings.WEBAUTHN_ENABLED}


@router.get("", response_model=list[PasskeyOut])
def my_passkeys(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return (db.query(PasskeyCredential)
            .filter(PasskeyCredential.user_id == user.id)
            .order_by(PasskeyCredential.created_at).all())


@router.post("/register/options")
def register_options(db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)) -> dict:
    _enabled()
    challenge, options = passkeys.registration_options(user, _credential_ids(db, user.id))
    ch = _new_challenge(db, "register", challenge, user.id)
    return {"challenge_id": ch.id, "options": options}


@router.post("/register", response_model=PasskeyOut, status_code=201)
def register(payload: PasskeyRegister, request: Request, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    _enabled()
    ch = _take_challenge(db, payload.challenge_id, "register")
    if ch.user_id != user.id:
        raise HTTPException(status_code=400, detail="Запрос выдан другому пользователю")
    try:
        data = passkeys.verify_registration(payload.credential, ch.challenge)
    except Exception as exc:  # noqa: BLE001
        audit.security(db, user, "auth.passkey_add", f"ключ не принят: {exc}"[:300],
                       request=request, result=False)
        raise HTTPException(status_code=400,
                            detail="Устройство не подтвердило ключ доступа") from exc
    if (db.query(PasskeyCredential.id)
            .filter(PasskeyCredential.credential_id == data["credential_id"]).first()):
        raise HTTPException(status_code=409, detail="Этот ключ доступа уже зарегистрирован")
    _, user_agent = audit.client_meta(request)
    key = PasskeyCredential(
        user_id=user.id,
        name=(payload.name.strip() or passkeys.device_name(user_agent))[:255],
        transports=passkeys.transports(payload.credential),
        **data,
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    audit.security(db, user, "auth.passkey_add", f"добавлен ключ доступа «{key.name}»",
                   request=request, object_type="passkey", object_id=key.id)
    return key


@router.delete("/{passkey_id}", status_code=204)
def delete_passkey(passkey_id: str, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    key = db.get(PasskeyCredential, passkey_id)
    if key is None or key.user_id != user.id:
        raise HTTPException(status_code=404, detail="Ключ доступа не найден")
    name = key.name
    db.delete(key)
    db.commit()
    audit.security(db, user, "auth.passkey_remove", f"удалён ключ доступа «{name}»",
                   request=request, object_type="passkey", object_id=passkey_id)


@router.post("/login/options")
def login_options(db: Session = Depends(get_db)) -> dict:
    _enabled()
    challenge, options = passkeys.authentication_options()
    ch = _new_challenge(db, "login", challenge)
    return {"challenge_id": ch.id, "options": options}


@router.post("/login", response_model=Token)
def login(payload: PasskeyLogin, request: Request, db: Session = Depends(get_db)):
    _enabled()
    ch = _take_challenge(db, payload.challenge_id, "login")
    cred_id = passkeys.credential_id(payload.credential)
    key = (db.query(PasskeyCredential).filter(PasskeyCredential.credential_id == cred_id).first()
           if cred_id else None)
    if key is None:
        audit.security(db, None, "auth.login", "вход по ключу доступа: ключ не зарегистрирован",
                       request=request, result=False, user_email=f"passkey:{cred_id[:16]}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ключ доступа не зарегистрирован — войдите по паролю и добавьте "
                   "устройство в Личном кабинете",
        )
    user = db.get(User, key.user_id)
    if user is None or not user.is_active or user.locked_at is not None:
        audit.security(db, user, "auth.login",
                       "вход по ключу доступа в отключённую или заблокированную запись",
                       request=request, result=False, user_email=None if user else "passkey")
        raise HTTPException(status_code=status.HTTP_423_LOCKED,
                            detail="Учётная запись заблокирована — обратитесь к администратору")
    try:
        key.sign_count = passkeys.verify_authentication(
            payload.credential, ch.challenge, key.public_key, key.sign_count)
    except Exception as exc:  # noqa: BLE001
        audit.security(db, user, "auth.login",
                       f"ключ доступа «{key.name}» не подтверждён: {exc}"[:300],
                       request=request, result=False)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Ключ доступа не подтверждён") from exc
    key.last_used_at = datetime.utcnow()
    db.commit()
    ip, user_agent = audit.client_meta(request)
    token, sess = open_session(db, user, ip, user_agent)
    audit.security(db, user, "auth.login",
                   f"вход по ключу доступа «{key.name}» (сессия {sess.id[:8]})", request=request)
    return Token(access_token=token)
