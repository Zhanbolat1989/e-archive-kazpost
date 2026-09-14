import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import DocumentModal from "../components/DocumentModal.jsx";

// Файлов за один запрос (сервер принимает до 20): обрыв соединения теряет
// только текущую порцию, а не всю партию.
const CHUNK = 10;

const isoToday = () => new Date().toISOString().slice(0, 10);
const monthStart = () => `${isoToday().slice(0, 8)}01`;

const STATE_BADGE = {
  wait: ["b-gray", "в очереди"],
  up: ["b-amber", "загрузка…"],
  ok: ["b-green", "принят"],
  err: ["b-red", "ошибка"],
};

const COPY_BADGE = {
  pending: "b-gray", certified: "b-green", mismatch: "b-red", no_original: "b-amber",
};

const TABS = [
  ["input", "Ввод сканов"],
  ["ecopies", "Электронные копии"],
  ["volume", "Объём оказанных услуг"],
];

export default function Scanning() {
  const { user } = useAuth();
  const canEdit = ["admin", "archivist"].includes(user?.role);
  const [tab, setTab] = useState("input");

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Сканирование</h1>
          <p className="muted">
            Ввод сканированных документов по номенклатуре дел, сверка электронных копий
            и учёт работ оцифровки (ТС-176 п. 4.5, разд. 8–12)
          </p>
        </div>
      </header>

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {TABS.map(([key, label]) => (
          <button key={key} className={`btn small ${tab === key ? "primary" : ""}`}
                  onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>

      {tab === "input" && <InputTab canEdit={canEdit} />}
      {tab === "ecopies" && <EcopiesTab canEdit={canEdit} />}
      {tab === "volume" && <VolumeTab />}
    </div>
  );
}

function InputTab({ canEdit }) {
  const [year, setYear] = useState(new Date().getFullYear());
  const [articles, setArticles] = useState([]);
  const [articleId, setArticleId] = useState("");
  const [caseId, setCaseId] = useState("");
  const [typeGroups, setTypeGroups] = useState([]);
  const [docType, setDocType] = useState("");
  const [departments, setDepartments] = useState([]);
  const [departmentId, setDepartmentId] = useState("");
  const [queue, setQueue] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [drag, setDrag] = useState(false);
  const inputRef = useRef();
  const keyRef = useRef(0);

  const load = useCallback(
    () => api.scanningArticles(year).then(setArticles).catch((e) => setError(e.message)),
    [year]
  );
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.documentTypes().then(setTypeGroups).catch(() => {});
    api.listDepartments().then(setDepartments).catch(() => {});
  }, []);

  const article = articles.find((a) => a.id === articleId);
  const selectedCase = article?.cases.find((c) => c.id === caseId);

  // Виды документов, которые разрешает статья; пустой список в статье — любые.
  const allowedGroups = useMemo(() => {
    if (!article || article.doc_types.length === 0) return typeGroups;
    return typeGroups
      .map((g) => ({ ...g, types: g.types.filter((t) => article.doc_types.includes(t)) }))
      .filter((g) => g.types.length > 0);
  }, [article, typeGroups]);

  useEffect(() => {
    // Выбранный вид недоступен в новой статье — сбрасываем, чтобы не отправить
    // на сервер вид, который он всё равно отклонит.
    const all = allowedGroups.flatMap((g) => g.types);
    if (!all.includes(docType)) setDocType(all[0] || "");
  }, [allowedGroups, docType]);

  function addFiles(list) {
    const items = Array.from(list || []).map((file) => ({
      key: ++keyRef.current, file, state: "wait", message: "",
    }));
    setQueue((q) => [...q, ...items]);
  }

  function mark(keys, state, message = "", perFile = null) {
    setQueue((q) => q.map((item) => {
      if (!keys.has(item.key)) return item;
      if (perFile) {
        const failure = perFile.get(item.file.name);
        return { ...item, state: failure ? "err" : "ok", message: failure || "" };
      }
      return { ...item, state, message };
    }));
  }

  async function openVolume() {
    setError("");
    try {
      const created = await api.scanningCreateCase({
        nomenclature_id: articleId, department_id: departmentId || null,
      });
      await load();
      setCaseId(created.id);
    } catch (e) { setError(e.message); }
  }

  async function upload() {
    if (!caseId || !docType) return;
    setBusy(true);
    setError("");
    const pending = queue.filter((q) => q.state === "wait" || q.state === "err");
    for (let i = 0; i < pending.length; i += CHUNK) {
      const part = pending.slice(i, i + CHUNK);
      const keys = new Set(part.map((p) => p.key));
      mark(keys, "up");
      const fd = new FormData();
      part.forEach((p) => fd.append("files", p.file));
      fd.append("doc_type", docType);
      fd.append("department_id", departmentId);
      try {
        const res = await api.scanningUpload(caseId, fd);
        mark(keys, "", "", new Map(res.errors.map((e) => [e.filename, e.error])));
      } catch (e) {
        mark(keys, "err", e.message);
      }
    }
    setBusy(false);
    load();
  }

  const pendingCount = queue.filter((q) => q.state === "wait" || q.state === "err").length;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.5fr) minmax(0, 1fr)", gap: 16 }}>
      <div className="card form">
        {error && <div className="alert error">{error}</div>}
        <div className="row2">
          <div>
            <label>Год номенклатуры</label>
            <input type="number" value={year}
                   onChange={(e) => { setYear(e.target.value); setArticleId(""); setCaseId(""); }} />
          </div>
          <div>
            <label>Подразделение</label>
            <select value={departmentId} onChange={(e) => setDepartmentId(e.target.value)}>
              <option value="">— из дела —</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>{d.index ? `${d.index} · ` : ""}{d.name}</option>
              ))}
            </select>
          </div>
        </div>

        <label>Статья номенклатуры</label>
        <select value={articleId} onChange={(e) => { setArticleId(e.target.value); setCaseId(""); }}>
          <option value="">— выберите статью —</option>
          {articles.map((a) => (
            <option key={a.id} value={a.id}>
              {a.index} · {a.title}{a.retention ? ` (${a.retention})` : ""}
            </option>
          ))}
        </select>
        {articles.length === 0 && (
          <div className="muted small">
            Номенклатуры за {year} год нет или она ещё в статусе «Проект».
          </div>
        )}
        {article && (
          <div className="muted small" style={{ marginTop: 4 }}>
            Виды документов по статье: {article.doc_types.length
              ? article.doc_types.join(", ")
              : "не ограничены (задаются в разделе «Номенклатура»)"}
          </div>
        )}

        {article && (
          <>
            <label>Дело (том)</label>
            <div style={{ display: "flex", gap: 8 }}>
              <select style={{ flex: 1 }} value={caseId} onChange={(e) => setCaseId(e.target.value)}>
                <option value="">— выберите том —</option>
                {article.cases.map((c) => (
                  <option key={c.id} value={c.id}>
                    Том {c.volume} · {c.status} · документов: {c.documents_count}
                  </option>
                ))}
              </select>
              {canEdit && (
                <button type="button" className="btn" onClick={openVolume}>+ Новый том</button>
              )}
            </div>
          </>
        )}

        {selectedCase && canEdit && (
          <>
            <label>Вид документа</label>
            <select value={docType} onChange={(e) => setDocType(e.target.value)}>
              {allowedGroups.map((g) => (
                <optgroup key={g.group} label={g.group}>
                  {g.types.map((t) => <option key={t} value={t}>{t}</option>)}
                </optgroup>
              ))}
            </select>

            <div
              className={`dropzone ${drag ? "over" : ""}`}
              style={{ marginTop: 12 }}
              onClick={() => inputRef.current.click()}
              onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files); }}
            >
              <input ref={inputRef} type="file" multiple hidden
                     onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
              <div className="dz-icon">🗂</div>
              <div>Перетащите сканы или нажмите для выбора</div>
              <div className="muted">
                Каждый файл — отдельный документ дела и электронная копия бумажного подлинника
              </div>
            </div>

            {queue.length > 0 && (
              <table className="grid" style={{ marginTop: 12 }}>
                <thead><tr><th>Файл</th><th>Размер</th><th>Состояние</th></tr></thead>
                <tbody>
                  {queue.map((q) => (
                    <tr key={q.key}>
                      <td>{q.file.name}</td>
                      <td className="num">{(q.file.size / 1024 / 1024).toFixed(1)} МБ</td>
                      <td>
                        <span className={`badge ${STATE_BADGE[q.state][0]}`}>{STATE_BADGE[q.state][1]}</span>
                        {q.message && <div className="muted small">{q.message}</div>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button type="button" className="btn primary" disabled={busy || pendingCount === 0 || !docType}
                      onClick={upload}>
                {busy ? "Приём…" : `Принять в дело (${pendingCount})`}
              </button>
              {queue.length > 0 && !busy && (
                <button type="button" className="btn"
                        onClick={() => setQueue((q) => q.filter((x) => x.state !== "ok"))}>
                  Убрать принятые
                </button>
              )}
            </div>
          </>
        )}
      </div>

      <div>
        {selectedCase
          ? <StagesPanel caseId={selectedCase.id} canEdit={canEdit}
                         title={`${selectedCase.index} · том ${selectedCase.volume}`} />
          : (
            <div className="card muted">
              Выберите статью номенклатуры и том дела: здесь появятся этапы работ по делу —
              НТО, экспертиза ценности, сканирование, прошивка и оцифровка.
            </div>
          )}
      </div>
    </div>
  );
}

function StagesPanel({ caseId, canEdit, title }) {
  const [stages, setStages] = useState([]);
  const [pages, setPages] = useState({});
  const [error, setError] = useState("");

  useEffect(() => {
    setStages([]);
    setPages({});
    api.scanningStages(caseId).then(setStages).catch((e) => setError(e.message));
  }, [caseId]);

  async function toggle(stage, done) {
    setError("");
    const raw = pages[stage.stage];
    try {
      setStages(await api.scanningSetStage(caseId, stage.stage, {
        done,
        // Пустое поле — объём считается по страницам принятых документов дела.
        pages: raw === undefined || raw === "" ? null : Number(raw),
      }));
    } catch (e) { setError(e.message); }
  }

  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>Этапы работ</h3>
      <div className="muted small" style={{ marginBottom: 8 }}>{title}</div>
      {error && <div className="alert error">{error}</div>}
      <table className="grid">
        <thead><tr><th>Этап</th><th>Страниц</th><th>Выполнен</th></tr></thead>
        <tbody>
          {stages.map((s) => (
            <tr key={s.stage}>
              <td>
                {s.label}
                {s.done && (
                  <div className="muted small">
                    {new Date(s.completed_at).toLocaleDateString("ru-RU")} · {s.performed_by}
                  </div>
                )}
              </td>
              <td>
                <input type="number" min="0" style={{ width: 90 }}
                       disabled={!canEdit}
                       value={pages[s.stage] ?? (s.done ? s.pages : "")}
                       placeholder="по документам"
                       onChange={(e) => setPages({ ...pages, [s.stage]: e.target.value })} />
              </td>
              <td>
                <input type="checkbox" checked={s.done} disabled={!canEdit}
                       onChange={(e) => toggle(s, e.target.checked)} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Реестр электронных копий (ТС-176 п. 11.6–11.7): результаты сверки с
// подлинником, опись копий и акт об уничтожении копий без подлинника.
function EcopiesTab({ canEdit }) {
  const [status, setStatus] = useState("");
  const [data, setData] = useState(null);
  const [checked, setChecked] = useState({});
  const [protocol, setProtocol] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [openDoc, setOpenDoc] = useState(null);

  const load = useCallback(
    () => api.listCopies({ status }).then(setData).catch((e) => setError(e.message)),
    [status]
  );
  useEffect(() => { setChecked({}); load(); }, [load]);

  const labels = Object.fromEntries((data?.statuses || []).map((s) => [s.key, s.label]));
  const destroyable = (d) => d.copy_status === "mismatch" || d.copy_status === "no_original";
  const picked = Object.keys(checked).filter((id) => checked[id]);

  async function open(id) {
    setError("");
    try { setOpenDoc(await api.getDocument(id)); } catch (e) { setError(e.message); }
  }

  async function createAct() {
    setError("");
    setNotice("");
    try {
      const act = await api.createCopyAct(picked, protocol.trim());
      setNotice(`Сформирован проект акта ${act.number}. Утверждение — в разделе «Уничтожение».`);
      setChecked({});
      setProtocol("");
      load();
    } catch (e) { setError(e.message); }
  }

  return (
    <div className="card">
      <div style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap", marginBottom: 12 }}>
        <div>
          <label>Результат сверки</label>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">все копии</option>
            {(data?.statuses || []).map((s) => (
              <option key={s.key} value={s.key}>{s.label} ({s.count})</option>
            ))}
          </select>
        </div>
        <button className="btn"
                onClick={() => api.downloadBlob("/ecopies/inventory/xlsx", "ecopies_inventory.xlsx")
                  .catch((e) => setError(e.message))}>
          Опись электронных копий (Excel)
        </button>
      </div>
      <p className="muted small" style={{ marginTop: 0 }}>
        Сверка с подлинником и удостоверение ЭЦП — в карточке документа (нажмите на строку).
        Копии без подлинника и с отрицательной сверкой уничтожаются по акту (ТС-176 п. 11.7).
      </p>
      {error && <div className="alert error">{error}</div>}
      {notice && <div className="alert success">{notice}</div>}

      {data && data.documents.length === 0 && (
        <p className="muted">Электронных копий с таким результатом сверки нет.</p>
      )}
      {data && data.documents.length > 0 && (
        <table className="grid">
          <thead>
            <tr>
              {canEdit && <th></th>}
              <th>Документ</th><th>Вид</th><th>Листов</th><th>Результат сверки</th><th>Сверка</th>
            </tr>
          </thead>
          <tbody>
            {data.documents.map((d) => (
              <tr key={d.id} style={{ cursor: "pointer" }} onClick={() => open(d.id)}>
                {canEdit && (
                  <td onClick={(e) => e.stopPropagation()}>
                    {destroyable(d) && (
                      <input type="checkbox" checked={!!checked[d.id]}
                             onChange={(e) => setChecked({ ...checked, [d.id]: e.target.checked })} />
                    )}
                  </td>
                )}
                <td>{d.title}</td>
                <td className="muted">{d.doc_type}</td>
                <td className="num">{d.page_count ?? "—"}</td>
                <td>
                  <span className={`badge ${COPY_BADGE[d.copy_status] || "b-gray"}`}>
                    {labels[d.copy_status] || d.copy_status}
                  </span>
                  {d.copy_note && <div className="muted small">{d.copy_note}</div>}
                </td>
                <td className="muted small">
                  {d.copy_checked_at
                    ? `${new Date(d.copy_checked_at).toLocaleDateString("ru-RU")} · ${d.copy_checked_by}`
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {canEdit && picked.length > 0 && (
        <div className="form" style={{ marginTop: 12 }}>
          <label>Протокол ЦЭК (ЭК) — можно указать и позже, до утверждения акта</label>
          <div style={{ display: "flex", gap: 8 }}>
            <input style={{ flex: 1 }} value={protocol} placeholder="напр. № 3 от 12.11.2026"
                   onChange={(e) => setProtocol(e.target.value)} />
            <button className="btn primary" onClick={createAct}>
              Сформировать акт об уничтожении копий ({picked.length})
            </button>
          </div>
        </div>
      )}

      {openDoc && (
        <DocumentModal doc={openDoc} onClose={() => setOpenDoc(null)} onChanged={load}
                       canDelete={false} onOpenDocument={open} />
      )}
    </div>
  );
}

function VolumeTab() {
  const [range, setRange] = useState({ date_from: monthStart(), date_to: isoToday() });
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    api.scanningVolume(range).then(setData).catch((e) => setError(e.message));
  }, [range]);

  const query = new URLSearchParams(range).toString();

  return (
    <div className="card">
      <div style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap", marginBottom: 12 }}>
        <div>
          <label>С</label>
          <input type="date" value={range.date_from}
                 onChange={(e) => setRange({ ...range, date_from: e.target.value })} />
        </div>
        <div>
          <label>По</label>
          <input type="date" value={range.date_to}
                 onChange={(e) => setRange({ ...range, date_to: e.target.value })} />
        </div>
        <button className="btn"
                onClick={() => api.downloadBlob(`/scanning/volume/xlsx?${query}`, "services_volume.xlsx")
                  .catch((e) => setError(e.message))}>
          Выгрузить в Excel
        </button>
      </div>
      {error && <div className="alert error">{error}</div>}
      {data && (
        <>
          <p className="muted" style={{ marginTop: 0 }}>
            Принято документов в дела за период: {data.documents}, страниц: {data.document_pages}
          </p>
          <table className="grid">
            <thead><tr><th>Этап работ</th><th>Дел</th><th>Страниц</th></tr></thead>
            <tbody>
              {data.summary.map((s) => (
                <tr key={s.stage}>
                  <td>{s.label}</td>
                  <td className="num">{s.cases}</td>
                  <td className="num">{s.pages}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.rows.length > 0 && (
            <table className="grid" style={{ marginTop: 16 }}>
              <thead>
                <tr><th>Дата</th><th>Этап</th><th>Дело</th><th>Том</th><th>Страниц</th><th>Исполнитель</th></tr>
              </thead>
              <tbody>
                {data.rows.map((r, i) => (
                  <tr key={`${r.case_id}-${r.stage}-${i}`}>
                    <td className="muted">{new Date(r.completed_at).toLocaleDateString("ru-RU")}</td>
                    <td>{r.label}</td>
                    <td>{r.case}</td>
                    <td className="num">{r.volume}</td>
                    <td className="num">{r.pages}</td>
                    <td className="muted">{r.performed_by}</td>
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
