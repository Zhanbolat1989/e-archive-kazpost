import { useEffect, useState, useCallback } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { useSort, SortTh } from "../sort.jsx";

// Модуль «Описи дел» (ТЗ АГП п. 8): карточки описей, автоформирование по
// категориям сроков хранения, вложения и выгрузка в Excel. Решения ЭК, ЦЭК и
// ЭПК по описи вносятся в разделе «НТО и передача» (ТС-176 п. 10.2–10.5).
const SORT = {
  number: (i) => i.number,
  title: (i) => i.title,
  year: (i) => i.year,
  kind: (i) => i.kind,
  items: (i) => i.items_count,
};

export default function Inventories() {
  const { user } = useAuth();
  const canEdit = ["admin", "archivist"].includes(user?.role);
  const [rows, setRows] = useState([]);
  const [kinds, setKinds] = useState([]);
  const [open, setOpen] = useState(null);      // развёрнутая опись
  const [attachments, setAttachments] = useState([]);
  const [decisions, setDecisions] = useState([]);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ year: new Date().getFullYear(), kind: "", autofill: true });
  const [error, setError] = useState("");
  const sort = useSort(rows, SORT);

  const load = useCallback(() => {
    api.listInventories().then(setRows).catch((e) => setError(e.message));
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.inventoryKinds().then((k) => {
      setKinds(k);
      setForm((f) => ({ ...f, kind: f.kind || k[0] }));
    }).catch(() => {});
  }, []);

  async function show(id) {
    setError("");
    setDecisions([]);
    api.objectDecisions("inventory", id).then(setDecisions).catch(() => {});
    try {
      setOpen(await api.getInventory(id));
      setAttachments(await api.listAttachments("inventory", id));
    } catch (e) { setError(e.message); }
  }

  async function create(e) {
    e.preventDefault();
    setError("");
    try {
      const inv = await api.createInventory({ ...form, year: Number(form.year) });
      setCreating(false);
      load();
      show(inv.id);
    } catch (e2) { setError(e2.message); }
  }

  async function attach(file) {
    if (!file) return;
    setError("");
    try {
      await api.uploadAttachment("inventory", open.id, file);
      setAttachments(await api.listAttachments("inventory", open.id));
    } catch (e) { setError(e.message); }
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Описи дел</h1>
          <p className="muted">
            Перечни единиц хранения по категориям сроков · описей: {rows.length}
          </p>
        </div>
        {canEdit && (
          <button className="btn primary" onClick={() => setCreating(true)}>+ Новая опись</button>
        )}
      </header>

      {error && <div className="alert error">{error}</div>}

      {creating && (
        <form className="card form" style={{ marginBottom: 18 }} onSubmit={create}>
          <div className="row3">
            <div>
              <label>Год</label>
              <input type="number" value={form.year}
                     onChange={(e) => setForm({ ...form, year: e.target.value })} />
            </div>
            <div>
              <label>Категория описи</label>
              <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                {kinds.map((k) => <option key={k}>{k}</option>)}
              </select>
            </div>
            <div>
              <label>Состав</label>
              <select value={form.autofill ? "auto" : "manual"}
                      onChange={(e) => setForm({ ...form, autofill: e.target.value === "auto" })}>
                <option value="auto">сформировать автоматически по срокам</option>
                <option value="manual">пустая опись</option>
              </select>
            </div>
          </div>
          <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
            <button className="btn primary">Создать</button>
            <button type="button" className="btn" onClick={() => setCreating(false)}>Отмена</button>
          </div>
        </form>
      )}

      <table className="grid">
        <thead>
          <tr>
            <SortTh label="Номер" sortKey="number" sort={sort} />
            <SortTh label="Заголовок" sortKey="title" sort={sort} />
            <SortTh label="Год" sortKey="year" sort={sort} />
            <SortTh label="Категория" sortKey="kind" sort={sort} />
            <SortTh label="Дел" sortKey="items" sort={sort} />
            <th></th>
          </tr>
        </thead>
        <tbody>
          {sort.sorted.map((i) => (
            <tr key={i.id}>
              <td><b>{i.number}</b></td>
              <td>{i.title}</td>
              <td className="muted">{i.year}</td>
              <td><span className="type-tag">{i.kind}</span></td>
              <td className="num">{i.items_count}</td>
              <td style={{ whiteSpace: "nowrap" }}>
                <button className="btn small" onClick={() => show(i.id)}>Открыть</button>{" "}
                <button className="btn small" onClick={() =>
                  api.downloadBlob(`/inventories/${i.id}/xlsx`, `opis_${i.number}.xlsx`)
                    .catch((e) => setError(e.message))}>
                  Excel
                </button>
                {user?.role === "admin" && (
                  <>
                    {" "}
                    <button className="icon-btn" title="Удалить опись" onClick={async () => {
                      if (!confirm("Удалить опись?")) return;
                      try { await api.deleteInventory(i.id); setOpen(null); load(); }
                      catch (e) { setError(e.message); }
                    }}>🗑</button>
                  </>
                )}
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={6} className="muted" style={{ textAlign: "center", padding: 30 }}>
              Описей нет. Создайте опись — система подберёт дела по категории срока хранения.
            </td></tr>
          )}
        </tbody>
      </table>

      {open && (
        <div className="card" style={{ marginTop: 18 }}>
          <header className="page-head" style={{ marginBottom: 10 }}>
            <div>
              <h3 style={{ margin: 0 }}>{open.number} · {open.title}</h3>
              <p className="muted" style={{ margin: 0 }}>
                {open.kind} · дел в описи: {open.items.length} · статус: {open.status}
              </p>
            </div>
            <div>
              {canEdit && (
                <button className="btn small" onClick={async () => {
                  if (!confirm("Пересобрать состав описи? Ручные правки состава будут потеряны.")) return;
                  try { setOpen(await api.refillInventory(open.id)); load(); }
                  catch (e) { setError(e.message); }
                }}>Пересобрать по срокам</button>
              )}{" "}
              <button className="btn small" onClick={() => setOpen(null)}>Закрыть</button>
            </div>
          </header>

          {decisions.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <h4 style={{ margin: "0 0 6px" }}>Решения экспертных комиссий</h4>
              <ul className="muted" style={{ margin: 0, lineHeight: 1.8 }}>
                {decisions.map((d) => (
                  <li key={d.id}>
                    <b>{d.decision_label}</b> — {d.protocol}{d.comment ? ` · ${d.comment}` : ""}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <table className="grid">
            <thead>
              <tr>
                <th>№</th><th>Индекс дела</th><th>Заголовок</th>
                <th>Год</th><th>Документов</th><th>Срок хранения</th>
              </tr>
            </thead>
            <tbody>
              {open.items.map((it) => (
                <tr key={it.case_id}>
                  <td className="num">{it.order_no}</td>
                  <td><b>{it.case_index}</b></td>
                  <td>{it.case_title}</td>
                  <td className="muted">{it.year}</td>
                  <td className="num">{it.documents_count}</td>
                  <td><span className="type-tag">{it.retention}</span></td>
                </tr>
              ))}
              {open.items.length === 0 && (
                <tr><td colSpan={6} className="muted" style={{ textAlign: "center", padding: 20 }}>
                  В описи нет дел этой категории за {open.year} год.
                </td></tr>
              )}
            </tbody>
          </table>

          <h4 style={{ marginBottom: 6 }}>Вложения</h4>
          <ul className="muted" style={{ lineHeight: 1.8 }}>
            {attachments.map((a) => (
              <li key={a.id}>
                <a href="#" onClick={(e) => {
                  e.preventDefault();
                  api.downloadBlob(`/attachments/${a.id}/download`, a.filename)
                    .catch((err) => setError(err.message));
                }}>{a.filename}</a>{" "}
                · {Math.round(a.size / 1024)} КБ · {a.uploaded_by}
                {canEdit && (
                  <> · <a href="#" onClick={async (e) => {
                    e.preventDefault();
                    await api.deleteAttachment(a.id);
                    setAttachments(await api.listAttachments("inventory", open.id));
                  }}>удалить</a></>
                )}
              </li>
            ))}
            {attachments.length === 0 && <li>файлов нет</li>}
          </ul>
          {canEdit && (
            <input type="file" onChange={(e) => attach(e.target.files[0])} />
          )}
        </div>
      )}
    </div>
  );
}
