"""Аутентификация и учётные записи.

Реализует требования раздела 14 ТС-176: блокировка после трёх неверных вводов
пароля (п. 4.4), второй фактор по email (п. 3), управление текущими сессиями
(п. 4.9) и аудит всех событий входа/авторизации.
"""
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import User, Role, UserSession, LoginChallenge, Department
from ..schemas import (
    LoginResponse, TwoFactorVerify, Token, UserCreate, UserUpdate, UserOut,
    ProfileUpdate, PasswordChange, SessionOut,
)
from ..security import (
    hash_password, verify_password, get_current_user, require_roles,
    open_session, active_sessions,
)
from ..services import audit, mailer

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _out(db: Session, u: User) -> UserOut:
    dep = db.get(Department, u.department_id) if u.department_id else None
    return UserOut(
        id=u.id, email=u.email, full_name=u.full_name, role=u.role,
        position=u.position, department_id=u.department_id,
        department_name=(dep.name if dep else None), can_sign=u.can_sign,
        is_active=u.is_active, locked=u.locked_at is not None,
    )


def _meta(request: Request) -> tuple[str, str]:
    return audit.client_meta(request)


def _needs_2fa(db: Session, user: User, user_agent: str) -> bool:
    """Второй фактор нужен при входе с незнакомого браузера либо когда у
    пользователя уже есть активная сессия (п. 3.3 ТС)."""
    if not settings.TWOFA_ENABLED:
        return False
    if active_sessions(db, user.id):
        return True
    known = (
        db.query(UserSession)
        .filter(UserSession.user_id == user.id, UserSession.user_agent == user_agent[:500])
        .first()
    )
    return known is None


def _issue_challenge(db: Session, user: User, ip: str, ua: str) -> LoginResponse:
    now = datetime.utcnow()
    # Предыдущие невыполненные коды гасим, а число уже сделанных попыток
    # переносим на новый код. Иначе повторный запрос кода обнулял бы счётчик и
    # TWOFA_MAX_ATTEMPTS переставал ограничивать подбор шестизначного кода
    # (достаточно было заново вызвать /login после каждых трёх промахов).
    live = (
        db.query(LoginChallenge)
        .filter(LoginChallenge.user_id == user.id,
                LoginChallenge.used_at.is_(None),
                LoginChallenge.expires_at > now)
        .order_by(LoginChallenge.created_at.desc())
        .all()
    )
    carried = max((c.attempts or 0) for c in live) if live else 0

    if carried >= settings.TWOFA_MAX_ATTEMPTS:
        # Лимит попыток исчерпан — новый код не выдаём и письмо не шлём
        # (иначе это ещё и канал рассылки писем на чужой адрес).
        return LoginResponse(
            twofa_required=True, challenge_id=live[0].id, delivery="throttled",
        )

    for old in live:
        old.used_at = now

    code = f"{secrets.randbelow(1_000_000):06d}"
    ch = LoginChallenge(
        user_id=user.id,
        code_hash=hash_password(code),
        expires_at=now + timedelta(minutes=settings.TWOFA_CODE_TTL_MINUTES),
        attempts=carried,
        ip_address=ip[:64], user_agent=ua[:500],
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)
    sent = mailer.send_2fa_code(user.email, code, ip)
    return LoginResponse(
        twofa_required=True, challenge_id=ch.id,
        delivery="email" if sent else "server_log",
    )


@router.post("/login", response_model=LoginResponse)
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(),
          db: Session = Depends(get_db)):
    ip, ua = _meta(request)
    user = db.query(User).filter(User.email == form.username).first()

    if not user:
        audit.security(db, None, "auth.login", f"неизвестный логин: {form.username}",
                       request=request, result=False, user_email=form.username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Неверный email или пароль")

    if not user.is_active:
        audit.security(db, user, "auth.login", "учётная запись отключена",
                       request=request, result=False)
        raise HTTPException(status_code=status.HTTP_423_LOCKED,
                            detail="Учётная запись отключена")

    if user.locked_at is not None:
        audit.security(db, user, "auth.login", "вход в заблокированную запись",
                       request=request, result=False)
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Учётная запись заблокирована после неверных попыток входа — "
                   "обратитесь к администратору",
        )

    if not verify_password(form.password, user.hashed_password):
        user.failed_attempts = (user.failed_attempts or 0) + 1
        locked = user.failed_attempts >= settings.LOGIN_MAX_ATTEMPTS
        if locked:
            user.locked_at = datetime.utcnow()
        db.commit()
        audit.security(
            db, user, "auth.login",
            f"неверный пароль (попытка {user.failed_attempts}"
            f"/{settings.LOGIN_MAX_ATTEMPTS})" + ("; запись заблокирована" if locked else ""),
            request=request, result=False,
        )
        if locked:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Учётная запись заблокирована после "
                       f"{settings.LOGIN_MAX_ATTEMPTS} неверных попыток входа",
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Неверный email или пароль")

    # Пароль верен — счётчик неудачных попыток сбрасывается.
    if user.failed_attempts:
        user.failed_attempts = 0
        db.commit()

    if _needs_2fa(db, user, ua):
        audit.security(db, user, "auth.2fa_required",
                       "запрошен код подтверждения входа", request=request)
        return _issue_challenge(db, user, ip, ua)

    token, sess = open_session(db, user, ip, ua)
    audit.security(db, user, "auth.login", f"вход выполнен (сессия {sess.id[:8]})",
                   request=request)
    return LoginResponse(access_token=token)


@router.post("/2fa", response_model=Token)
def verify_2fa(request: Request, payload: TwoFactorVerify,
               db: Session = Depends(get_db)):
    ip, ua = _meta(request)
    ch = db.get(LoginChallenge, payload.challenge_id)
    if ch is None or ch.used_at is not None or ch.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=400, detail="Код недействителен или истёк")

    user = db.get(User, ch.user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="Код недействителен")

    # Состояние записи проверяем заново: её могли отключить или заблокировать
    # между вводом пароля и вводом кода — сессию в этом случае открывать нельзя.
    if not user.is_active or user.locked_at is not None:
        audit.security(db, user, "auth.2fa", "запись отключена или заблокирована",
                       request=request, result=False)
        raise HTTPException(status_code=status.HTTP_423_LOCKED,
                            detail="Учётная запись заблокирована — обратитесь к администратору")

    if ch.attempts >= settings.TWOFA_MAX_ATTEMPTS:
        audit.security(db, user, "auth.2fa", "исчерпаны попытки ввода кода",
                       request=request, result=False)
        raise HTTPException(status_code=429, detail="Слишком много попыток ввода кода")

    if not verify_password(payload.code, ch.code_hash):
        ch.attempts += 1
        db.commit()
        audit.security(db, user, "auth.2fa", f"неверный код (попытка {ch.attempts})",
                       request=request, result=False)
        raise HTTPException(status_code=400, detail="Неверный код подтверждения")

    ch.used_at = datetime.utcnow()
    db.commit()
    token, sess = open_session(db, user, ip, ua)
    audit.security(db, user, "auth.login",
                   f"вход подтверждён вторым фактором (сессия {sess.id[:8]})",
                   request=request)
    return Token(access_token=token)


@router.post("/logout", status_code=204)
def logout(request: Request, user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    jti = getattr(request.state, "session_jti", None)
    if jti:
        sess = db.query(UserSession).filter(UserSession.jti == jti).first()
        if sess and sess.revoked_at is None:
            sess.revoked_at = datetime.utcnow()
            db.commit()
    audit.security(db, user, "auth.logout", "выход из системы", request=request)


# ---------------------------------------------------------------- Личный кабинет
@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _out(db, user)


@router.patch("/me", response_model=UserOut)
def update_me(request: Request, payload: ProfileUpdate,
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    audit.record(db, user, "profile.update", "user", user.id,
                 "обновлён профиль", request=request)
    return _out(db, user)


@router.post("/me/password", status_code=204)
def change_password(request: Request, payload: PasswordChange,
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, user.hashed_password):
        audit.security(db, user, "auth.password_change", "неверный текущий пароль",
                       request=request, result=False)
        raise HTTPException(status_code=400, detail="Текущий пароль указан неверно")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400,
                            detail="Новый пароль должен быть не короче 8 символов")
    user.hashed_password = hash_password(payload.new_password)
    # Смена пароля прекращает все прочие сессии: если пароль был скомпрометирован,
    # чужой доступ должен закончиться немедленно.
    jti = getattr(request.state, "session_jti", None)
    for s in active_sessions(db, user.id):
        if s.jti != jti:
            s.revoked_at = datetime.utcnow()
    db.commit()
    audit.security(db, user, "auth.password_change", "пароль изменён", request=request)


@router.get("/me/sessions", response_model=list[SessionOut])
def my_sessions(request: Request, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    jti = getattr(request.state, "session_jti", None)
    return [
        SessionOut(
            id=s.id, user_email=user.email, ip_address=s.ip_address,
            user_agent=s.user_agent, created_at=s.created_at,
            last_seen_at=s.last_seen_at, expires_at=s.expires_at,
            current=(s.jti == jti),
        )
        for s in active_sessions(db, user.id)
    ]


@router.delete("/me/sessions/{session_id}", status_code=204)
def revoke_my_session(request: Request, session_id: str,
                      user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    sess = db.get(UserSession, session_id)
    if sess is None or sess.user_id != user.id:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    sess.revoked_at = datetime.utcnow()
    db.commit()
    audit.security(db, user, "session.revoke", f"завершена своя сессия {session_id[:8]}",
                   request=request, object_id=session_id)


# ------------------------------------------------------------- Администрирование
@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db),
               # Аудитор ИБ видит учётные записи и их полномочия, но не меняет их.
               _: User = Depends(require_roles(Role.admin, Role.auditor))):
    return [_out(db, u) for u in db.query(User).order_by(User.email).all()]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(request: Request, payload: UserCreate, db: Session = Depends(get_db),
                admin: User = Depends(require_roles(Role.admin))):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=409, detail="Пользователь уже существует")
    # Требование к длине пароля одно и то же при создании и при смене — иначе
    # через API можно завести запись с паролем, который сам владелец потом
    # не сможет установить через /me/password.
    if len(payload.password) < 8:
        raise HTTPException(status_code=400,
                            detail="Пароль должен быть не короче 8 символов")
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        role=payload.role,
        position=payload.position,
        department_id=payload.department_id or None,
        can_sign=payload.can_sign,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit.security(db, admin, "user.create", f"создан пользователь {user.email} "
                   f"с ролью {user.role.value}", request=request, object_id=user.id,
                   object_type="user")
    return _out(db, user)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(request: Request, user_id: str, payload: UserUpdate,
                db: Session = Depends(get_db),
                admin: User = Depends(require_roles(Role.admin))):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    changes = payload.model_dump(exclude_unset=True)
    if "department_id" in changes and not changes["department_id"]:
        changes["department_id"] = None
    # Администратор не может отключить или разжаловать сам себя: разблокировка
    # и смена ролей доступны только администратору, поэтому последний из них,
    # отключив себя, сделал бы систему неуправляемой без правки базы.
    if user.id == admin.id:
        if changes.get("is_active") is False:
            raise HTTPException(status_code=400,
                                detail="Нельзя отключить собственную учётную запись")
        if "role" in changes and changes["role"] != user.role:
            raise HTTPException(status_code=400,
                                detail="Нельзя изменить роль собственной учётной записи")
    was_role, was_active = user.role, user.is_active
    for field, value in changes.items():
        setattr(user, field, value)
    db.commit()
    # Отключение и смена роли — события безопасности; отключённый пользователь
    # теряет все активные сессии сразу.
    if not user.is_active and was_active:
        for s in active_sessions(db, user.id):
            s.revoked_at = datetime.utcnow()
        db.commit()
    detail = ", ".join(f"{k}={v}" for k, v in changes.items())
    audit.security(db, admin, "user.update", f"{user.email}: {detail}"
                   + (f" (роль была {was_role.value})" if user.role != was_role else ""),
                   request=request, object_id=user.id, object_type="user")
    return _out(db, user)


@router.post("/users/{user_id}/unlock", response_model=UserOut)
def unlock_user(request: Request, user_id: str, db: Session = Depends(get_db),
                admin: User = Depends(require_roles(Role.admin))):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    user.locked_at = None
    user.failed_attempts = 0
    db.commit()
    audit.security(db, admin, "user.unlock", f"разблокирована запись {user.email}",
                   request=request, object_id=user.id, object_type="user")
    return _out(db, user)


@router.get("/sessions", response_model=list[SessionOut])
def all_sessions(request: Request, db: Session = Depends(get_db),
                 # Просмотр сессий — и аудитору ИБ; завершает их только администратор.
                 _: User = Depends(require_roles(Role.admin, Role.auditor))):
    """Все активные сессии системы (п. 4.9 ТС)."""
    jti = getattr(request.state, "session_jti", None)
    now = datetime.utcnow()
    rows = (
        db.query(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .filter(UserSession.revoked_at.is_(None), UserSession.expires_at > now)
        .order_by(UserSession.last_seen_at.desc())
        .all()
    )
    return [
        SessionOut(
            id=s.id, user_email=u.email, ip_address=s.ip_address,
            user_agent=s.user_agent, created_at=s.created_at,
            last_seen_at=s.last_seen_at, expires_at=s.expires_at,
            current=(s.jti == jti),
        )
        for s, u in rows
    ]


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(request: Request, session_id: str, db: Session = Depends(get_db),
                   admin: User = Depends(require_roles(Role.admin))):
    sess = db.get(UserSession, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    sess.revoked_at = datetime.utcnow()
    db.commit()
    owner = db.get(User, sess.user_id)
    audit.security(db, admin, "session.revoke",
                   f"администратор завершил сессию {owner.email if owner else ''}",
                   request=request, object_id=session_id)
