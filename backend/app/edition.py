"""Редакции системы под заказчиков.

Одна кодовая база обслуживает нескольких заказчиков: исправления безопасности
и общие модули не должны расходиться между копиями. Редакция определяет только
то, что видит пользователь, — название, оформление, состав и группировку
разделов меню. Права доступа от редакции не зависят: скрытый раздел не
становится доступнее или недоступнее, чем по ролям.

Редакция выбирается переменной окружения EDITION; фронтенд получает профиль
через публичный GET /api/meta/edition (страница входа тоже оформляется
по редакции, а токена у неё ещё нет).
"""
from .config import settings

# Все разделы интерфейса. Фронтенд знает, как их отрисовать; редакция лишь
# решает, какие показывать и в каком порядке.
MODULES = (
    "dashboard", "search", "documents", "cases", "inventories", "nto", "nomenclature",
    "issues", "lifecycle", "scanning", "upload", "quality", "imports",
    "archive_requests", "reports", "enterprise", "security", "admin", "account",
    "support", "help",
)

_BASE = {
    "key": "base",
    "product": "e-archive",
    "organization": "",
    "subtitle": "Электронный архив",
    "tagline": "Электронный архив · AI-поиск · ЭЦП РК",
    "mark": "e",
    "theme": None,
    "spec": "",
    "sections": [
        {"title": None, "items": [
            "search", "dashboard", "documents", "cases", "nomenclature", "issues",
            "lifecycle", "scanning", "upload", "archive_requests", "inventories", "nto",
            "quality", "imports", "admin", "reports", "enterprise", "security",
            "support", "help",
        ]},
    ],
    "labels": {},
}

# АО «Казпочта»: разделы сгруппированы ровно по модулям ТС-176 (п. 4.2), чтобы
# при приёмке каждый модуль спецификации находился в меню под своим именем.
_KAZPOST = {
    "key": "kazpost",
    "product": "Электронный архив",
    "organization": "АО «Казпочта»",
    "subtitle": "Qazpost Digital · ИС «ЭА»",
    "tagline": "АО «Казпочта» · Qazpost Digital",
    "mark": "ЭА",
    "theme": {
        "brand": "#1f5aa8",
        "brand_d": "#184a8c",
        "brand_ink": "#ffffff",
        "brand_text": "#1f5aa8",
        "accent": "#f5b700",
    },
    "spec": "ТС-176 от 03.04.2026",
    "sections": [
        {"title": None, "items": ["dashboard", "search"]},
        {"title": "Управление документами", "items": [
            "documents", "cases", "inventories", "nto", "nomenclature", "issues", "lifecycle",
        ]},
        {"title": "Сканирование", "items": ["scanning", "upload", "quality", "imports"]},
        {"title": None, "items": ["reports", "enterprise"]},
        {"title": "Администрирование", "items": ["security", "admin"]},
        # «Личный кабинет»: заявки на дополнительные услуги и обращения с SLA
        # (разд. 13, разд. 14 п. 2.9, 2.10, 6.1) — рядом с кабинетом и помощью.
        {"title": None, "items": ["account", "support", "help"]},
    ],
    # Названия компонентов из ТС-176 п. 4.3–4.9 там, где они отличаются от
    # общих названий разделов.
    "labels": {
        "issues": "Запросы на выдачу дел",
        "lifecycle": "Уничтожение и инвентаризация",
        "nto": "НТО, ЭК и передача в госархив",
        "scanning": "Ввод сканов и учёт работ",
        "upload": "Приём документов",
        "quality": "Верификация распознавания",
        "imports": "Импорт пакетов",
        "reports": "Управление отчетами",
        "security": "Пользователи и сессии",
        "admin": "Настройки и журналы",
        "account": "Личный кабинет",
        "support": "Заявки и SLA",
    },
}

EDITIONS = {"base": _BASE, "kazpost": _KAZPOST}


def disabled_modules() -> set[str]:
    """Разделы, отключённые при развёртывании (EDITION_DISABLED_MODULES).

    Нужно, когда контур заказчика не тянет модуль по ресурсам: например,
    ИИ-ассистент без сервера языковой модели."""
    return {m.strip() for m in settings.EDITION_DISABLED_MODULES.split(",") if m.strip()}


def profile() -> dict:
    """Профиль текущей редакции с учётом отключённых разделов."""
    base = EDITIONS[settings.EDITION]
    off = disabled_modules()
    sections = []
    for section in base["sections"]:
        items = [m for m in section["items"] if m not in off]
        if items:
            sections.append({"title": section["title"], "items": items})
    enabled = [m for s in sections for m in s["items"]]
    return {
        **{k: v for k, v in base.items() if k != "sections"},
        "sections": sections,
        "modules": enabled,
        # Подсказка с демонстрационной учётной записью уместна только в локальной
        # работе базовой редакции; в контуре заказчика её быть не должно.
        "demo": settings.EDITION == "base" and settings.ENVIRONMENT == "dev",
    }
