import { useEffect, useState, useCallback } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { useSort, SortTh, PERMANENT_RANK } from "../sort.jsx";

const NOM_SORT = {
  index: (n) => n.index,
  title: (n) => n.title,
  year: (n) => n.year,
  article: (n) => n.article,
  retention: (n) => (n.permanent ? PERMANENT_RANK : n.retention_years ?? null),
};

const EMPTY = {
  index: "", title: "", year: new Date().getFullYear(),
  article: "", retention_label: "5 лет", retention_years: 5, permanent: false, note: "",
};

const PRESETS = [
  { label: "5 лет", years: 5, permanent: false },
  { label: "10 лет", years: 10, permanent: false },
  { label: "75 лет", years: 75, permanent: false },
  { label: "Постоянно", years: null, permanent: true },
  { label: "До минования надобности", years: null, permanent: false },
];

export default function Nomenclature() {
  const { user } = useAuth();
  const canEdit = ["admin", "archivist"].includes(user?.role);
  const [items, setItems] = useState([]);
  const sort = useSort(items, NOM_SORT);
  const [form, setForm] = useState(EMPTY);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api.listNomenclature().then(setItems).catch((e) => setError(e.message));
  }, []);
  useEffect(() => { load(); }, [load]);

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

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Номенклатура дел</h1>
          <p className="muted">Систематизированный перечень дел со сроками хранения (перечень 279-НҚ)</p>
        </div>
        {canEdit && <button className="btn primary" onClick={() => setCreating(true)}>+ Добавить статью</button>}
      </header>

      {error && <div className="alert error">{error}</div>}

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
          <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
            <button className="btn primary">Добавить</button>
            <button type="button" className="btn" onClick={() => setCreating(false)}>Отмена</button>
          </div>
        </form>
      )}

      <table className="grid">
        <thead>
          <tr>
            <SortTh label="Индекс" sortKey="index" sort={sort} />
            <SortTh label="Заголовок дела" sortKey="title" sort={sort} />
            <SortTh label="Год" sortKey="year" sort={sort} />
            <SortTh label="Статья" sortKey="article" sort={sort} />
            <SortTh label="Срок хранения" sortKey="retention" sort={sort} />
            {canEdit && <th></th>}
          </tr>
        </thead>
        <tbody>
          {sort.sorted.map((n) => (
            <tr key={n.id}>
              <td><b>{n.index}</b></td>
              <td>{n.title}</td>
              <td className="muted">{n.year}</td>
              <td className="muted">{n.article || "—"}</td>
              <td><span className="type-tag">{n.permanent ? "Постоянно" : n.retention_label}</span></td>
              {canEdit && (
                <td>
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
          {items.length === 0 && (
            <tr><td colSpan={canEdit ? 6 : 5} className="muted" style={{ textAlign: "center", padding: 30 }}>
              Номенклатура пуста. Добавьте статьи — они зададут индексы и сроки хранения для дел.
            </td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
