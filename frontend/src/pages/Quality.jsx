import { useEffect, useState, useCallback } from "react";
import { api } from "../api.js";
import DocumentModal from "../components/DocumentModal.jsx";
import { useAuth } from "../auth.jsx";
import { useSort, SortTh, dateKey } from "../sort.jsx";

// Контроль качества оцифровки: перечень документов, требующих
// ручной проверки, со сводкой по распознаванию.
const SORT = {
  title: (d) => d.title,
  pages: (d) => d.page_count,
  confidence: (d) => d.ocr_confidence,
  reason: (d) => d.review_reason,
  created: (d) => dateKey(d.created_at),
};

function confidenceBadge(value) {
  if (value == null) return <span className="muted">—</span>;
  const cls = value >= 85 ? "b-green" : value >= 70 ? "b-amber" : "b-red";
  return <span className={`badge ${cls}`}>{value.toFixed(0)}%</span>;
}

export default function Quality() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState("");
  const sort = useSort(data?.documents || [], SORT);

  const load = useCallback(() => {
    api.reviewQueue().then(setData).catch((e) => setError(e.message));
  }, []);

  useEffect(() => { load(); }, [load]);

  async function accept(id) {
    setError("");
    try {
      await api.acceptReview(id);
      load();
    } catch (e) { setError(e.message); }
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Качество оцифровки</h1>
          <p className="muted">
            Документы, требующие ручной проверки после распознавания
          </p>
        </div>
      </header>

      {error && <div className="alert error">{error}</div>}

      {data && (
        <div className="dash-grid" style={{ marginBottom: 18 }}>
          <div className="card dash-card">
            <h3 style={{ marginTop: 0 }}>На проверке</h3>
            <div className="stat-value">{data.total_flagged}</div>
            <p className="muted" style={{ marginBottom: 0 }}>документов</p>
          </div>
          <div className="card dash-card">
            <h3 style={{ marginTop: 0 }}>Средняя уверенность</h3>
            <div className="stat-value">
              {data.average_confidence != null ? `${data.average_confidence}%` : "—"}
            </div>
            <p className="muted" style={{ marginBottom: 0 }}>
              по {data.recognized_documents} распознанным
            </p>
          </div>
          <div className="card dash-card">
            <h3 style={{ marginTop: 0 }}>Страниц обработано</h3>
            <div className="stat-value">{data.total_pages.toLocaleString("ru-RU")}</div>
            <p className="muted" style={{ marginBottom: 0 }}>листов в архиве</p>
          </div>
        </div>
      )}

      <table className="grid">
        <thead>
          <tr>
            <SortTh label="Документ" sortKey="title" sort={sort} />
            <SortTh label="Страниц" sortKey="pages" sort={sort} />
            <SortTh label="Уверенность OCR" sortKey="confidence" sort={sort} />
            <SortTh label="Причина проверки" sortKey="reason" sort={sort} />
            <SortTh label="Принят" sortKey="created" sort={sort} />
            <th></th>
          </tr>
        </thead>
        <tbody>
          {sort.sorted.map((d) => (
            <tr key={d.id}>
              <td onClick={async () => setSelected(await api.getDocument(d.id))}
                  style={{ cursor: "pointer" }}>
                <div className="doc-title">{d.title}</div>
                <div className="doc-file muted">{d.doc_type}</div>
              </td>
              <td className="num">{d.page_count ?? "—"}</td>
              <td>{confidenceBadge(d.ocr_confidence)}</td>
              <td className="muted">
                {d.review_reason || "—"}
                {d.duplicate_of_id && (
                  <>
                    {" "}
                    <a href="#" onClick={async (e) => {
                      e.preventDefault();
                      setSelected(await api.getDocument(d.duplicate_of_id));
                    }}>открыть оригинал</a>
                  </>
                )}
              </td>
              <td className="muted">{new Date(d.created_at).toLocaleDateString("ru-RU")}</td>
              <td>
                <button className="btn small" onClick={() => accept(d.id)}>
                  Проверено
                </button>
              </td>
            </tr>
          ))}
          {data && data.documents.length === 0 && (
            <tr><td colSpan={6} className="muted" style={{ textAlign: "center", padding: 30 }}>
              Все документы распознаны уверенно — проверять нечего.
            </td></tr>
          )}
        </tbody>
      </table>

      {selected && (
        <DocumentModal
          key={selected.id}
          doc={selected}
          canDelete={user?.role === "admin"}
          onClose={() => setSelected(null)}
          onChanged={load}
          onOpenDocument={async (id) => setSelected(await api.getDocument(id))}
        />
      )}
    </div>
  );
}
