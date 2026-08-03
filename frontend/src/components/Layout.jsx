import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import Icon from "./Icon.jsx";

const ROLE_LABEL = {
  admin: "Администратор",
  archivist: "Архивариус",
  viewer: "Читатель",
};

export default function Layout() {
  const { user, logout } = useAuth();
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">e</span>
          <div>
            <div className="brand-name">e-archive</div>
            <div className="brand-sub">Электронный архив</div>
          </div>
        </div>
        <nav>
          <NavLink to="/" end><Icon name="dashboard" /> Дашборд</NavLink>
          <NavLink to="/documents"><Icon name="document" /> Документы</NavLink>
          <NavLink to="/cases"><Icon name="folder" /> Дела</NavLink>
          <NavLink to="/nomenclature"><Icon name="list" /> Номенклатура</NavLink>
          <NavLink to="/issues"><Icon name="issue" /> Выдача</NavLink>
          <NavLink to="/lifecycle"><Icon name="trash" /> Уничтожение</NavLink>
          <NavLink to="/search"><Icon name="bot" /> ИИ-ассистент</NavLink>
          <NavLink to="/upload"><Icon name="upload" /> Приём</NavLink>
          <NavLink to="/reports"><Icon name="dashboard" /> Отчеты</NavLink>
          <NavLink to="/enterprise"><Icon name="folder" /> Предприятие</NavLink>
          {user?.role === "admin" && (
            <NavLink to="/security"><Icon name="list" /> Безопасность</NavLink>
          )}
          <NavLink to="/help"><Icon name="document" /> Помощь</NavLink>
        </nav>
        <div className="sidebar-foot">
          <NavLink to="/account" className="user-chip user-chip-link">
            <div className="avatar">{(user?.full_name || user?.email || "?")[0]}</div>
            <div className="user-meta">
              <div className="user-name">{user?.full_name || user?.email}</div>
              <div className="user-role">{ROLE_LABEL[user?.role] || user?.role}</div>
            </div>
          </NavLink>
          <button className="btn ghost small" onClick={logout}>Выйти</button>
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
