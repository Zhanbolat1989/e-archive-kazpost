import { useEffect, useState, useCallback } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { useSort, SortTh, dateKey } from "../sort.jsx";

// Реестр архивных запросов (ТЗ АГП п. 8): обращение → исполнитель → ответ.
const SORT = {
  number: (r) => r.number,
  reg_date: (r) => dateKey(r.reg_date),
  applicant: (r) => r.applicant,
  status: (r) => r.status,
  due_date: (r) => dateKey(r.due_date),
};

// Пока справочник не загружен или пуст (ТС-176 п. 4.9).
const FALLBACK_TYPES = ["Тематический", "Социально-правовой", "Биографический", "Имущественный"];

const EMPTY = {
  applicant: "", applicant_contact: "", request_type: "", subject: "",
  executor_email: "", due_date: "",
};

const STATUS_CLASS = {
  "Зарегистрирован": "b-blue",
  "В работе": "b-amber",
  "Исполнен": "b-green",
  "Отказано": "b-red",
};

export default function ArchiveRequests() {
  const { user } = useAuth();
  const canEdit = ["admin", "archivist"].includes(user?.role);
  const [rows, setRows] = useState([]);
  const [statuses, setStatuses] = useState([]);
  const [types, setTypes] = useState(FALLBACK_TYPES);
  const [filter, setFilter] = useState({ status: "", overdue: "" });
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState("");
  const sort = useSort(rows, SORT);

  const load = useCallback(() => {
    const params = { ...filter };
    if (params.overdue === "") delete params.overdue;
    api.listArchiveRequests(params).then(setRows).catch((e) => setError(e.message));
  }, [filter]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.requestStatuses().then(setStatuses).catch(() => {});
    api.dictionaryValues("request_types")
      .then((values) => values.length && setTypes(values))
      .catch(() => {});
  }, []);

  // Пока вид не выбран, в запрос уходит первый из справочника.
  const requestType = form.request_type || types[0];

  async function create(e) {
    e.preventDefault();
    setError("");
    try {
      const payload = { ...form, request_type: requestType };
      if (!payload.due_date) delete payload.due_date;
      await api.createArchiveRequest(payload);
      setForm(EMPTY);
      setCreating(false);
      load();
    } catch (e2) { setError(e2.message); }
  }

  async function setStatus(row, status) {
    setError("");
    try {
      await api.updateArchiveRequest(row.id, { status, version: row.version });
      load();
    } catch (e) { setError(e.message); }
  }

  const overdue = rows.filter((r) => r.overdue).length;

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Архивные запросы</h1>
          <p className="muted">
            Обращения за сведениями и копиями документов · всего {rows.length}
            {overdue > 0 && <> · <span className="badge b-red">просрочено: {overdue}</span></>}
          </p>
        </div>
        {canEdit && (
          <button className="btn primary" onClick={() => setCreating(true)}>
            + Зарегистрировать запрос
          </button>
        )}
      </header>

      {error && <div className="alert error">{error}</div>}

      <div className="card" style={{ marginBottom: 16, display: "flex", gap: 12, flexWrap: "wrap" }}>
        <div>
          <label>Статус</label>
          <select value={filter.status} onChange={(e) => setFilter({ ...filter, status: e.target.value })}>
            <option value="">все</option>
            {statuses.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <label>Срок</label>
          <select value={filter.overdue} onChange={(e) => setFilter({ ...filter, overdue: e.target.value })}>
            <option value="">все</option>
            <option value="true">просроченные</option>
            <option value="false">в срок</option>
          </select>
        </div>
      </div>

      {creating && (
        <form className="card form" style={{ marginBottom: 18 }} onSubmit={create}>
          <div className="row3">
            <div>
              <label>Заявитель</label>
              <input value={form.applicant} required
                     onChange={(e) => setForm({ ...form, applicant: e.target.value })}
                     placeholder="ФИО или организация" />
            </div>
            <div>
              <label>Контакты</label>
              <input value={form.applicant_contact}
                     onChange={(e) => setForm({ ...form, applicant_contact: e.target.value })}
                     placeholder="телефон, e-mail" />
            </div>
            <div>
              <label>Вид запроса</label>
              <select value={requestType}
                      onChange={(e) => setForm({ ...form, request_type: e.target.value })}>
                {types.map((t) => <option key={t}>{t}</option>)}
              </select>
            </div>
          </div>
          <label>Содержание запроса</label>
          <textarea rows={3} value={form.subject}
                    onChange={(e) => setForm({ ...form, subject: e.target.value })}
                    placeholder="о чём запрошены сведения" />
          <div className="row3">
            <div>
              <label>Исполнитель (e-mail)</label>
              <input value={form.executor_email}
                     onChange={(e) => setForm({ ...form, executor_email: e.target.value })} />
            </div>
            <div>
              <label>Срок исполнения</label>
              <input type="date" value={form.due_date}
                     onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
              <div className="muted" style={{ fontSize: 12 }}>
                по умолчанию — 30 дней с даты регистрации
              </div>
            </div>
          </div>
          <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
            <button className="btn primary">Зарегистрировать</button>
            <button type="button" className="btn" onClick={() => setCreating(false)}>Отмена</button>
          </div>
        </form>
      )}

      <table className="grid">
        <thead>
          <tr>
            <SortTh label="Номер" sortKey="number" sort={sort} />
            <SortTh label="Дата" sortKey="reg_date" sort={sort} />
            <SortTh label="Заявитель" sortKey="applicant" sort={sort} />
            <th>Содержание</th>
            <SortTh label="Срок" sortKey="due_date" sort={sort} />
            <SortTh label="Статус" sortKey="status" sort={sort} />
            {canEdit && <th></th>}
          </tr>
        </thead>
        <tbody>
          {sort.sorted.map((r) => (
            <tr key={r.id}>
              <td><b>{r.number}</b><div className="muted" style={{ fontSize: 12 }}>{r.request_type}</div></td>
              <td className="muted">{new Date(r.reg_date).toLocaleDateString("ru-RU")}</td>
              <td>
                {r.applicant}
                {r.applicant_contact && (
                  <div className="muted" style={{ fontSize: 12 }}>{r.applicant_contact}</div>
                )}
              </td>
              <td className="muted">{r.subject || "—"}</td>
              <td className={r.overdue ? "badge b-red" : "muted"}>
                {r.due_date ? new Date(r.due_date).toLocaleDateString("ru-RU") : "—"}
              </td>
              <td><span className={`badge ${STATUS_CLASS[r.status] || ""}`}>{r.status}</span></td>
              {canEdit && (
                <td>
                  <select value="" onChange={(e) => e.target.value && setStatus(r, e.target.value)}>
                    <option value="">изменить статус…</option>
                    {statuses.filter((s) => s !== r.status).map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </td>
              )}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={canEdit ? 7 : 6} className="muted" style={{ textAlign: "center", padding: 30 }}>
                Запросов нет. Зарегистрируйте обращение — система проследит срок исполнения.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
