import { useEffect, useState, useCallback } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";

const fmtD = (d) => (d ? new Date(d).toLocaleDateString("ru-RU") : "—");

// Основание уничтожения электронной копии (ТС-176 п. 11.7).
const COPY_REASON = {
  mismatch: "отрицательный результат сверки",
  no_original: "подлинник отсутствует",
};

export default function Lifecycle() {
  const { user } = useAuth();
  const canEdit = ["admin", "archivist"].includes(user?.role);
  const isAdmin = user?.role === "admin";
  const [acts, setActs] = useState([]);
  const [expired, setExpired] = useState([]);
  const [checked, setChecked] = useState({});
  const [selected, setSelected] = useState(null); // act detail
  const [protocol, setProtocol] = useState("");
  const [ledger, setLedger] = useState(null);
  const [audit, setAudit] = useState([]);
  const [error, setError] = useState("");
  const [modalError, setModalError] = useState("");
  const [busy, setBusy] = useState(false);
  const [overview, setOverview] = useState(null);

  const load = useCallback(() => {
    api.listDestructionActs().then(setActs).catch((e) => setError(e.message));
    api.dashboard().then((d) => setExpired(d.retention?.expired || [])).catch(() => {});
    api.ledger().then(setLedger).catch(() => {});
    api.destructionOverview().then(setOverview).catch(() => {});
    if (user?.role === "admin") api.auditLog().then(setAudit).catch(() => {});
  }, [user]);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    setProtocol(selected?.commission_protocol || "");
    setModalError("");
  }, [selected?.id, selected?.commission_protocol]);

  const pickedIds = Object.keys(checked).filter((k) => checked[k]);
  const isCopyAct = selected?.kind === "ecopy";

  async function createAct() {
    setBusy(true); setError("");
    try {
      const act = await api.createDestructionAct(pickedIds, true, "");
      setChecked({});
      load();
      setSelected(act);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  async function saveProtocol() {
    setBusy(true); setModalError("");
    try {
      setSelected(await api.updateDestructionAct(selected.id, { commission_protocol: protocol }));
      load();
    } catch (e) { setModalError(e.message); } finally { setBusy(false); }
  }

  async function approve() {
    const what = isCopyAct
      ? "Электронные копии будут помечены уничтоженными и исключены из поиска."
      : "Документы будут помечены уничтоженными и исключены из поиска.";
    if (!confirm(`Утвердить акт ${selected.number}? ${what}`)) return;
    setBusy(true); setModalError("");
    try {
      const act = await api.approveDestructionAct(selected.id);
      setSelected(act);
      load();
    } catch (e) { setModalError(e.message); } finally { setBusy(false); }
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Экспертиза ценности и уничтожение</h1>
          <p className="muted">Акты о выделении к уничтожению (прил. 14/15 приказа № 235) · акты об уничтожении электронных копий · книга учёта</p>
        </div>
      </header>

      {error && <div className="alert error">{error}</div>}

      {/* Перечни по срокам уничтожения (ТЗ АГП п. 8): подлежащие уничтожению,
          приближающиеся к сроку и не подлежащие уничтожению — с разбивкой по
          годам уничтожения. */}
      {overview && (
        <div className="card" style={{ marginBottom: 18 }}>
          <header className="page-head" style={{ marginBottom: 8 }}>
            <div>
              <h3 style={{ margin: 0 }}>Сроки уничтожения</h3>
              <p className="muted" style={{ margin: 0 }}>
                по состоянию на {fmtD(overview.as_of)}
              </p>
            </div>
            <button className="btn small"
                    onClick={() => api.downloadBlob("/destruction-overview/xlsx",
                                                    "destruction_overview.xlsx")
                      .catch((e) => setError(e.message))}>
              Выгрузить в Excel
            </button>
          </header>
          <div className="dash-grid">
            <div className="card dash-card">
              <h3 style={{ marginTop: 0 }}>Подлежат уничтожению</h3>
              <div className="stat-value">{overview.to_destroy.length}</div>
              <p className="muted" style={{ marginBottom: 0 }}>срок хранения истёк</p>
            </div>
            <div className="card dash-card">
              <h3 style={{ marginTop: 0 }}>Срок приближается</h3>
              <div className="stat-value">{overview.approaching.length}</div>
              <p className="muted" style={{ marginBottom: 0 }}>истекает в ближайший год</p>
            </div>
            <div className="card dash-card">
              <h3 style={{ marginTop: 0 }}>Не подлежат уничтожению</h3>
              <div className="stat-value">{overview.not_subject_total}</div>
              <p className="muted" style={{ marginBottom: 0 }}>постоянного хранения</p>
            </div>
          </div>
          {overview.by_destruction_year.length > 0 && (
            <table className="grid" style={{ marginTop: 12 }}>
              <thead>
                <tr><th>Год уничтожения</th><th>Документов</th><th>Уничтожено фактически</th></tr>
              </thead>
              <tbody>
                {overview.by_destruction_year.map((row) => {
                  const done = overview.destroyed_by_year.find((d) => d.year === row.year);
                  return (
                    <tr key={row.year}>
                      <td><b>{row.year}</b></td>
                      <td className="num">{row.documents}</td>
                      <td className="num">{done ? done.documents : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      <div className="dash-grid">
        <div className="card dash-card wide">
          <h3>⌛ Документы с истёкшим сроком хранения</h3>
          {expired.length === 0 && <p className="muted">Истёкших сроков нет.</p>}
          {expired.map((r) => (
            <label className="ret-row" key={r.id} style={{ cursor: canEdit ? "pointer" : "default" }}>
              <span>
                {canEdit && (
                  <input type="checkbox" checked={!!checked[r.id]}
                    onChange={(e) => setChecked({ ...checked, [r.id]: e.target.checked })}
                    style={{ marginRight: 8 }} />
                )}
                {r.title} <span className="muted small">({r.doc_type} · {r.retention_label})</span>
              </span>
              <span className="ret-date">{fmtD(r.retention_until)}</span>
            </label>
          ))}
          {canEdit && expired.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <button className="btn primary" disabled={pickedIds.length === 0 || busy} onClick={createAct}>
                Сформировать акт на уничтожение ({pickedIds.length})
              </button>
            </div>
          )}
        </div>

        <div className="card dash-card">
          <h3>📗 Книга учёта поступления и выбытия</h3>
          {!ledger ? <p className="muted">Загрузка…</p> : (
            <>
              <div className="kpi-row" style={{ gridTemplateColumns: "1fr 1fr 1fr", marginBottom: 10 }}>
                <div><div className="kpi-val" style={{ fontSize: "1.3rem" }}>{ledger.total_received}</div><div className="kpi-lbl">поступило</div></div>
                <div><div className="kpi-val" style={{ fontSize: "1.3rem" }}>{ledger.total_removed}</div><div className="kpi-lbl">выбыло</div></div>
                <div><div className="kpi-val" style={{ fontSize: "1.3rem" }}>{ledger.in_archive}</div><div className="kpi-lbl">в архиве</div></div>
              </div>
              {ledger.rows.slice(-6).map((r) => (
                <div className="ret-row" key={r.month}>
                  <span>{r.month}</span>
                  <span className="muted">+{r.received} / −{r.removed}</span>
                </div>
              ))}
            </>
          )}
        </div>

        <div className="card dash-card">
          <h3>🗂 Акты</h3>
          {acts.length === 0 && <p className="muted">Актов пока нет.</p>}
          {acts.map((a) => (
            <div className="ret-row" key={a.id} style={{ cursor: "pointer" }}
                 onClick={async () => setSelected(await api.getDestructionAct(a.id))}>
              <span>
                <b>{a.number}</b> · {a.items_count} {a.kind === "ecopy" ? "коп." : "док."}
              </span>
              <span className={`badge ${a.status === "Утверждён" ? "b-green" : "b-amber"}`}>{a.status}</span>
            </div>
          ))}
          {canEdit && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 14 }}>
              <button className="btn small" title="Акт проверки наличия и состояния (прил. 26): сверка SHA-256 с хранилищем"
                onClick={() => api.postBlob("/inventory-check/pdf", "inventory_check.pdf").catch((e) => setError(e.message))}>
                🔍 Проверка наличия (PDF)
              </button>
              <button className="btn small" title="Акт миграции ЭД в PDF/A (прил. 1)"
                onClick={() => api.downloadBlob("/migration-act/pdf", "migration_act.pdf").catch((e) => setError(e.message))}>
                🔄 Акт миграции (PDF)
              </button>
            </div>
          )}
        </div>

        {user?.role === "admin" && (
          <div className="card dash-card wide">
            <h3>📜 Журнал аудита</h3>
            {audit.length === 0 && <p className="muted">Записей пока нет.</p>}
            <div style={{ maxHeight: 280, overflow: "auto" }}>
              {audit.map((a) => (
                <div className="ret-row" key={a.id}>
                  <span>
                    <b>{a.action}</b> <span className="muted small">{a.detail?.slice(0, 60)}</span>
                  </span>
                  <span className="muted small" style={{ whiteSpace: "nowrap" }}>
                    {a.user_email.split("@")[0]} · {new Date(a.ts).toLocaleString("ru-RU")}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {selected && (
        <div className="modal-backdrop" onClick={() => setSelected(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <h2>Акт {selected.number}</h2>
              <button className="icon-btn" onClick={() => setSelected(null)}>✕</button>
            </div>
            <div className="badges">
              <span className={`badge ${selected.status === "Утверждён" ? "b-green" : "b-amber"}`}>{selected.status}</span>
              <span className="badge b-gray">
                {isCopyAct
                  ? "уничтожение электронных копий (ТС-176 п. 11.7)"
                  : selected.is_electronic ? "электронные документы (прил. 15)" : "бумажные (прил. 14)"}
              </span>
            </div>
            <div className="meta-grid">
              <div><span>Дата</span>{fmtD(selected.act_date)}</div>
              <div><span>Составил</span>{selected.created_by || "—"}</div>
              <div><span>Утвердил</span>{selected.approved_by || "—"}</div>
              <div><span>Документов</span>{selected.items_count}</div>
              {(isCopyAct || selected.commission_protocol) && (
                <div><span>Протокол ЦЭК (ЭК)</span>{selected.commission_protocol || "не указан"}</div>
              )}
            </div>
            {isCopyAct && canEdit && selected.status !== "Утверждён" && (
              <div className="form" style={{ margin: "8px 0 12px" }}>
                <label>Протокол ЦЭК (ЭК) — номер и дата</label>
                <div style={{ display: "flex", gap: 8 }}>
                  <input style={{ flex: 1 }} value={protocol} placeholder="напр. № 3 от 12.11.2026"
                         onChange={(e) => setProtocol(e.target.value)} />
                  <button className="btn" disabled={busy || protocol === (selected.commission_protocol || "")}
                          onClick={saveProtocol}>
                    Сохранить
                  </button>
                </div>
                <div className="muted small">
                  Акт об уничтожении копий утверждается руководителем по согласованию с ЦЭК (ЭК).
                </div>
              </div>
            )}
            <div className="case-docs">
              {selected.documents.map((d, i) => (
                <div key={d.id} className="case-doc-row">
                  <span className="case-doc-num">{i + 1}.</span>
                  <span>{d.title}</span>
                  <span className="muted small">
                    {isCopyAct
                      ? COPY_REASON[d.copy_status] || d.copy_status
                      : `${d.retention_label} · истёк ${fmtD(d.retention_until)}`}
                  </span>
                </div>
              ))}
            </div>
            {modalError && <div className="alert error">{modalError}</div>}
            <div className="modal-actions">
              <button className="btn" onClick={() => api.downloadActPdf(selected.id, selected.number).catch((e) => setModalError(e.message))}>
                ⬇️ Скачать акт (PDF)
              </button>
              {isAdmin && selected.status !== "Утверждён" && (
                <button className="btn danger" disabled={busy} onClick={approve}>
                  ✅ Утвердить акт
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
