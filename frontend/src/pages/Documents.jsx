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
  status: (d) => (d.destroyed_at ? "уничтожен" : d.status),
};

export default function Documents() {
  const { user } = useAuth();
  const [docs, setDocs] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const sort = useSort(docs, DOC_SORT);

  const load = useCallback(async () => {
    try {
      setDocs(await api.listDocuments());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

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

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Документы</h1>
          <p className="muted">Каталог архива · {docs.length} записей</p>
        </div>
      </header>

      {loading ? (
        <div className="muted">Загрузка…</div>
      ) : docs.length === 0 ? (
        <div className="empty">
          <div className="empty-icon">📭</div>
          <p>Архив пуст. Перейдите в раздел «Приём», чтобы загрузить первый документ.</p>
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
                <td>
                  {d.destroyed_at ? (
                    <span className="badge b-red">🗑 уничтожен</span>
                  ) : (
                    <>
                      <StatusBadge status={d.status} />{" "}
                      <SignatureBadge status={d.signature_status} />
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
