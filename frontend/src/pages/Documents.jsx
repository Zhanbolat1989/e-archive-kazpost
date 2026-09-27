import { useEffect, useState, useCallback } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { StatusBadge, SignatureBadge } from "../components/StatusBadge.jsx";
import DocumentModal from "../components/DocumentModal.jsx";
import { useSort, SortTh, dateKey } from "../sort.jsx";

const DOC_SORT = {
  title: (d) => d.title,
  doc_type: (d) => d.doc_type,
  counterparty: (d) => d.counterparty,
  amount: (d) => (d.amount != null ? Number(d.amount) : null),
  date: (d) => dateKey(d.doc_date || d.created_at),
  pages: (d) => d.page_count,
  status: (d) => (d.destroyed_at ? "уничтожен" : d.status),
};

// Фильтры модуля «Документы».
const RETENTION = [
  { value: "", label: "любой срок" },
  { value: "permanent", label: "постоянного хранения" },
  { value: "expired", label: "срок истёк — к уничтожению" },
  { value: "expiring", label: "истекает в ближайший год" },
  { value: "active", label: "срок не подходит" },
];

const EMPTY_FILTER = {
  department_id: "", doc_group: "", retention: "", year: "", needs_review: "",
};

export default function Documents() {
  const { user } = useAuth();
  const [docs, setDocs] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState(EMPTY_FILTER);
  const [departments, setDepartments] = useState([]);
  const [groups, setGroups] = useState([]);
  const [error, setError] = useState("");
  const sort = useSort(docs, DOC_SORT);

  const load = useCallback(async () => {
    try {
      const params = Object.fromEntries(
        Object.entries(filter).filter(([, v]) => v !== "")
      );
      setDocs(await api.listDocuments({ ...params, limit: 200 }));
      setError("");
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    api.listDepartments().then(setDepartments).catch(() => {});
    api.documentTypes().then((g) => setGroups(g.map((x) => x.group))).catch(() => {});
  }, []);

  async function open(id) {
    setSelected(await api.getDocument(id));
  }

  // Auto-refresh while anything is still being processed.
  useEffect(() => {
    const active = docs.some((d) =>
      ["uploaded", "scanning", "processing"].includes(d.status)
    );
    if (!active) return;
    const t = setInterval(load, 2500);
    return () => clearInterval(t);
  }, [docs, load]);

  const filtered = Object.values(filter).some((v) => v !== "");

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Документы</h1>
          <p className="muted">
            Каталог архива · {docs.length} записей{filtered ? " по фильтру" : ""}
          </p>
        </div>
      </header>

      {error && <div className="alert error">{error}</div>}

      <div className="card" style={{ marginBottom: 16, display: "flex", gap: 12, flexWrap: "wrap" }}>
        <div>
          <label>Подразделение</label>
          <select value={filter.department_id}
                  onChange={(e) => setFilter({ ...filter, department_id: e.target.value })}>
            <option value="">все</option>
            {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </div>
        <div>
          <label>Категория документов</label>
          <select value={filter.doc_group}
                  onChange={(e) => setFilter({ ...filter, doc_group: e.target.value })}>
            <option value="">все</option>
            {groups.map((g) => <option key={g} value={g}>{g}</option>)}
          </select>
        </div>
        <div>
          <label>Срок хранения</label>
          <select value={filter.retention}
                  onChange={(e) => setFilter({ ...filter, retention: e.target.value })}>
            {RETENTION.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        </div>
        <div>
          <label>Год документа</label>
          <input type="number" style={{ width: 110 }} value={filter.year}
                 placeholder="все"
                 onChange={(e) => setFilter({ ...filter, year: e.target.value })} />
        </div>
        <div>
          <label>Распознавание</label>
          <select value={filter.needs_review}
                  onChange={(e) => setFilter({ ...filter, needs_review: e.target.value })}>
            <option value="">все</option>
            <option value="true">требуют проверки</option>
            <option value="false">проверены</option>
          </select>
        </div>
        {filtered && (
          <div style={{ alignSelf: "flex-end" }}>
            <button className="btn small" onClick={() => setFilter(EMPTY_FILTER)}>
              Сбросить
            </button>
          </div>
        )}
      </div>

      {loading ? (
        <div className="muted">Загрузка…</div>
      ) : docs.length === 0 ? (
        <div className="empty">
          <div className="empty-icon">📭</div>
          <p>
            {filtered
              ? "По заданным условиям документов нет — измените фильтр."
              : "Архив пуст. Перейдите в раздел «Приём», чтобы загрузить первый документ."}
          </p>
        </div>
      ) : (
        <table className="grid">
          <thead>
            <tr>
              <SortTh label="Наименование" sortKey="title" sort={sort} />
              <SortTh label="Тип" sortKey="doc_type" sort={sort} />
              <SortTh label="Контрагент" sortKey="counterparty" sort={sort} />
              <SortTh label="Сумма" sortKey="amount" sort={sort} />
              <SortTh label="Дата" sortKey="date" sort={sort} />
              <SortTh label="Стр." sortKey="pages" sort={sort} />
              <SortTh label="Статус" sortKey="status" sort={sort} />
            </tr>
          </thead>
          <tbody>
            {sort.sorted.map((d) => (
              <tr key={d.id} onClick={() => open(d.id)}>
                <td>
                  <div className="doc-title">{d.title}</div>
                  <div className="doc-file muted">{d.doc_number || d.original_filename}</div>
                </td>
                <td><span className="type-tag">{d.doc_type}</span></td>
                <td className="muted">{d.counterparty || "—"}</td>
                <td className="num">{d.amount != null ? `${Number(d.amount).toLocaleString("ru-RU")} ₸` : "—"}</td>
                <td className="muted">
                  {d.doc_date
                    ? new Date(d.doc_date).toLocaleDateString("ru-RU")
                    : new Date(d.created_at).toLocaleDateString("ru-RU")}
                </td>
                <td className="num">{d.page_count ?? "—"}</td>
                <td>
                  {d.destroyed_at ? (
                    <span className="badge b-red">🗑 уничтожен</span>
                  ) : (
                    <>
                      <StatusBadge status={d.status} />{" "}
                      <SignatureBadge status={d.signature_status} />
                      {d.needs_review && (
                        <> <span className="badge b-amber" title={d.review_reason}>
                          проверить
                        </span></>
                      )}
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {selected && (
        <DocumentModal
          key={selected.id}
          doc={selected}
          canDelete={user?.role === "admin"}
          onClose={() => setSelected(null)}
          onChanged={load}
          onOpenDocument={open}
        />
      )}
    </div>
  );
}
