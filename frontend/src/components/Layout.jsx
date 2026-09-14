import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import { MODULES, moduleAllowed, useEdition } from "../edition.jsx";
import Icon from "./Icon.jsx";

const ROLE_LABEL = {
  admin: "Администратор",
  archivist: "Архивариус",
  viewer: "Читатель",
  auditor: "Аудитор ИБ",
};

export default function Layout() {
  const { user, logout } = useAuth();
  const edition = useEdition();

  const userCard = (
    <>
      <div className="avatar">{(user?.full_name || user?.email || "?")[0]}</div>
      <div className="user-meta">
        <div className="user-name">{user?.full_name || user?.email}</div>
        <div className="user-role">{ROLE_LABEL[user?.role] || user?.role}</div>
      </div>
    </>
  );

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">{edition.mark}</span>
          <div>
            <div className="brand-name">{edition.product}</div>
            <div className="brand-sub">{edition.organization || edition.subtitle}</div>
          </div>
        </div>
        <nav>
          {edition.sections.map((section, i) => {
            const items = section.items.filter((key) => moduleAllowed(key, user?.role));
            if (items.length === 0) return null;
            return (
              <div key={section.title || `section-${i}`} className="nav-section">
                {section.title && <div className="nav-section-title">{section.title}</div>}
                {items.map((key) => (
                  <NavLink key={key} to={MODULES[key].to} end={MODULES[key].end}>
                    <Icon name={MODULES[key].icon} /> {edition.label(key)}
                  </NavLink>
                ))}
              </div>
            );
          })}
        </nav>
        <div className="sidebar-foot">
          {edition.has("account") ? (
            <NavLink to="/account" className="user-chip user-chip-link">
              {userCard}
            </NavLink>
          ) : (
            <div className="user-chip">{userCard}</div>
          )}
          <button className="btn ghost small" onClick={logout}>Выйти</button>
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
