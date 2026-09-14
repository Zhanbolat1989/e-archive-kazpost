import { useEffect, useState } from "react";
import { api } from "../api.js";
import Dictionaries from "../components/Dictionaries.jsx";

// Администрирование по ТЗ АГП п. 8–9 и ТС-176 п. 4.9: история изменений
// записей, справочники, доступ к документам по категориям, ключи внешних
// систем, журнал ИИ-агента и обращения в поддержку.
const TABS = [
  { key: "changes", label: "История изменений" },
  { key: "dictionaries", label: "Справочники" },
  { key: "access", label: "Доступ к документам" },
  { key: "keys", label: "Ключи интеграции" },
  { key: "agent", label: "Журнал ИИ-ассистента" },
  { key: "support", label: "Обращения" },
];

const ROLES = [
  { value: "archivist", label: "Архивариус" },
  { value: "viewer", label: "Читатель" },
];

export default function Admin() {
  const [tab, setTab] = useState("changes");
  const [error, setError] = useState("");

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Администрирование</h1>
          <p className="muted">Изменения записей, доступ, интеграции и журнал ассистента</p>
        </div>
      </header>

      <div className="tabs" style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        {TABS.map((t) => (
          <button key={t.key}
                  className={`btn small ${tab === t.key ? "primary" : ""}`}
                  onClick={() => { setTab(t.key); setError(""); }}>
            {t.label}
          </button>
        ))}
      </div>

      {error && <div className="alert error">{error}</div>}

      {tab === "changes" && <Changes onError={setError} />}
      {tab === "dictionaries" && <Dictionaries onError={setError} />}
      {tab === "access" && <Access onError={setError} />}
      {tab === "keys" && <Keys onError={setError} />}
      {tab === "agent" && <AgentJournal onError={setError} />}
      {tab === "support" && <Tickets onError={setError} />}
    </div>
  );
}

function Changes({ onError }) {
  const [rows, setRows] = useState([]);
  const [type, setType] = useState("");

  useEffect(() => {
    api.changeHistory({ object_type: type }).then(setRows).catch((e) => onError(e.message));
  }, [type, onError]);

  return (
    <>
      <div className="card" style={{ marginBottom: 14 }}>
        <label>Объект</label>
        <select value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">все</option>
          <option value="document">документы</option>
          <option value="nomenclature">номенклатура</option>
          <option value="archive_request">архивные запросы</option>
        </select>
      </div>
      <table className="grid">
        <thead>
          <tr><th>Дата</th><th>Пользователь</th><th>Объект</th><th>Поле</th>
            <th>Было</th><th>Стало</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td className="muted">{new Date(r.ts).toLocaleString("ru-RU")}</td>
              <td>{r.user_email}</td>
              <td className="muted">{r.object_type}</td>
              <td><b>{r.field}</b></td>
              <td className="muted">{r.old_value || "—"}</td>
              <td>{r.new_value || "—"}</td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={6} className="muted" style={{ textAlign: "center", padding: 30 }}>
              Изменений пока не зафиксировано.
            </td></tr>
          )}
        </tbody>
      </table>
    </>
  );
}

function Access({ onError }) {
  const [groups, setGroups] = useState([]);
  const [current, setCurrent] = useState({});
  const [role, setRole] = useState(ROLES[0].value);

  function reload() {
    api.docAccess().then((rows) => {
      const map = {};
      rows.forEach((r) => { map[r.role] = r.doc_groups; });
      setCurrent(map);
    }).catch((e) => onError(e.message));
  }

  useEffect(() => {
    api.docAccessGroups().then(setGroups).catch(() => {});
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selected = current[role] || [];

  async function toggle(group) {
    const next = selected.includes(group)
      ? selected.filter((g) => g !== group)
      : [...selected, group];
    onError("");
    try {
      await api.setDocAccess(role, next);
      reload();
    } catch (e) { onError(e.message); }
  }

  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>Категории документов, доступные роли</h3>
      <p className="muted">
        Роль без отмеченных категорий видит все документы. Как только отмечена
        хотя бы одна — в поиске, перечнях и ответах ассистента остаются только
        документы отмеченных категорий. Администратору доступны все категории.
      </p>
      <label>Роль</label>
      <select value={role} onChange={(e) => setRole(e.target.value)}>
        {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
      </select>
      <ul style={{ listStyle: "none", padding: 0, marginTop: 14, lineHeight: 2 }}>
        {groups.map((g) => (
          <li key={g}>
            <label style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
              <input type="checkbox" checked={selected.includes(g)}
                     onChange={() => toggle(g)} />
              {g}
            </label>
          </li>
        ))}
      </ul>
      {selected.length === 0 && (
        <p className="muted" style={{ marginBottom: 0 }}>
          Ограничений нет — роли доступны все категории.
        </p>
      )}
    </div>
  );
}

function Keys({ onError }) {
  const [rows, setRows] = useState([]);
  const [name, setName] = useState("");
  const [role, setRole] = useState("viewer");
  const [issued, setIssued] = useState(null);

  function load() {
    api.listApiKeys().then(setRows).catch((e) => onError(e.message));
  }
  useEffect(load, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function create(e) {
    e.preventDefault();
    onError("");
    try {
      const key = await api.createApiKey({ name, role });
      setIssued(key);
      setName("");
      load();
    } catch (e2) { onError(e2.message); }
  }

  return (
    <>
      <form className="card form" style={{ marginBottom: 16 }} onSubmit={create}>
        <h3 style={{ marginTop: 0 }}>Новый ключ доступа</h3>
        <p className="muted">
          Ключ передаётся внешней системой в заголовке X-API-Key и заменяет вход
          по паролю для интеграции (ТЗ АГП п. 7, 9).
        </p>
        <div className="row3">
          <div>
            <label>Назначение</label>
            <input value={name} required onChange={(e) => setName(e.target.value)}
                   placeholder="напр. 1С:Бухгалтерия" />
          </div>
          <div>
            <label>Права</label>
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </select>
          </div>
        </div>
        <button className="btn primary" style={{ marginTop: 12 }}>Создать ключ</button>
      </form>

      {issued && (
        <div className="alert" style={{ marginBottom: 16 }}>
          Ключ создан и показывается один раз — сохраните его сейчас:
          <div><code>{issued.key}</code></div>
        </div>
      )}

      <table className="grid">
        <thead>
          <tr><th>Назначение</th><th>Префикс</th><th>Права</th>
            <th>Создан</th><th>Последнее обращение</th><th></th></tr>
        </thead>
        <tbody>
          {rows.map((k) => (
            <tr key={k.id}>
              <td>{k.name}</td>
              <td className="muted"><code>{k.prefix}…</code></td>
              <td><span className="type-tag">{k.role}</span></td>
              <td className="muted">{new Date(k.created_at).toLocaleDateString("ru-RU")}</td>
              <td className="muted">
                {k.last_used_at ? new Date(k.last_used_at).toLocaleString("ru-RU") : "—"}
              </td>
              <td>
                {k.revoked_at ? (
                  <span className="badge b-red">отозван</span>
                ) : (
                  <button className="btn small" onClick={async () => {
                    if (!confirm("Отозвать ключ? Внешняя система потеряет доступ.")) return;
                    try { await api.revokeApiKey(k.id); load(); }
                    catch (e) { onError(e.message); }
                  }}>Отозвать</button>
                )}
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={6} className="muted" style={{ textAlign: "center", padding: 30 }}>
              Ключей нет.
            </td></tr>
          )}
        </tbody>
      </table>
    </>
  );
}

function AgentJournal({ onError }) {
  const [rows, setRows] = useState([]);
  const [stats, setStats] = useState(null);

  useEffect(() => {
    api.agentLog({ limit: 100 }).then(setRows).catch((e) => onError(e.message));
    api.agentStats().then(setStats).catch(() => {});
  }, [onError]);

  return (
    <>
      {stats && stats.total > 0 && (
        <div className="dash-grid" style={{ marginBottom: 16 }}>
          <div className="card dash-card">
            <h3 style={{ marginTop: 0 }}>Вопросов</h3>
            <div className="stat-value">{stats.total}</div>
          </div>
          <div className="card dash-card">
            <h3 style={{ marginTop: 0 }}>Отказов</h3>
            <div className="stat-value">{stats.refused}</div>
            <p className="muted" style={{ marginBottom: 0 }}>ответ «нет информации»</p>
          </div>
          <div className="card dash-card">
            <h3 style={{ marginTop: 0 }}>Среднее время</h3>
            <div className="stat-value">{(stats.avg_ms / 1000).toFixed(1)} с</div>
          </div>
        </div>
      )}
      <table className="grid">
        <thead>
          <tr><th>Дата</th><th>Пользователь</th><th>Вопрос</th><th>Ответ</th>
            <th>Источники</th><th>Уверенность</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td className="muted">{new Date(r.ts).toLocaleString("ru-RU")}</td>
              <td>{r.user_email}</td>
              <td>{r.question}</td>
              <td className="muted" style={{ maxWidth: 420 }}>
                {r.answer.length > 300 ? `${r.answer.slice(0, 300)}…` : r.answer}
              </td>
              <td className="muted">
                {r.sources.length === 0 ? "—" : (
                  <ul style={{ paddingLeft: 16, margin: 0 }}>
                    {r.sources.map((s, i) => (
                      <li key={i}>{s.title}{s.page_no ? `, с. ${s.page_no}` : ""}</li>
                    ))}
                  </ul>
                )}
              </td>
              <td>
                {r.refused ? <span className="badge b-amber">отказ</span>
                  : r.cancelled ? <span className="badge">остановлен</span>
                    : <span className="type-tag">{r.confidence || r.route}</span>}
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={6} className="muted" style={{ textAlign: "center", padding: 30 }}>
              Вопросов ассистенту пока не задавали.
            </td></tr>
          )}
        </tbody>
      </table>
    </>
  );
}

function Tickets({ onError }) {
  const [rows, setRows] = useState([]);
  const [answers, setAnswers] = useState({});

  function load() {
    api.listTickets().then(setRows).catch((e) => onError(e.message));
  }
  useEffect(load, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function answer(id) {
    onError("");
    try {
      await api.answerTicket(id, { answer: answers[id] || "", status: "Закрыто" });
      setAnswers((a) => ({ ...a, [id]: "" }));
      load();
    } catch (e) { onError(e.message); }
  }

  return (
    <table className="grid">
      <thead>
        <tr><th>Дата</th><th>От кого</th><th>Тема</th><th>Текст</th>
          <th>Статус</th><th>Ответ</th></tr>
      </thead>
      <tbody>
        {rows.map((t) => (
          <tr key={t.id}>
            <td className="muted">{new Date(t.created_at).toLocaleString("ru-RU")}</td>
            <td>{t.user_email}</td>
            <td><b>{t.subject}</b></td>
            <td className="muted">{t.body}</td>
            <td><span className="type-tag">{t.status}</span></td>
            <td>
              {t.answer ? <span className="muted">{t.answer}</span> : (
                <>
                  <textarea rows={2} value={answers[t.id] || ""}
                            onChange={(e) => setAnswers({ ...answers, [t.id]: e.target.value })} />
                  <button className="btn small" onClick={() => answer(t.id)}>Ответить</button>
                </>
              )}
            </td>
          </tr>
        ))}
        {rows.length === 0 && (
          <tr><td colSpan={6} className="muted" style={{ textAlign: "center", padding: 30 }}>
            Обращений нет.
          </td></tr>
        )}
      </tbody>
    </table>
  );
}
