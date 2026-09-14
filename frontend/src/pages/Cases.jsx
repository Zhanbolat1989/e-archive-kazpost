import { useEffect, useState, useCallback } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import DocumentModal from "../components/DocumentModal.jsx";
import ApprovalPanel from "../components/ApprovalPanel.jsx";
import { useSort, SortTh, dateKey, PERMANENT_RANK } from "../sort.jsx";

const CASE_STATUS = {
  "Формируется": "b-amber",
  "Закрыто": "b-green",
  "Передано": "b-gray",
  "Уничтожено": "b-red",
};

const CASE_SORT = {
  index: (c) => c.index,
  title: (c) => c.title,
  year: (c) => c.year,
  documents_count: (c) => c.documents_count,
  retention: (c) => (c.permanent ? PERMANENT_RANK : c.retention_years ?? null),
  retention_until: (c) => (c.permanent ? PERMANENT_RANK : dateKey(c.retention_until)),
  status: (c) => c.status,
};

const fmtD = (d) => (d ? new Date(d).toLocaleDateString("ru-RU") : "—");

export default function Cases() {
  const { user } = useAuth();
  const canEdit = ["admin", "archivist"].includes(user?.role);
  const [cases, setCases] = useState([]);
  const sort = useSort(cases, CASE_SORT);
  const [nomenclature, setNomenclature] = useState([]);
  const [selected, setSelected] = useState(null); // CaseDetail
  const [docModal, setDocModal] = useState(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ title: "", index: "", nomenclature_id: "", year: new Date().getFullYear() });
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api.listCases().then(setCases).catch((e) => setError(e.message));
    api.listNomenclature().then(setNomenclature).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

  async function openCase(id) {
    setSelected(await api.getCase(id));
  }

  async function openDoc(id) {
    setDocModal(await api.getDocument(id));
  }

  async function create(e) {
    e.preventDefault();
    setError("");
    try {
      const payload = { ...form, year: Number(form.year) || undefined };
      if (!payload.nomenclature_id) delete payload.nomenclature_id;
      await api.createCase(payload);
      setCreating(false);
      setForm({ title: "", index: "", nomenclature_id: "", year: new Date().getFullYear() });
      load();
    } catch (e2) { setError(e2.message); }
  }

  async function closeCase() {
    await api.updateCase(selected.id, { status: "Закрыто" });
    await openCase(selected.id);
    load();
  }

  function pickNom(id) {
    const n = nomenclature.find((x) => x.id === id);
    setForm((f) => ({
      ...f, nomenclature_id: id,
      index: n ? n.index : f.index,
      title: f.title || (n ? n.title : ""),
    }));
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Дела</h1>
          <p className="muted">Единицы хранения · {cases.length} дел</p>
        </div>
        {canEdit && (
          <button className="btn primary" onClick={() => setCreating(true)}>+ Завести дело</button>
        )}
      </header>

      {error && <div className="alert error">{error}</div>}

      {creating && (
        <form className="card form" style={{ marginBottom: 18 }} onSubmit={create}>
          <div className="row3">
            <div>
              <label>Статья номенклатуры</label>
              <select value={form.nomenclature_id} onChange={(e) => pickNom(e.target.value)}>
                <option value="">— без номенклатуры —</option>
                {nomenclature.map((n) => (
                  <option key={n.id} value={n.id}>{n.index} · {n.title} ({n.retention_label || "срок не задан"})</option>
                ))}
              </select>
            </div>
            <div>
              <label>Индекс дела</label>
              <input value={form.index} onChange={(e) => setForm({ ...form, index: e.target.value })} placeholder="из номенклатуры или автоматически" />
            </div>
            <div>
              <label>Год</label>
              <input type="number" value={form.year} onChange={(e) => setForm({ ...form, year: e.target.value })} />
            </div>
          </div>
          <label>Заголовок дела</label>
          <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required placeholder="Договоры аренды помещений за 2023 год" />
          <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
            <button className="btn primary">Создать</button>
            <button type="button" className="btn" onClick={() => setCreating(false)}>Отмена</button>
          </div>
        </form>
      )}

      <table className="grid">
        <thead>
          <tr>
            <SortTh label="Индекс" sortKey="index" sort={sort} />
            <SortTh label="Заголовок" sortKey="title" sort={sort} />
            <SortTh label="Год" sortKey="year" sort={sort} />
            <SortTh label="Док-в" sortKey="documents_count" sort={sort} />
            <SortTh label="Срок хранения" sortKey="retention" sort={sort} />
            <SortTh label="Хранить до" sortKey="retention_until" sort={sort} />
            <SortTh label="Статус" sortKey="status" sort={sort} />
          </tr>
        </thead>
        <tbody>
          {sort.sorted.map((c) => (
            <tr key={c.id} onClick={() => openCase(c.id)}>
              <td><b>{c.index || "—"}</b>{c.volume > 1 ? ` т.${c.volume}` : ""}</td>
              <td className="doc-title">{c.title}</td>
              <td className="muted">{c.year}</td>
              <td>{c.documents_count}</td>
              <td className="muted">{c.permanent ? "Постоянно" : (c.retention_label || "—")}</td>
              <td className="muted">{c.permanent ? "∞" : fmtD(c.retention_until)}</td>
              <td><span className={`badge ${CASE_STATUS[c.status] || "b-gray"}`}>{c.status}</span></td>
            </tr>
          ))}
          {cases.length === 0 && (
            <tr><td colSpan={7} className="muted" style={{ textAlign: "center", padding: 30 }}>
              Дел пока нет. Заведите первое дело.
            </td></tr>
          )}
        </tbody>
      </table>

      {selected && (
        <div className="modal-backdrop" onClick={() => setSelected(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <h2>{selected.index && <span className="muted">{selected.index} · </span>}{selected.title}</h2>
              <button className="icon-btn" onClick={() => setSelected(null)}>✕</button>
            </div>
            <div className="badges">
              <span className={`badge ${CASE_STATUS[selected.status] || "b-gray"}`}>{selected.status}</span>
              <span className="badge b-gray">{selected.permanent ? "Постоянно" : (selected.retention_label || "срок не задан")}</span>
              {selected.retention_until && !selected.permanent && (
                <span className="badge b-amber">хранить до {fmtD(selected.retention_until)}</span>
              )}
            </div>
            <div className="meta-grid">
              <div><span>Год</span>{selected.year}</div>
              <div><span>Крайние даты</span>{fmtD(selected.date_from)} — {fmtD(selected.date_to)}</div>
              <div><span>Документов</span>{selected.documents_count}</div>
              <div><span>Том</span>{selected.volume}</div>
            </div>

            {selected.annotation && (
              <div className="annotation">
                <div className="annotation-label">📝 Аннотация дела (ИИ)</div>
                <p>{selected.annotation}</p>
              </div>
            )}

            <h3 style={{ margin: "10px 0 8px" }}>Документы дела</h3>
            {selected.documents.length === 0 && (
              <p className="muted">В деле пока нет документов. Привяжите их при загрузке (Приём) или из карточки документа.</p>
            )}
            <div className="case-docs">
              {selected.documents.map((d, i) => (
                <div key={d.id} className="case-doc-row">
                  <span className="case-doc-num">{i + 1}.</span>
                  <button className="linklike" onClick={() => openDoc(d.id)}>
                    {d.title}
                  </button>
                  <span className="muted small">{d.doc_number} · {fmtD(d.doc_date)}</span>
                  {canEdit && (
                    <button className="icon-btn" title="Изъять из дела"
                      onClick={async () => { await api.removeDocFromCase(selected.id, d.id); openCase(selected.id); }}>
                      ✕
                    </button>
                  )}
                </div>
              ))}
            </div>

            <ApprovalPanel objectType="case" objectId={selected.id}
              canStart={canEdit && selected.status !== "Уничтожено"} />

            <h3 style={{ margin: "16px 0 8px" }}>Нормативные формы</h3>
            <div className="forms-grid">
              {[
                ["internal_opis", "📋 Внутренняя опись", "прил. 28"],
                ["zaverit", "📃 Лист-заверитель", "прил. 31"],
                ["e_opis", "💾 Опись эл. дела", "№ 236"],
                ["cover", "📕 Обложка дела", ""],
              ].map(([kind, label, hint]) => (
                <div className="form-row" key={kind}>
                  <span className="form-label">{label} {hint && <span className="muted small">({hint})</span>}</span>
                  <span className="form-btns">
                    <button className="btn small" onClick={() =>
                      api.downloadForm(selected.id, kind, "pdf", `${kind}_${selected.index || "delo"}.pdf`)
                        .catch((e) => setError(e.message))}>PDF</button>
                    <button className="btn small" onClick={() =>
                      api.downloadForm(selected.id, kind, "docx", `${kind}_${selected.index || "delo"}.docx`)
                        .catch((e) => setError(e.message))}>DOCX</button>
                    {canEdit && (
                      <button className="btn small" title="Сохранить PDF в архив (WORM)" onClick={async () => {
                        try { await api.archiveForm(selected.id, kind); openCase(selected.id); }
                        catch (e) { setError(e.message); }
                      }}>→ в архив</button>
                    )}
                  </span>
                </div>
              ))}
            </div>

            <div className="modal-actions">
              {canEdit && selected.status === "Формируется" && (
                <button className="btn" onClick={closeCase}>📁 Закрыть дело</button>
              )}
              {canEdit && selected.documents.length > 0 && (
                <button className="btn"
                  title="Краткое содержание дела по аннотациям его документов (ТЗ АГП п. 12.4)"
                  onClick={async () => {
                    setError("");
                    try {
                      await api.annotateCase(selected.id);
                      openCase(selected.id);
                    } catch (e) { setError(e.message); }
                  }}>
                  📝 Аннотация дела (ИИ)
                </button>
              )}
              {canEdit && (
                <button className="btn" title="Информационный пакет для передачи в госархив"
                  onClick={() => api.downloadBlob(`/cases/${selected.id}/export`, `case_${selected.index || "delo"}.zip`).catch((e) => setError(e.message))}>
                  📦 Экспорт дела (ZIP)
                </button>
              )}
              {canEdit && (
                <button className="btn" title="Все документы дела одним файлом, готово к печати"
                  onClick={() => api.downloadBlob(`/cases/${selected.id}/print`, `print_${selected.index || "delo"}.pdf`)
                    .then(({ skipped }) => {
                      if (skipped > 0) setError(`Готово, но ${skipped} документ(ов) не удалось включить в печать (неподдерживаемый формат) — см. журнал аудита.`);
                    })
                    .catch((e) => setError(e.message))}>
                  🖨 Печать документов (PDF)
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {docModal && (
        <DocumentModal key={docModal.id} doc={docModal} onClose={() => setDocModal(null)}
          onChanged={() => openCase(selected.id)} onOpenDocument={openDoc} />
      )}
    </div>
  );
}
