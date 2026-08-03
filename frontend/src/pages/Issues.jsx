import { useEffect, useState, useCallback } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { useSort, SortTh, dateKey } from "../sort.jsx";

const fmtD = (d) => (d ? new Date(d).toLocaleDateString("ru-RU") : "—");

const STATUS_CLS = { "Заказ": "b-amber", "Выдано": "b-gray", "Возвращено": "b-green" };

const ISSUE_SORT = {
  case_index: (i) => i.case_index,
  requested_by: (i) => i.requested_by,
  order_date: (i) => dateKey(i.order_date),
  issue_date: (i) => dateKey(i.issue_date),
  due_date: (i) => dateKey(i.due_date),
  status: (i) => i.status,
};

export default function Issues() {
  const { user } = useAuth();
  const canEdit = ["admin", "archivist"].includes(user?.role);
  const [issues, setIssues] = useState([]);
  const sort = useSort(issues, ISSUE_SORT);
  const [cases, setCases] = useState([]);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ case_id: "", requested_by: "", purpose: "", due_date: "" });
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api.listIssues().then(setIssues).catch((e) => setError(e.message));
    api.listCases().then(setCases).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  async function create(e) {
    e.preventDefault();
    setError("");
    try {
      const payload = { ...form };
      if (!payload.due_date) delete payload.due_date;
      await api.createIssue(payload);
      setCreating(false);
      setForm({ case_id: "", requested_by: "", purpose: "", due_date: "" });
      load();
    } catch (e2) { setError(e2.message); }
  }

  const onHands = issues.filter((i) => i.status === "Выдано");
  const overdue = onHands.filter((i) => i.overdue);

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Выдача дел</h1>
          <p className="muted">Заказ → акт выдачи → возврат (прил. 20–22 приказа № 235) · на руках: {onHands.length}{overdue.length > 0 ? ` · просрочено: ${overdue.length}` : ""}</p>
        </div>
        {canEdit && <button className="btn primary" onClick={() => setCreating(true)}>+ Заказ на выдачу</button>}
      </header>

      {error && <div className="alert error">{error}</div>}
      {overdue.length > 0 && (
        <div className="alert error">⚠ Просрочен возврат: {overdue.map((i) => `${i.case_index} (${i.requested_by})`).join(", ")}</div>
      )}

      {creating && (
        <form className="card form" style={{ marginBottom: 18 }} onSubmit={create}>
          <label>Дело</label>
          <select value={form.case_id} onChange={(e) => setForm({ ...form, case_id: e.target.value })} required>
            <option value="">— выберите дело —</option>
            {cases.map((c) => (
              <option key={c.id} value={c.id}>{c.index ? `${c.index} · ` : ""}{c.title} ({c.year})</option>
            ))}
          </select>
          <div className="row2">
            <div>
              <label>Кому выдаётся</label>
              <input value={form.requested_by} onChange={(e) => setForm({ ...form, requested_by: e.target.value })} required placeholder="ФИО / подразделение" />
            </div>
            <div>
              <label>Срок возврата</label>
              <input type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
            </div>
          </div>
          <label>Цель использования</label>
          <input value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })} placeholder="служебная необходимость…" />
          <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
            <button className="btn primary">Создать заказ</button>
            <button type="button" className="btn" onClick={() => setCreating(false)}>Отмена</button>
          </div>
        </form>
      )}

      <table className="grid">
        <thead>
          <tr>
            <SortTh label="Дело" sortKey="case_index" sort={sort} />
            <SortTh label="Кому" sortKey="requested_by" sort={sort} />
            <SortTh label="Заказ" sortKey="order_date" sort={sort} />
            <SortTh label="Выдано" sortKey="issue_date" sort={sort} />
            <SortTh label="Возврат до" sortKey="due_date" sort={sort} />
            <SortTh label="Статус" sortKey="status" sort={sort} />
            <th></th>
          </tr>
        </thead>
        <tbody>
          {sort.sorted.map((i) => (
            <tr key={i.id}>
              <td><b>{i.case_index || "—"}</b> <span className="muted small">{i.case_title}</span></td>
              <td>{i.requested_by}</td>
              <td className="muted">{fmtD(i.order_date)}</td>
              <td className="muted">{fmtD(i.issue_date)}</td>
              <td className={i.overdue ? "ret-date" : "muted"}>{fmtD(i.due_date)}</td>
              <td>
                <span className={`badge ${STATUS_CLS[i.status] || "b-gray"}`}>{i.status}</span>
                {i.overdue && <span className="badge b-red" style={{ marginLeft: 6 }}>просрочено</span>}
              </td>
              <td style={{ whiteSpace: "nowrap" }}>
                {canEdit && i.status === "Заказ" && (
                  <button className="btn small" onClick={async () => { await api.markIssued(i.id); load(); }}>Выдать</button>
                )}
                {canEdit && i.status === "Выдано" && (
                  <button className="btn small" onClick={async () => { await api.markReturned(i.id); load(); }}>Вернуть</button>
                )}
                <button className="btn small" style={{ marginLeft: 6 }}
                  onClick={() => api.downloadBlob(`/issues/${i.id}/act`, "issue_act.pdf").catch((e) => setError(e.message))}>
                  Акт PDF
                </button>
              </td>
            </tr>
          ))}
          {issues.length === 0 && (
            <tr><td colSpan={7} className="muted" style={{ textAlign: "center", padding: 30 }}>
              Выдач пока нет.
            </td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
