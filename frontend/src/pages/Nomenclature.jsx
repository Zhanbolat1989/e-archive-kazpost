import { useEffect, useState, useCallback, useMemo } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { useSort, SortTh, PERMANENT_RANK } from "../sort.jsx";
import ApprovalPanel from "../components/ApprovalPanel.jsx";

const NOM_SORT = {
  index: (n) => n.index,
  title: (n) => n.title,
  year: (n) => n.year,
  article: (n) => n.article,
  retention: (n) => (n.permanent ? PERMANENT_RANK : n.retention_years ?? null),
  status: (n) => n.status,
};

// Жизненный цикл статьи номенклатуры (ТЗ АГП п. 8).
const STATUS_CLASS = {
  "Проект": "b-gray",
  "На согласовании": "b-amber",
  "Действующая": "b-green",
  "Архивная": "b-gray",
};

const EMPTY = {
  index: "", title: "", year: new Date().getFullYear(),
  article: "", retention_label: "5 лет", retention_years: 5, permanent: false, note: "",
  doc_types: [],
};

const PRESETS = [
  { label: "5 лет", years: 5, permanent: false },
  { label: "10 лет", years: 10, permanent: false },
  { label: "75 лет", years: 75, permanent: false },
  { label: "Постоянно", years: null, permanent: true },
  { label: "До минования надобности", years: null, permanent: false },
];

// Виды документов статьи (ТС-176 п. 4.5): по ним модуль «Сканирование»
// ограничивает ввод сканов в дела статьи.
function DocTypesSelect({ groups, value, onChange }) {
  return (
    <select multiple size={8} value={value}
            onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
      {groups.map((g) => (
        <optgroup key={g.group} label={g.group}>
          {g.types.map((t) => <option key={t} value={t}>{t}</option>)}
        </optgroup>
      ))}
    </select>
  );
}

export default function Nomenclature() {
  const { user } = useAuth();
  const canEdit = ["admin", "archivist"].includes(user?.role);
  const [items, setItems] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [statuses, setStatuses] = useState([]);
  const [filterStatus, setFilterStatus] = useState("");
  const [typeGroups, setTypeGroups] = useState([]);
  const [editingTypes, setEditingTypes] = useState(null);
  const [approvalFor, setApprovalFor] = useState(null); // статья с открытым согласованием
  const shown = useMemo(
    () => (filterStatus ? items.filter((n) => n.status === filterStatus) : items),
    [items, filterStatus]
  );
  const sort = useSort(shown, NOM_SORT);

  const load = useCallback(() => {
    api.listNomenclature().then(setItems).catch((e) => setError(e.message));
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.nomenclatureStatuses().then(setStatuses).catch(() => {});
    api.documentTypes().then(setTypeGroups).catch(() => {});
  }, []);

  async function changeStatus(item, status) {
    setError("");
    try {
      await api.setNomenclatureStatus(item.id, status);
      load();
    } catch (e) { setError(e.message); }
  }

  function pickPreset(label) {
    const p = PRESETS.find((x) => x.label === label);
    setForm((f) => ({ ...f, retention_label: p.label, retention_years: p.years, permanent: p.permanent }));
  }

  async function create(e) {
    e.preventDefault();
    setError("");
    try {
      await api.createNomenclature({ ...form, year: Number(form.year) });
      setForm(EMPTY);
      setCreating(false);
      load();
    } catch (e2) { setError(e2.message); }
  }

  async function saveTypes() {
    setError("");
    try {
      await api.updateNomenclature(editingTypes.id, {
        doc_types: editingTypes.doc_types, version: editingTypes.version,
      });
      setEditingTypes(null);
      load();
    } catch (e) { setError(e.message); }
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Номенклатура дел</h1>
          <p className="muted">Систематизированный перечень дел со сроками хранения (перечень 279-НҚ)</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn"
                  title="Сводная номенклатура дел организации в Excel (ТЗ АГП п. 8)"
                  onClick={() => api.downloadBlob("/nomenclature/summary/xlsx", "nomenclature.xlsx")
                    .catch((e) => setError(e.message))}>
            Сводная в Excel
          </button>
          {canEdit && <button className="btn primary" onClick={() => setCreating(true)}>+ Добавить статью</button>}
        </div>
      </header>

      {error && <div className="alert error">{error}</div>}

      <div className="card" style={{ marginBottom: 16 }}>
        <label>Статус статьи</label>
        <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
          <option value="">все</option>
          {statuses.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      {creating && (
        <form className="card form" style={{ marginBottom: 18 }} onSubmit={create}>
          <div className="row3">
            <div>
              <label>Индекс дела</label>
              <input value={form.index} onChange={(e) => setForm({ ...form, index: e.target.value })} placeholder="оставьте пустым — присвоится автоматически" />
            </div>
            <div>
              <label>Год</label>
              <input type="number" value={form.year} onChange={(e) => setForm({ ...form, year: e.target.value })} />
            </div>
            <div>
              <label>Статья перечня 279-НҚ</label>
              <input value={form.article} onChange={(e) => setForm({ ...form, article: e.target.value })} placeholder="напр. 224" />
            </div>
          </div>
          <label>Заголовок дела</label>
          <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required placeholder="Договоры аренды помещений" />
          <label>Срок хранения</label>
          <select value={form.retention_label} onChange={(e) => pickPreset(e.target.value)}>
            {PRESETS.map((p) => <option key={p.label} value={p.label}>{p.label}</option>)}
          </select>
          <label>Виды документов в делах статьи</label>
          <DocTypesSelect groups={typeGroups} value={form.doc_types}
                          onChange={(doc_types) => setForm({ ...form, doc_types })} />
          <div className="muted small">
            Ctrl/Shift — несколько видов. Ничего не выбрано — при сканировании принимаются любые виды.
          </div>
          <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
            <button className="btn primary">Добавить</button>
            <button type="button" className="btn" onClick={() => setCreating(false)}>Отмена</button>
          </div>
        </form>
      )}

      {editingTypes && (
        <div className="card form" style={{ marginBottom: 18 }}>
          <h3 style={{ marginTop: 0 }}>Виды документов: {editingTypes.index} · {editingTypes.title}</h3>
          <DocTypesSelect groups={typeGroups} value={editingTypes.doc_types}
                          onChange={(doc_types) => setEditingTypes({ ...editingTypes, doc_types })} />
          <div className="muted small">
            Ctrl/Shift — несколько видов. Ничего не выбрано — в дела статьи принимаются любые виды.
          </div>
          <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
            <button className="btn primary" onClick={saveTypes}>Сохранить</button>
            <button className="btn" onClick={() => setEditingTypes(null)}>Отмена</button>
          </div>
        </div>
      )}

      {/* Согласование статьи по маршруту оргструктуры (ТС-176 п. 4.10): без
          согласованного маршрута статья не вводится в действие. */}
      {approvalFor && (
        <div className="card" style={{ marginBottom: 18 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
            <h3 style={{ margin: 0 }}>Согласование: {approvalFor.index} · {approvalFor.title}</h3>
            <button className="icon-btn" onClick={() => setApprovalFor(null)}>✕</button>
          </div>
          <ApprovalPanel objectType="nomenclature" objectId={approvalFor.id}
            canStart={["Проект", "На согласовании"].includes(approvalFor.status)}
            onStarted={load} />
        </div>
      )}

      <table className="grid">
        <thead>
          <tr>
            <SortTh label="Индекс" sortKey="index" sort={sort} />
            <SortTh label="Заголовок дела" sortKey="title" sort={sort} />
            <SortTh label="Год" sortKey="year" sort={sort} />
            <SortTh label="Статья" sortKey="article" sort={sort} />
            <SortTh label="Срок хранения" sortKey="retention" sort={sort} />
            <SortTh label="Статус" sortKey="status" sort={sort} />
            {canEdit && <th></th>}
          </tr>
        </thead>
        <tbody>
          {sort.sorted.map((n) => (
            <tr key={n.id}>
              <td><b>{n.index}</b></td>
              <td>
                {n.title}
                {n.doc_types?.length > 0 && (
                  <div className="muted small">Виды: {n.doc_types.join(", ")}</div>
                )}
              </td>
              <td className="muted">{n.year}</td>
              <td className="muted">{n.article || "—"}</td>
              <td><span className="type-tag">{n.permanent ? "Постоянно" : n.retention_label}</span></td>
              <td>
                <span className={`badge ${STATUS_CLASS[n.status] || ""}`}>{n.status}</span>
              </td>
              {canEdit && (
                <td style={{ whiteSpace: "nowrap" }}>
                  {/* Ввести в действие можно только согласованную статью:
                      сервер отклонит переход, если маршрут не завершён. */}
                  <select value="" onChange={(e) => e.target.value && changeStatus(n, e.target.value)}>
                    <option value="">статус…</option>
                    {statuses.filter((s) => s !== n.status).map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>{" "}
                  <button className="icon-btn" title="Согласование статьи"
                    onClick={() => setApprovalFor({
                      id: n.id, index: n.index, title: n.title, status: n.status,
                    })}>
                    📝
                  </button>{" "}
                  <button className="icon-btn" title="Виды документов (для модуля «Сканирование»)"
                    onClick={() => setEditingTypes({
                      id: n.id, index: n.index, title: n.title, version: n.version,
                      doc_types: n.doc_types || [],
                    })}>
                    🗂
                  </button>{" "}
                  <button className="icon-btn" title="Удалить"
                    onClick={async () => {
                      if (!confirm("Удалить статью номенклатуры?")) return;
                      setError("");
                      // 409, если по статье уже заведены дела.
                      try { await api.deleteNomenclature(n.id); }
                      catch (e) { setError(e.message); return; }
                      load();
                    }}>
                    🗑
                  </button>
                </td>
              )}
            </tr>
          ))}
          {shown.length === 0 && (
            <tr><td colSpan={canEdit ? 7 : 6} className="muted" style={{ textAlign: "center", padding: 30 }}>
              {filterStatus
                ? `Статей со статусом «${filterStatus}» нет.`
                : "Номенклатура пуста. Добавьте статьи — они зададут индексы и сроки хранения для дел."}
            </td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
