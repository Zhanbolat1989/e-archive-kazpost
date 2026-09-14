import { useEffect, useState, useCallback } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";

const fmtTs = (t) => (t ? new Date(t).toLocaleString("ru-RU") : "—");

const TYPE_CLS = {
  LOGIN: "b-green", LOGOUT: "b-gray", SECURITY: "b-amber",
  CREATE: "b-green", UPDATE: "b-gray", DELETE: "b-red", READ: "b-gray",
};

const ROLES = [
  ["admin", "Администратор"],
  ["archivist", "Архивариус"],
  ["viewer", "Читатель"],
  ["auditor", "Аудитор ИБ"],
];

export default function Security() {
  const { user } = useAuth();
  // Аудитор ИБ (ТС-176 разд. 14 п. 5.1) видит журнал, сессии и учётные записи,
  // но ничего не меняет: управляет доступом только администратор.
  const isAdmin = user?.role === "admin";
  const [tab, setTab] = useState("audit");
  const [trail, setTrail] = useState([]);
  const [stats, setStats] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [users, setUsers] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [filters, setFilters] = useState({ user_email: "", action_type: "", result: "" });
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    email: "", password: "", full_name: "", role: "archivist",
    position: "", department_id: "", can_sign: false,
  });

  const loadAudit = useCallback(() => {
    const params = { limit: 200 };
    if (filters.user_email) params.user_email = filters.user_email;
    if (filters.action_type) params.action_type = filters.action_type;
    if (filters.result !== "") params.result = filters.result;
    api.auditTrail(params).then(setTrail).catch((e) => setError(e.message));
    api.auditStats().then(setStats).catch(() => {});
  }, [filters]);

  const loadRest = useCallback(() => {
    api.allSessions().then(setSessions).catch((e) => setError(e.message));
    api.listUsers().then(setUsers).catch(() => {});
    api.listDepartments().then(setDepartments).catch(() => {});
  }, []);

  useEffect(() => { loadAudit(); }, [loadAudit]);
  useEffect(() => { loadRest(); }, [loadRest]);

  async function act(fn, okMessage) {
    setError(""); setInfo("");
    try {
      const res = await fn();
      setInfo(okMessage(res));
      loadAudit();
      loadRest();
    } catch (e) { setError(e.message); }
  }

  async function createUser(e) {
    e.preventDefault();
    setError("");
    try {
      await api.createUser({ ...form, department_id: form.department_id || null });
      setForm({ email: "", password: "", full_name: "", role: "archivist",
                position: "", department_id: "", can_sign: false });
      setCreating(false);
      loadRest();
    } catch (e2) { setError(e2.message); }
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Безопасность</h1>
          <p className="muted">
            Аудиторский след, сессии и учётные записи (раздел 14 ТС)
            {!isAdmin && " · режим аудитора: только просмотр"}
          </p>
        </div>
        {tab === "audit" && (
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn" onClick={() =>
              api.downloadBlob("/audit/export", "audit_trail.ndjson")
                .catch((e) => setError(e.message))}>
              ⬇️ Выгрузить для SIEM
            </button>
            {isAdmin && (
              <button className="btn" title="Перенести записи старше срока оперативного доступа"
                onClick={() => act(() => api.archiveAudit(),
                  (r) => `Перенесено в архив записей: ${r.archived}`)}>
                📦 В архив
              </button>
            )}
          </div>
        )}
      </header>

      {error && <div className="alert error">{error}</div>}
      {info && <div className="alert success">{info}</div>}

      <div className="suggestions" style={{ marginBottom: 16 }}>
        {[["audit", "Аудиторский след"], ["sessions", "Активные сессии"],
          ["users", "Пользователи"]].map(([k, label]) => (
          <button key={k} className={`chip ${tab === k ? "active" : ""}`}
                  onClick={() => setTab(k)}>{label}</button>
        ))}
      </div>

      {tab === "audit" && (
        <>
          {stats && (
            <div className="kpi-row" style={{ marginBottom: 16 }}>
              <div className="card dash-card">
                <div className="kpi-val">{stats.total}</div>
                <div className="kpi-lbl">всего записей</div>
              </div>
              <div className="card dash-card">
                <div className="kpi-val">{stats.operational}</div>
                <div className="kpi-lbl">оперативный доступ ({stats.operational_days} дн.)</div>
              </div>
              <div className="card dash-card">
                <div className="kpi-val">{stats.archived}</div>
                <div className="kpi-lbl">в архиве</div>
              </div>
              <div className="card dash-card">
                <div className="kpi-val" style={{ color: stats.failures ? "#dc2626" : undefined }}>
                  {stats.failures}
                </div>
                <div className="kpi-lbl">неуспешных событий</div>
              </div>
            </div>
          )}

          <div className="card form" style={{ marginBottom: 16 }}>
            <div className="row3">
              <div>
                <label>Пользователь</label>
                <input value={filters.user_email} placeholder="email или его часть"
                  onChange={(e) => setFilters({ ...filters, user_email: e.target.value })} />
              </div>
              <div>
                <label>Тип действия</label>
                <select value={filters.action_type}
                  onChange={(e) => setFilters({ ...filters, action_type: e.target.value })}>
                  <option value="">— все —</option>
                  {["LOGIN", "LOGOUT", "SECURITY", "CREATE", "READ", "UPDATE", "DELETE"]
                    .map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div>
                <label>Результат</label>
                <select value={filters.result}
                  onChange={(e) => setFilters({ ...filters, result: e.target.value })}>
                  <option value="">— все —</option>
                  <option value="true">успешно</option>
                  <option value="false">неуспешно</option>
                </select>
              </div>
            </div>
          </div>

          <table className="grid">
            <thead>
              <tr>
                <th>Дата и время</th><th>Пользователь</th><th>Действие</th>
                <th>Тип</th><th>Объект</th><th>IP</th><th>Результат</th>
              </tr>
            </thead>
            <tbody>
              {trail.map((r) => (
                <tr key={r.id}>
                  <td className="muted" style={{ whiteSpace: "nowrap" }}>{fmtTs(r.ts)}</td>
                  <td>{r.user_email}</td>
                  <td>
                    <b>{r.action}</b>
                    {r.detail && <div className="doc-file muted">{r.detail.slice(0, 70)}</div>}
                  </td>
                  <td><span className={`badge ${TYPE_CLS[r.action_type] || "b-gray"}`}>
                    {r.action_type}</span></td>
                  <td className="muted">{r.object_type || "—"}</td>
                  <td className="muted">{r.ip_address || "—"}</td>
                  <td>
                    {r.result
                      ? <span className="badge b-green">успешно</span>
                      : <span className="badge b-red">отказ</span>}
                    {r.archived && <span className="badge b-gray" style={{ marginLeft: 6 }}>архив</span>}
                  </td>
                </tr>
              ))}
              {trail.length === 0 && (
                <tr><td colSpan={7} className="muted" style={{ textAlign: "center", padding: 30 }}>
                  Записей не найдено.
                </td></tr>
              )}
            </tbody>
          </table>
        </>
      )}

      {tab === "sessions" && (
        <table className="grid">
          <thead>
            <tr>
              <th>Пользователь</th><th>IP</th><th>Устройство / браузер</th>
              <th>Вход</th><th>Активность</th>{isAdmin && <th></th>}
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => (
              <tr key={s.id}>
                <td><b>{s.user_email}</b>{s.current &&
                  <span className="badge b-green" style={{ marginLeft: 6 }}>текущая</span>}</td>
                <td className="muted">{s.ip_address || "—"}</td>
                <td className="muted small">{s.user_agent?.slice(0, 60) || "—"}</td>
                <td className="muted">{fmtTs(s.created_at)}</td>
                <td className="muted">{fmtTs(s.last_seen_at)}</td>
                {isAdmin && (
                  <td>
                    <button className="btn small" disabled={s.current}
                      onClick={() => act(() => api.revokeSession(s.id), () => "Сессия завершена")}>
                      Завершить
                    </button>
                  </td>
                )}
              </tr>
            ))}
            {sessions.length === 0 && (
              <tr><td colSpan={isAdmin ? 6 : 5} className="muted" style={{ textAlign: "center", padding: 30 }}>
                Активных сессий нет.
              </td></tr>
            )}
          </tbody>
        </table>
      )}

      {tab === "users" && (
        <>
          {isAdmin && (
            <div style={{ marginBottom: 14 }}>
              <button className="btn primary" onClick={() => setCreating(true)}>
                + Пользователь
              </button>
            </div>
          )}

          {isAdmin && creating && (
            <form className="card form" onSubmit={createUser} style={{ marginBottom: 18 }}>
              <div className="row3">
                <div>
                  <label>Email</label>
                  <input type="email" value={form.email} required
                    onChange={(e) => setForm({ ...form, email: e.target.value })} />
                </div>
                <div>
                  <label>Пароль</label>
                  <input type="password" value={form.password} required minLength={8}
                    onChange={(e) => setForm({ ...form, password: e.target.value })} />
                </div>
                <div>
                  <label>Роль</label>
                  <select value={form.role}
                    onChange={(e) => setForm({ ...form, role: e.target.value })}>
                    {ROLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </div>
              </div>
              <div className="row3">
                <div>
                  <label>ФИО</label>
                  <input value={form.full_name}
                    onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
                </div>
                <div>
                  <label>Должность</label>
                  <input value={form.position}
                    onChange={(e) => setForm({ ...form, position: e.target.value })} />
                </div>
                <div>
                  <label>Подразделение</label>
                  <select value={form.department_id}
                    onChange={(e) => setForm({ ...form, department_id: e.target.value })}>
                    <option value="">— не указано —</option>
                    {departments.map((d) => (
                      <option key={d.id} value={d.id}>{d.index} {d.name}</option>
                    ))}
                  </select>
                </div>
              </div>
              <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10 }}>
                <input type="checkbox" checked={form.can_sign} style={{ width: "auto" }}
                  onChange={(e) => setForm({ ...form, can_sign: e.target.checked })} />
                Право подписи документов
              </label>
              <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
                <button className="btn primary">Создать</button>
                <button type="button" className="btn" onClick={() => setCreating(false)}>Отмена</button>
              </div>
            </form>
          )}

          <table className="grid">
            <thead>
              <tr>
                <th>Пользователь</th><th>Роль</th><th>Подразделение</th>
                <th>Подпись</th><th>Состояние</th>{isAdmin && <th></th>}
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>
                    <b>{u.full_name || u.email}</b>
                    <div className="doc-file muted">{u.email}{u.position ? ` · ${u.position}` : ""}</div>
                  </td>
                  <td>
                    <select value={u.role} disabled={!isAdmin || u.id === user?.id}
                      onChange={(e) => act(() => api.updateUser(u.id, { role: e.target.value }),
                        () => `Роль ${u.email} изменена`)}>
                      {ROLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                    </select>
                  </td>
                  <td className="muted">{u.department_name || "—"}</td>
                  <td>
                    <input type="checkbox" checked={u.can_sign} style={{ width: "auto" }}
                      disabled={!isAdmin}
                      onChange={(e) => act(() => api.updateUser(u.id, { can_sign: e.target.checked }),
                        () => "Право подписи обновлено")} />
                  </td>
                  <td>
                    {u.locked
                      ? <span className="badge b-red">заблокирован</span>
                      : u.is_active
                        ? <span className="badge b-green">активен</span>
                        : <span className="badge b-gray">отключён</span>}
                  </td>
                  {isAdmin && (
                    <td style={{ whiteSpace: "nowrap" }}>
                      {u.locked && (
                        <button className="btn small"
                          onClick={() => act(() => api.unlockUser(u.id), () => "Запись разблокирована")}>
                          Разблокировать
                        </button>
                      )}
                      {u.id !== user?.id && (
                        <button className="btn small" style={{ marginLeft: 6 }}
                          onClick={() => act(() => api.updateUser(u.id, { is_active: !u.is_active }),
                            () => u.is_active ? "Учётная запись отключена" : "Учётная запись включена")}>
                          {u.is_active ? "Отключить" : "Включить"}
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
