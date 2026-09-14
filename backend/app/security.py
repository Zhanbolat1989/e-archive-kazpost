import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User, Role, UserSession

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Минимальный интервал обновления last_seen_at сессии (см. get_current_user).
SESSION_TOUCH_INTERVAL = timedelta(minutes=1)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str, jti: str) -> tuple[str, datetime]:
    """Токен привязан к сессии через jti — это позволяет отзывать доступ
    (п. 4.9 ТС: управление текущими сессиями) без смены общего секрета."""
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "exp": expire, "jti": jti}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM), expire


def open_session(db: Session, user: User, ip: str, user_agent: str) -> tuple[str, UserSession]:
    """Создаёт сессию и выдаёт для неё токен."""
    jti = uuid.uuid4().hex
    token, expire = create_access_token(user.id, jti)
    sess = UserSession(
        user_id=user.id, jti=jti, ip_address=ip[:64], user_agent=user_agent[:500],
        expires_at=expire,
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return token, sess


def active_sessions(db: Session, user_id: str) -> list[UserSession]:
    now = datetime.utcnow()
    return (
        db.query(UserSession)
        .filter(UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now)
        .order_by(UserSession.created_at.desc())
        .all()
    )


def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не удалось проверить учётные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: Optional[str] = payload.get("sub")
        jti: Optional[str] = payload.get("jti")
        if user_id is None or not jti:
            raise cred_exc
    except JWTError:
        raise cred_exc

    # Сессия должна существовать и быть активной: отозванный администратором
    # доступ обязан прекращаться немедленно, а не по истечении срока токена.
    sess = db.query(UserSession).filter(UserSession.jti == jti).first()
    if sess is None or sess.revoked_at is not None or sess.expires_at <= datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Сессия завершена — войдите заново",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.get(User, user_id)
    if user is None:
        raise cred_exc
    if not user.is_active or user.locked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Учётная запись заблокирована — обратитесь к администратору",
        )

    # Отметка активности сессии; ошибка записи не должна ломать сам запрос.
    # Пишем не чаще раза в минуту: для списка сессий такой точности достаточно,
    # а иначе каждый запрос на чтение превращался бы в отдельную транзакцию
    # записи и обесценивал кэш сессии SQLAlchemy (expire_on_commit).
    now = datetime.utcnow()
    if (now - sess.last_seen_at) >= SESSION_TOUCH_INTERVAL:
        try:
            sess.last_seen_at = now
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()

    request.state.session_jti = jti
    return user


# ---- Ключи доступа внешних информационных систем (ТЗ АГП п. 7, 9) ----
API_KEY_HEADER = "X-API-Key"
API_KEY_PREFIX_LEN = 8


def hash_api_key(key: str) -> str:
    """SHA-256, а не bcrypt: ключ — случайные 32 байта, подбирать его перебором
    бессмысленно, а проверка выполняется на каждом запросе внешней системы и
    должна быть быстрой."""
    import hashlib

    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """(ключ, префикс, хэш). Ключ показывается владельцу один раз."""
    import secrets

    key = "ea_" + secrets.token_urlsafe(32)
    return key, key[:API_KEY_PREFIX_LEN], hash_api_key(key)


def _api_key_user(db: Session, raw: str) -> Optional[User]:
    """Пользователь, от имени которого действует внешняя система.

    Объект User создаётся в памяти и не сохраняется: у ключа нет учётной записи,
    но аудиту нужен идентификатор действующего лица, а проверке доступа — роль.
    """
    from .models import ApiKey

    key = (db.query(ApiKey)
           .filter(ApiKey.prefix == raw[:API_KEY_PREFIX_LEN],
                   ApiKey.revoked_at.is_(None))
           .first())
    if key is None or not secrets_compare(key.key_hash, hash_api_key(raw)):
        return None
    try:
        key.last_used_at = datetime.utcnow()
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    return User(id=key.id, email=f"api:{key.name}", full_name=key.name,
                role=key.role, is_active=True, hashed_password="")


def secrets_compare(a: str, b: str) -> bool:
    import secrets as _s

    return _s.compare_digest(a or "", b or "")


def get_api_or_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Доступ по ключу внешней системы либо по обычному токену пользователя.

    Ключ проверяется первым: у внешней интеграции нет сессии, и требовать от
    неё вход по паролю нельзя. Если ключа нет — работает обычная проверка
    токена со всеми её правилами (активная сессия, блокировка учётной записи).
    """
    raw = request.headers.get(API_KEY_HEADER)
    if raw:
        user = _api_key_user(db, raw)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Ключ доступа недействителен")
        return user
    token = request.headers.get("authorization", "")
    if not token.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Не удалось проверить учётные данные",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return get_current_user(request, token.split(" ", 1)[1], db)


def require_roles(*roles: Role):
    def checker(user: User = Depends(get_current_user)) -> User:
        if roles and user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав для этого действия",
            )
        return user

    return checker
