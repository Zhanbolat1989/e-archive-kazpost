import { createContext, useContext, useEffect, useState } from "react";
import { api } from "./api.js";

// Разделы интерфейса. Какие из них показывать и как сгруппировать, решает
// редакция на сервере (GET /api/meta/edition) — здесь только как отрисовать.
// roles — роли, которым раздел доступен (по умолчанию всем); hiddenFor — роли,
// которым он не показывается. Аудитору ИБ (ТС-176 разд. 14 п. 5.1) закрыты
// разделы с содержимым документов: сервер ему их всё равно не отдаст.
const NO_AUDITOR = ["auditor"];

export const MODULES = {
  dashboard: { to: "/", label: "Дашборд", icon: "dashboard", end: true },
  search: { to: "/search", label: "ИИ-ассистент", icon: "bot", hiddenFor: NO_AUDITOR },
  documents: { to: "/documents", label: "Документы", icon: "document", hiddenFor: NO_AUDITOR },
  cases: { to: "/cases", label: "Дела", icon: "folder" },
  inventories: { to: "/inventories", label: "Описи дел", icon: "list" },
  nto: { to: "/nto", label: "НТО и передача", icon: "list" },
  nomenclature: { to: "/nomenclature", label: "Номенклатура", icon: "list" },
  issues: { to: "/issues", label: "Выдача", icon: "issue" },
  lifecycle: { to: "/lifecycle", label: "Уничтожение", icon: "trash" },
  scanning: { to: "/scanning", label: "Сканирование", icon: "upload", hiddenFor: NO_AUDITOR },
  upload: { to: "/upload", label: "Приём", icon: "upload", hiddenFor: NO_AUDITOR },
  quality: { to: "/quality", label: "Качество оцифровки", icon: "document", hiddenFor: NO_AUDITOR },
  imports: { to: "/imports", label: "Импорт", icon: "upload", roles: ["admin"] },
  archive_requests: { to: "/archive-requests", label: "Архивные запросы", icon: "issue" },
  reports: { to: "/reports", label: "Отчеты", icon: "dashboard" },
  enterprise: { to: "/enterprise", label: "Предприятие", icon: "folder" },
  security: { to: "/security", label: "Безопасность", icon: "list", roles: ["admin", "auditor"] },
  admin: { to: "/admin", label: "Администрирование", icon: "list", roles: ["admin"] },
  account: { to: "/account", label: "Личный кабинет", icon: "document" },
  support: { to: "/support", label: "Обращения и SLA", icon: "issue" },
  help: { to: "/help", label: "Помощь", icon: "document" },
};

export function moduleAllowed(key, role) {
  const m = MODULES[key];
  if (!m) return false;
  if (m.roles && !m.roles.includes(role)) return false;
  return !(m.hiddenFor && m.hiddenFor.includes(role));
}

// Профиль на случай недоступного сервера: интерфейс не должен пропадать
// целиком из-за того, что не загрузилось оформление.
const FALLBACK = {
  key: "base",
  product: "e-archive",
  organization: "",
  subtitle: "Электронный архив",
  tagline: "Электронный архив",
  mark: "e",
  theme: null,
  demo: false,
  labels: {},
  sections: [{ title: null, items: Object.keys(MODULES).filter((m) => m !== "account") }],
  modules: Object.keys(MODULES),
};

const THEME_VARS = {
  brand: "--brand",
  brand_d: "--brand-d",
  brand_ink: "--brand-ink",
  brand_text: "--brand-text",
  accent: "--accent",
};

function applyTheme(theme) {
  if (!theme) return;
  const root = document.documentElement;
  Object.entries(THEME_VARS).forEach(([key, cssVar]) => {
    if (theme[key]) root.style.setProperty(cssVar, theme[key]);
  });
}

const EditionContext = createContext(FALLBACK);

export function EditionProvider({ children }) {
  const [edition, setEdition] = useState(null);

  useEffect(() => {
    api.edition()
      .then((e) => {
        applyTheme(e.theme);
        document.title = e.organization ? `${e.product} · ${e.organization}` : e.product;
        setEdition(e);
      })
      .catch(() => setEdition(FALLBACK));
  }, []);

  // Пока профиль не пришёл, не рисуем интерфейс: иначе меню и название
  // мелькнули бы в оформлении другой редакции.
  if (!edition) return <div className="center muted">Загрузка…</div>;
  return <EditionContext.Provider value={edition}>{children}</EditionContext.Provider>;
}

export function useEdition() {
  const edition = useContext(EditionContext);
  return {
    ...edition,
    has: (key) => edition.modules.includes(key),
    label: (key) => edition.labels?.[key] || MODULES[key]?.label || key,
  };
}
