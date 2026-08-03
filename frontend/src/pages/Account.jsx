import { useEffect, useState, useCallback } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";

const ROLE_LABEL = {
  admin: "Администратор", archivist: "Архивариус", viewer: "Читатель",
};
const fmtTs = (t) => (t ? new Date(t).toLocaleString("ru-RU") : "—");

export default function Account() {
  const { user, refresh } = useAuth();
  const [profile, setProfile] = useState({ full_name: "", position: "" });
  const [pwd, setPwd] = useState({ current_password: "", new_password: "", repeat: "" });
  const [sessions, setSessions] = useState([]);
  const [approvals, setApprovals] = useState([]);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  const load = useCallback(() => {
    api.mySessions().then(setSessions).catch((e) => setError(e.message));
    api.myApprovals().then(setApprovals).catch(() => {});
  }, []);

  useEffect(() => {
    if (user) setProfile({ full_name: user.full_name || "", position: user.position || "" });
  }, [user]);
  useEffect(() => { load(); }, [load]);

  async function saveProfile(e) {
    e.preventDefault();
    setError(""); setInfo("");
    try {
      await api.updateProfile(profile);
      await refresh();
      setInfo("Профиль сохранён");
    } catch (e2) { setError(e2.message); }
  }

  async function savePassword(e) {
    e.preventDefault();
    setError(""); setInfo("");
    if (pwd.new_password !== pwd.repeat) {
      setError("Новый пароль и подтверждение не совпадают");
      return;
    }
    try {
      await api.changePassword(pwd.current_password, pwd.new_password);
      setPwd({ current_password: "", new_password: "", repeat: "" });
      setInfo("Пароль изменён. Остальные сессии завершены.");
      load();
    } catch (e2) { setError(e2.message); }
  }

  async function decide(id, approve) {
    setError(""); setInfo("");
    try {
      await api.decideApproval(id, approve, "");
      setInfo(approve ? "Согласовано" : "Отклонено");
      load();
    } catch (e2) { setError(e2.message); }
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Личный кабинет</h1>
          <p className="muted">
            {user?.email} · {ROLE_LABEL[user?.role] || user?.role}
            {user?.department_name ? ` · ${user.department_name}` : ""}
          </p>
        </div>
      </header>

      {error && <div className="alert error">{error}</div>}
      {info && <div className="alert success">{info}</div>}

      {approvals.length > 0 && (
        <div className="card dash-card wide" style={{ marginBottom: 18 }}>
          <h3 style={{ marginTop: 0 }}>📝 Ожидают вашего согласования ({approvals.length})</h3>
          {approvals.map((a) => (
            <div className="ret-row" key={a.id}>
              <span>
                <b>{a.title}</b>
                <span className="muted small"> · {a.object_type === "document" ? "документ" : "дело"}
                  {" · от "}{a.created_by}</span>
              </span>
              <span style={{ display: "flex", gap: 8 }}>
                <button className="btn small" onClick={() => decide(a.id, true)}>Согласовать</button>
                <button className="btn small danger" onClick={() => decide(a.id, false)}>Отклонить</button>
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="row2" style={{ alignItems: "start", gap: 18 }}>
        <form className="card form" onSubmit={saveProfile}>
          <h3 style={{ marginTop: 0 }}>Профиль</h3>
          <label>ФИО</label>
          <input value={profile.full_name}
            onChange={(e) => setProfile({ ...profile, full_name: e.target.value })} />
          <label>Должность</label>
          <input value={profile.position}
            onChange={(e) => setProfile({ ...profile, position: e.target.value })} />
          <label>Email</label>
          <input value={user?.email || ""} disabled />
          <div style={{ marginTop: 14 }}>
            <button className="btn primary">Сохранить профиль</button>
          </div>
        </form>

        <form className="card form" onSubmit={savePassword}>
          <h3 style={{ marginTop: 0 }}>Смена пароля</h3>
          <label>Текущий пароль</label>
          <input type="password" required value={pwd.current_password}
            onChange={(e) => setPwd({ ...pwd, current_password: e.target.value })} />
          <label>Новый пароль</label>
          <input type="password" required minLength={8} value={pwd.new_password}
            onChange={(e) => setPwd({ ...pwd, new_password: e.target.value })} />
          <label>Повторите новый пароль</label>
          <input type="password" required minLength={8} value={pwd.repeat}
            onChange={(e) => setPwd({ ...pwd, repeat: e.target.value })} />
          <p className="muted small" style={{ marginBottom: 0 }}>
            После смены пароля все прочие сессии будут завершены.
          </p>
          <div style={{ marginTop: 14 }}>
            <button className="btn primary">Изменить пароль</button>
          </div>
        </form>
      </div>

      <h2 style={{ marginTop: 24 }}>Мои сессии</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        Устройства, с которых выполнен вход в систему
      </p>
      <table className="grid">
        <thead>
          <tr><th>IP</th><th>Браузер / устройство</th><th>Вход</th><th>Активность</th><th></th></tr>
        </thead>
        <tbody>
          {sessions.map((s) => (
            <tr key={s.id}>
              <td>{s.ip_address || "—"}
                {s.current && <span className="badge b-green" style={{ marginLeft: 6 }}>текущая</span>}</td>
              <td className="muted small">{s.user_agent?.slice(0, 64) || "—"}</td>
              <td className="muted">{fmtTs(s.created_at)}</td>
              <td className="muted">{fmtTs(s.last_seen_at)}</td>
              <td>
                <button className="btn small" disabled={s.current}
                  onClick={async () => {
                    try { await api.revokeMySession(s.id); load(); }
                    catch (e) { setError(e.message); }
                  }}>
                  Завершить
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
