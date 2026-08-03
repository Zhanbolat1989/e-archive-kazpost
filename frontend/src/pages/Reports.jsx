import { useEffect, useState, useCallback } from "react";
import { api } from "../api.js";
import { useSort, SortTh } from "../sort.jsx";

// Заголовки колонок отчётов: ключ из API → человекочитаемое название.
const LABEL = {
  index: "Индекс", title: "Заголовок", year: "Год", status: "Статус",
  documents: "Док-в", retention: "Срок хранения", retention_until: "Хранить до",
  date_from: "Дата с", date_to: "Дата по", doc_type: "Тип", doc_number: "Номер",
  counterparty: "Контрагент", doc_date: "Дата документа", signature: "ЭЦП",
  case_id: "Дело", created_at: "Принят", case_index: "Дело",
  case_title: "Заголовок дела", requested_by: "Кому", purpose: "Цель",
  order_date: "Заказ", issue_date: "Выдано", due_date: "Возврат до",
  returned_at: "Возвращено", overdue: "Просрочено", number: "Номер акта",
  act_date: "Дата акта", kind: "Вид", created_by: "Составил",
  approved_by: "Утвердил", approved_at: "Утверждён",
};

const fmt = (v) => {
  if (v === true) return "да";
  if (v === false) return "—";
  if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}/.test(v)) {
    return new Date(v).toLocaleDateString("ru-RU");
  }
  return v === "" || v == null ? "—" : String(v);
};

export default function Reports() {
  const [reports, setReports] = useState([]);
  const [active, setActive] = useState("cases");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const rows = data?.rows || [];
  const columns = rows.length ? Object.keys(rows[0]) : [];
  // Сортировка строится по фактическим колонкам выбранного отчёта.
  const accessors = Object.fromEntries(columns.map((c) => [c, (r) => r[c]]));
  const sort = useSort(rows, accessors);

  useEffect(() => {
    api.listReports().then(setReports).catch((e) => setError(e.message));
  }, []);

  const load = useCallback((key) => {
    setLoading(true);
    api.getReport(key)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(active); }, [active, load]);

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Отчеты</h1>
          <p className="muted">Сводные отчеты по архивному фонду (п. 4.4 ТС)</p>
        </div>
        {data && rows.length > 0 && (
          <button
            className="btn"
            onClick={() => api.downloadBlob(`/reports/${active}/csv`, `report_${active}.csv`)
              .catch((e) => setError(e.message))}
          >
            ⬇️ Выгрузить CSV
          </button>
        )}
      </header>

      {error && <div className="alert error">{error}</div>}

      <div className="suggestions" style={{ marginBottom: 16 }}>
        {reports.map((r) => (
          <button
            key={r.key}
            className={`chip ${active === r.key ? "active" : ""}`}
            onClick={() => setActive(r.key)}
          >
            {r.title}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="muted">Загрузка…</div>
      ) : !data ? null : (
        <>
          <div className="kpi-row" style={{ marginBottom: 16 }}>
            <div className="card dash-card">
              <div className="kpi-val">{data.total}</div>
              <div className="kpi-lbl">всего записей</div>
            </div>
            {Object.entries(data.summary || {}).slice(0, 5).map(([k, v]) => (
              <div className="card dash-card" key={k}>
                <div className="kpi-val">{v}</div>
                <div className="kpi-lbl">{k}</div>
              </div>
            ))}
          </div>

          {rows.length === 0 ? (
            <div className="empty">
              <div className="empty-icon">📊</div>
              <p>По этому отчету данных пока нет.</p>
            </div>
          ) : (
            <table className="grid">
              <thead>
                <tr>
                  {columns.map((c) => (
                    <SortTh key={c} label={LABEL[c] || c} sortKey={c} sort={sort} />
                  ))}
                </tr>
              </thead>
              <tbody>
                {sort.sorted.map((r, i) => (
                  <tr key={i}>
                    {columns.map((c) => (
                      <td key={c} className={c === "overdue" && r[c] ? "ret-date" : "muted"}>
                        {fmt(r[c])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
