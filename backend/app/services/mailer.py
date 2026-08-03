"""Отправка писем (коды второго фактора, п. 3.3 раздела 14 ТС).

Если SMTP не сконфигурирован, письмо не отправляется, а код пишется в журнал
сервера — это режим разработки/демонстрации. В промышленной среде задайте
SMTP_HOST и остальные параметры в .env, иначе второй фактор не дойдёт до
пользователя.
"""
import logging
import smtplib
from email.message import EmailMessage

from ..config import settings

log = logging.getLogger("mailer")


def configured() -> bool:
    return bool(settings.SMTP_HOST.strip())


def send(to: str, subject: str, body: str) -> bool:
    """Возвращает True, если письмо реально ушло по SMTP."""
    if not configured():
        log.warning("SMTP не настроен — письмо для %s не отправлено. Текст: %s", to, body)
        return False
    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as s:
            if settings.SMTP_TLS:
                s.starttls()
            if settings.SMTP_USER:
                s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            s.send_message(msg)
        return True
    except Exception as exc:  # noqa: BLE001
        log.error("Не удалось отправить письмо на %s: %s", to, exc)
        return False


def send_2fa_code(to: str, code: str, ip: str = "") -> bool:
    body = (
        f"Проверочный код для входа в электронный архив: {code}\n\n"
        f"Код действует {settings.TWOFA_CODE_TTL_MINUTES} мин."
        + (f"\nПопытка входа с адреса {ip}." if ip else "")
        + "\n\nЕсли вы не входили в систему, сообщите администратору."
    )
    return send(to, "Код подтверждения входа — e-archive", body)
