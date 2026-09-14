import { Fragment, useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";

// Научно-техническая обработка, экспертные комиссии и передача дел в госархив
// (ТС-176 п. 5.3, 8.2, 10.2–10.5).
const TABS = [
  { key: "protocols", label: "Протоколы ЭК / ЦЭК / ЭПК" },
  { key: "records", label: "Документы НТО" },
  { key: "transfers", label: "Передача в госархив" },
];

const STATUS_CLASS = { "Проект": "b-gray", "Утверждён": "b-green", "Передано": "b-green" };
const DECISION_CLASS = { approved: "b-green", agreed: "b-green", revision: "b-amber", rejected: "b-red" };

const fmtD = (d) => (d ? new Date(d).toLocaleDateString("ru-RU") : "—");
const today = () => new Date().toISOString().slice(0, 10);
const protocolLabel = (p) => `${p.commission} № ${p.number} от ${fmtD(p.protocol_date)}`;

// Объекты, по которым комиссия принимает решение, — варианты выбора в протоколе.
const OBJECT_OPTIONS = {
  inventory: () => api.listInventories().then((rows) => rows.map((x) => ({
    id: x.id, label: `Опись № ${x.number}: ${x.title} (${x.status})`,
  }))),
  destruction_act: () => api.listDestructionActs().then((rows) => rows.map((x) => ({
    id: x.id, label: `Акт № ${x.number} (${x.status})`,
  }))),
  nto: () => api.listNtoRecords().then((rows) => rows.map((x) => ({
    id: x.id, label: `${x.number} · ${x.title}`,
  }))),
  transfer: () => api.listTransfers().then((rows) => rows.map((x) => ({
    id: x.id, label: `Акт приёма-передачи № ${x.number} (${x.status})`,
  }))),
};

// Действие с перезагрузкой списка; true — если удалось.
function useRunner(load, onError) {
  return useCallback(async (action) => {
    onError("");
    try {
      await action();
      load();
      return true;
    } catch (e) {
      onError(e.message);
      return false;
    }
  }, [load, onError]);
}

export default function Nto() {
  const { user } = useAuth();
  const canEdit = ["admin", "archivist"].includes(user?.role);
  const isAdmin = user?.role === "admin";
  const [tab, setTab] = useState("protocols");
  const [meta, setMeta] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => { api.ntoMeta().then(setMeta).catch((e) => setError(e.message)); }, []);

  const props = { meta, canEdit, isAdmin, onError: setError };

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>НТО, экспертные комиссии и передача</h1>
          <p className="muted">
            Протоколы ЭК, ЦЭК и ЭПК · историческая справка, предисловие к описи и акты НТО ·
            акты приёма-передачи дел на государственное хранение
          </p>
        </div>
      </header>

      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        {TABS.map((t) => (
          <button key={t.key} className={`btn small ${tab === t.key ? "primary" : ""}`}
                  onClick={() => { setTab(t.key); setError(""); }}>
            {t.label}
          </button>
        ))}
      </div>

      {error && <div className="alert error">{error}</div>}

      {meta && tab === "protocols" && <Protocols {...props} />}
      {meta && tab === "records" && <Records {...props} />}
      {meta && tab === "transfers" && <Transfers {...props} />}
    </div>
  );
}

// ---- Протоколы экспертных комиссий ----

const EMPTY_PROTOCOL = { commission: "ЭК", number: "", protocol_date: today(), agenda: "", note: "" };
const EMPTY_DECISION = { object_type: "inventory", object_id: "", decision: "approved", comment: "" };

function Attachments({ ownerType, ownerId, canEdit, onError }) {
  const [rows, setRows] = useState([]);
  const load = useCallback(() => {
    api.listAttachments(ownerType, ownerId).then(setRows).catch(() => setRows([]));
  }, [ownerType, ownerId]);
  useEffect(() => { load(); }, [load]);

  async function attach(file) {
    if (!file) return;
    onError("");
    try {
      await api.uploadAttachment(ownerType, ownerId, file);
      load();
    } catch (e) { onError(e.message); }
  }

  return (
    <>
      <ul className="muted" style={{ lineHeight: 1.8, margin: "4px 0" }}>
        {rows.map((a) => (
          <li key={a.id}>
            <a href="#" onClick={(e) => {
              e.preventDefault();
              api.downloadBlob(`/attachments/${a.id}/download`, a.filename)
                .catch((err) => onError(err.message));
            }}>{a.filename}</a> · {Math.round(a.size / 1024)} КБ · {a.uploaded_by}
          </li>
        ))}
        {rows.length === 0 && <li>файлов нет</li>}
      </ul>
      {canEdit && <input type="file" onChange={(e) => attach(e.target.files[0])} />}
    </>
  );
}

function Protocols({ meta, canEdit, isAdmin, onError }) {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState(null);
  const [open, setOpen] = useState(null);           // id развёрнутого протокола
  const [decision, setDecision] = useState(EMPTY_DECISION);
  const [objects, setObjects] = useState([]);

  const load = useCallback(() => {
    api.listProtocols().then(setRows).catch((e) => onError(e.message));
  }, [onError]);
  useEffect(() => { load(); }, [load]);
  const run = useRunner(load, onError);

  useEffect(() => {
    if (!open) return;
    setObjects([]);
    OBJECT_OPTIONS[decision.object_type]().then(setObjects).catch(() => setObjects([]));
  }, [open, decision.object_type]);

  const label = (list, key) => meta[list].find((x) => x.key === key)?.label || key;

  async function save(e) {
    e.preventDefault();
    const { id, ...payload } = form;
    if (await run(() => (id ? api.updateProtocol(id, payload) : api.createProtocol(payload)))) {
      setForm(null);
    }
  }

  async function addDecision(e) {
    e.preventDefault();
    if (await run(() => api.addProtocolDecision(open, decision))) {
      setDecision({ ...EMPTY_DECISION, object_type: decision.object_type });
    }
  }

  return (
    <>
      {canEdit && !form && (
        <button className="btn primary" style={{ marginBottom: 14 }}
                onClick={() => setForm(EMPTY_PROTOCOL)}>+ Протокол</button>
      )}

      {form && (
        <form className="card form" style={{ marginBottom: 18 }} onSubmit={save}>
          <div className="row3">
            <div>
              <label>Комиссия</label>
              <select value={form.commission} onChange={(e) => setForm({ ...form, commission: e.target.value })}>
                {meta.commissions.map((c) => <option key={c.key} value={c.key}>{c.key} — {c.label}</option>)}
              </select>
            </div>
            <div>
              <label>Номер протокола</label>
              <input value={form.number} required maxLength={64}
                     onChange={(e) => setForm({ ...form, number: e.target.value })} />
            </div>
            <div>
              <label>Дата заседания</label>
              <input type="date" value={form.protocol_date} required
                     onChange={(e) => setForm({ ...form, protocol_date: e.target.value })} />
            </div>
          </div>
          <label>Повестка: рассмотренные вопросы</label>
          <textarea rows={3} value={form.agenda}
                    onChange={(e) => setForm({ ...form, agenda: e.target.value })} />
          <label>Примечание</label>
          <input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
          <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
            <button className="btn primary">Сохранить</button>
            <button type="button" className="btn" onClick={() => setForm(null)}>Отмена</button>
          </div>
        </form>
      )}

      <table className="grid">
        <thead>
          <tr><th>Протокол</th><th>Повестка</th><th>Решений</th><th></th></tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <Fragment key={p.id}>
              <tr>
                <td>
                  <b>{protocolLabel(p)}</b>
                  <div className="muted small">{label("commissions", p.commission)}</div>
                </td>
                <td className="muted">{p.agenda || "—"}</td>
                <td className="num">{p.decisions.length}</td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <button className="btn small" onClick={() => setOpen(open === p.id ? null : p.id)}>
                    {open === p.id ? "Свернуть" : "Решения"}
                  </button>{" "}
                  {canEdit && (
                    <button className="icon-btn" title="Изменить" onClick={() => setForm({
                      id: p.id, commission: p.commission, number: p.number,
                      protocol_date: p.protocol_date, agenda: p.agenda, note: p.note,
                    })}>✏️</button>
                  )}
                  {isAdmin && p.decisions.length === 0 && (
                    <button className="icon-btn" title="Удалить" onClick={() => {
                      if (confirm(`Удалить протокол ${protocolLabel(p)}?`)) run(() => api.deleteProtocol(p.id));
                    }}>🗑</button>
                  )}
                </td>
              </tr>
              {open === p.id && (
                <tr>
                  <td colSpan={4}>
                    <table className="grid" style={{ margin: "6px 0 12px" }}>
                      <thead>
                        <tr><th>Объект</th><th>Решение</th><th>Комментарий</th>{isAdmin && <th></th>}</tr>
                      </thead>
                      <tbody>
                        {p.decisions.map((d) => (
                          <tr key={d.id}>
                            <td>
                              <div className="muted small">{label("objects", d.object_type)}</div>
                              {d.object_title}
                            </td>
                            <td>
                              <span className={`badge ${DECISION_CLASS[d.decision] || "b-gray"}`}>
                                {label("decisions", d.decision)}
                              </span>
                            </td>
                            <td className="muted">{d.comment || "—"}</td>
                            {isAdmin && (
                              <td>
                                <button className="icon-btn" title="Удалить решение" onClick={() => {
                                  if (confirm("Удалить решение? Статус описи и протокол в акте, внесённые им, останутся — их правят в карточке.")) {
                                    run(() => api.deleteProtocolDecision(p.id, d.id));
                                  }
                                }}>✕</button>
                              </td>
                            )}
                          </tr>
                        ))}
                        {p.decisions.length === 0 && (
                          <tr><td colSpan={isAdmin ? 4 : 3} className="muted" style={{ textAlign: "center" }}>
                            Решения не внесены.
                          </td></tr>
                        )}
                      </tbody>
                    </table>

                    {canEdit && (
                      <form onSubmit={addDecision}
                            style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
                        <div>
                          <label>Объект</label>
                          <select value={decision.object_type}
                                  onChange={(e) => setDecision({ ...decision, object_type: e.target.value, object_id: "" })}>
                            {meta.objects.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
                          </select>
                        </div>
                        <div style={{ flex: 1, minWidth: 240 }}>
                          <label>Какой</label>
                          <select value={decision.object_id} required
                                  onChange={(e) => setDecision({ ...decision, object_id: e.target.value })}>
                            <option value="">— выберите —</option>
                            {objects.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                          </select>
                        </div>
                        <div>
                          <label>Решение</label>
                          <select value={decision.decision}
                                  onChange={(e) => setDecision({ ...decision, decision: e.target.value })}>
                            {meta.decisions.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
                          </select>
                        </div>
                        <div style={{ flex: 1, minWidth: 160 }}>
                          <label>Комментарий</label>
                          <input value={decision.comment}
                                 onChange={(e) => setDecision({ ...decision, comment: e.target.value })} />
                        </div>
                        <button className="btn primary">Внести решение</button>
                      </form>
                    )}
                    <p className="muted small">
                      Решение по описи меняет её статус; положительное решение по проекту акта о
                      выделении к уничтожению вписывает в акт номер протокола.
                    </p>

                    <h4 style={{ margin: "12px 0 6px" }}>Скан подписанного протокола</h4>
                    <Attachments ownerType="commission_protocol" ownerId={p.id}
                                 canEdit={canEdit} onError={onError} />
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={4} className="muted" style={{ textAlign: "center", padding: 30 }}>
              Протоколов нет. Зарегистрируйте заседание комиссии и внесите решения по описям и актам.
            </td></tr>
          )}
        </tbody>
      </table>
    </>
  );
}

// ---- Документы НТО ----

function emptyRecord(kind) {
  return {
    kind, number: "", record_date: today(), title: "", fond: "",
    year_from: "", year_to: "", inventory_id: "", fields: {}, items: [],
  };
}

const EMPTY_ITEM = { case_index: "", title: "", years: "", note: "" };

function Records({ meta, canEdit, isAdmin, onError }) {
  const [rows, setRows] = useState([]);
  const [kind, setKind] = useState("");
  const [form, setForm] = useState(null);
  const [inventories, setInventories] = useState([]);
  const [fonds, setFonds] = useState([]);

  const load = useCallback(() => {
    api.listNtoRecords(kind).then(setRows).catch((e) => onError(e.message));
  }, [kind, onError]);
  useEffect(() => { load(); }, [load]);
  const run = useRunner(load, onError);

  const formOpen = Boolean(form);
  useEffect(() => {
    if (!formOpen) return;
    api.listInventories().then(setInventories).catch(() => {});
    api.dictionaryValues("fonds").then(setFonds).catch(() => {});
  }, [formOpen]);

  const spec = form ? meta.kinds.find((k) => k.key === form.kind) : null;
  const kindLabel = (key) => meta.kinds.find((k) => k.key === key)?.label || key;

  async function save(e) {
    e.preventDefault();
    const { id, ...rest } = form;
    const payload = {
      ...rest,
      year_from: rest.year_from ? Number(rest.year_from) : null,
      year_to: rest.year_to ? Number(rest.year_to) : null,
      inventory_id: rest.inventory_id || null,
      record_date: rest.record_date || null,
    };
    if (await run(() => (id ? api.updateNtoRecord(id, payload) : api.createNtoRecord(payload)))) {
      setForm(null);
    }
  }

  function setItem(i, patch) {
    setForm((f) => ({ ...f, items: f.items.map((x, j) => (j === i ? { ...x, ...patch } : x)) }));
  }

  return (
    <>
      <div className="card" style={{ marginBottom: 14, display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
        <div>
          <label>Вид документа</label>
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">все</option>
            {meta.kinds.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
          </select>
        </div>
        {canEdit && !form && (
          <button className="btn primary" onClick={() => setForm(emptyRecord(kind || meta.kinds[0].key))}>
            + Документ НТО
          </button>
        )}
      </div>

      {form && spec && (
        <form className="card form" style={{ marginBottom: 18 }} onSubmit={save}>
          <div className="row3">
            <div>
              <label>Вид</label>
              <select value={form.kind} disabled={Boolean(form.id)}
                      onChange={(e) => setForm({ ...emptyRecord(e.target.value), record_date: form.record_date })}>
                {meta.kinds.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
              </select>
            </div>
            <div>
              <label>Номер</label>
              <input value={form.number} placeholder="присвоится автоматически"
                     onChange={(e) => setForm({ ...form, number: e.target.value })} />
            </div>
            <div>
              <label>Дата</label>
              <input type="date" value={form.record_date}
                     onChange={(e) => setForm({ ...form, record_date: e.target.value })} />
            </div>
          </div>
          <label>Заголовок</label>
          <input value={form.title} placeholder="по умолчанию — по виду, фонду и годам"
                 onChange={(e) => setForm({ ...form, title: e.target.value })} />
          <div className="row3">
            <div>
              <label>Фонд</label>
              <input value={form.fond} list="nto-fonds"
                     onChange={(e) => setForm({ ...form, fond: e.target.value })} />
              <datalist id="nto-fonds">{fonds.map((f) => <option key={f} value={f} />)}</datalist>
            </div>
            <div>
              <label>С года</label>
              <input type="number" value={form.year_from}
                     onChange={(e) => setForm({ ...form, year_from: e.target.value })} />
            </div>
            <div>
              <label>По год</label>
              <input type="number" value={form.year_to}
                     onChange={(e) => setForm({ ...form, year_to: e.target.value })} />
            </div>
          </div>
          {spec.needs_inventory && (
            <>
              <label>Опись</label>
              <select value={form.inventory_id} required
                      onChange={(e) => setForm({ ...form, inventory_id: e.target.value })}>
                <option value="">— выберите опись —</option>
                {inventories.map((i) => (
                  <option key={i.id} value={i.id}>№ {i.number} · {i.title}</option>
                ))}
              </select>
            </>
          )}

          {spec.fields.map((f) => (
            <div key={f.key}>
              <label>{f.label}</label>
              <textarea rows={4} value={form.fields[f.key] || ""}
                        onChange={(e) => setForm({ ...form, fields: { ...form.fields, [f.key]: e.target.value } })} />
            </div>
          ))}

          {spec.has_items && (
            <>
              <label>Недостающие дела</label>
              {form.items.map((it, i) => (
                <div key={i} style={{ display: "flex", gap: 8, marginBottom: 6, flexWrap: "wrap" }}>
                  <input style={{ width: 110 }} placeholder="индекс" value={it.case_index}
                         onChange={(e) => setItem(i, { case_index: e.target.value })} />
                  <input style={{ flex: 1, minWidth: 200 }} placeholder="заголовок дела" required value={it.title}
                         onChange={(e) => setItem(i, { title: e.target.value })} />
                  <input style={{ width: 120 }} placeholder="крайние даты" value={it.years}
                         onChange={(e) => setItem(i, { years: e.target.value })} />
                  <input style={{ flex: 1, minWidth: 140 }} placeholder="примечание" value={it.note}
                         onChange={(e) => setItem(i, { note: e.target.value })} />
                  <button type="button" className="icon-btn" title="Убрать"
                          onClick={() => setForm({ ...form, items: form.items.filter((_, j) => j !== i) })}>✕</button>
                </div>
              ))}
              <button type="button" className="btn small"
                      onClick={() => setForm({ ...form, items: [...form.items, EMPTY_ITEM] })}>+ дело</button>
            </>
          )}

          <p className="muted small">
            Сведения, которые система ведёт сама — дела, описи, этапы работ, акты уничтожения, —
            форма возьмёт из базы при печати.
          </p>
          <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
            <button className="btn primary">Сохранить</button>
            <button type="button" className="btn" onClick={() => setForm(null)}>Отмена</button>
          </div>
        </form>
      )}

      <table className="grid">
        <thead>
          <tr><th>Номер</th><th>Вид</th><th>Заголовок</th><th>Дата</th><th>Статус</th><th></th></tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const draft = r.status === "Проект";
            return (
              <tr key={r.id}>
                <td><b>{r.number}</b></td>
                <td className="muted">{kindLabel(r.kind)}</td>
                <td>{r.title}</td>
                <td className="muted">{fmtD(r.record_date)}</td>
                <td><span className={`badge ${STATUS_CLASS[r.status] || "b-gray"}`}>{r.status}</span></td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <button className="btn small" onClick={() =>
                    api.downloadBlob(`/nto/records/${r.id}/form?fmt=pdf`, `${r.kind}_${r.number}.pdf`)
                      .catch((e) => onError(e.message))}>PDF</button>{" "}
                  {canEdit && draft && (
                    <button className="icon-btn" title="Изменить" onClick={() => setForm({
                      id: r.id, kind: r.kind, number: r.number, record_date: r.record_date,
                      title: r.title, fond: r.fond, year_from: r.year_from ?? "", year_to: r.year_to ?? "",
                      inventory_id: r.inventory_id || "", fields: r.fields || {}, items: r.items || [],
                    })}>✏️</button>
                  )}
                  {isAdmin && draft && (
                    <>
                      <button className="btn small" onClick={() => {
                        if (confirm(`Утвердить «${r.title}»? После утверждения документ не меняется.`)) {
                          run(() => api.approveNtoRecord(r.id));
                        }
                      }}>Утвердить</button>{" "}
                      <button className="icon-btn" title="Удалить" onClick={() => {
                        if (confirm("Удалить проект документа?")) run(() => api.deleteNtoRecord(r.id));
                      }}>🗑</button>
                    </>
                  )}
                </td>
              </tr>
            );
          })}
          {rows.length === 0 && (
            <tr><td colSpan={6} className="muted" style={{ textAlign: "center", padding: 30 }}>
              Документов НТО нет.
            </td></tr>
          )}
        </tbody>
      </table>
    </>
  );
}

// ---- Передача дел на государственное хранение ----

const EMPTY_TRANSFER = {
  number: "", act_date: today(), archive_name: "", fond: "", basis: "", note: "", case_ids: [],
};

function Transfers({ canEdit, isAdmin, onError }) {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState(null);
  const [cases, setCases] = useState([]);
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState(null);

  const load = useCallback(() => {
    api.listTransfers().then(setRows).catch((e) => onError(e.message));
  }, [onError]);
  useEffect(() => { load(); }, [load]);
  const run = useRunner(load, onError);

  const formOpen = Boolean(form);
  useEffect(() => {
    if (!formOpen) return;
    // Передаются только закрытые дела — сервер проверит это ещё раз.
    api.listCases().then((cs) => setCases(cs.filter((c) => c.status === "Закрыто"))).catch(() => {});
  }, [formOpen]);

  const needle = filter.trim().toLowerCase();
  const shown = cases.filter((c) => !needle || `${c.index} ${c.title} ${c.year}`.toLowerCase().includes(needle));

  function toggle(id) {
    setForm((f) => ({
      ...f,
      case_ids: f.case_ids.includes(id) ? f.case_ids.filter((x) => x !== id) : [...f.case_ids, id],
    }));
  }

  async function save(e) {
    e.preventDefault();
    const { id, ...payload } = form;
    if (await run(() => (id ? api.updateTransfer(id, payload) : api.createTransfer(payload)))) {
      setForm(null);
    }
  }

  return (
    <>
      {canEdit && !form && (
        <button className="btn primary" style={{ marginBottom: 14 }}
                onClick={() => setForm(EMPTY_TRANSFER)}>+ Акт приёма-передачи</button>
      )}

      {form && (
        <form className="card form" style={{ marginBottom: 18 }} onSubmit={save}>
          <div className="row3">
            <div>
              <label>Принимающий государственный архив</label>
              <input value={form.archive_name} required maxLength={512}
                     onChange={(e) => setForm({ ...form, archive_name: e.target.value })} />
            </div>
            <div>
              <label>Номер акта</label>
              <input value={form.number} placeholder="присвоится автоматически"
                     onChange={(e) => setForm({ ...form, number: e.target.value })} />
            </div>
            <div>
              <label>Дата акта</label>
              <input type="date" value={form.act_date}
                     onChange={(e) => setForm({ ...form, act_date: e.target.value })} />
            </div>
          </div>
          <div className="row2">
            <div>
              <label>Фонд</label>
              <input value={form.fond} onChange={(e) => setForm({ ...form, fond: e.target.value })} />
            </div>
            <div>
              <label>Основание</label>
              <input value={form.basis} placeholder="напр. график передачи документов"
                     onChange={(e) => setForm({ ...form, basis: e.target.value })} />
            </div>
          </div>
          <label>Примечание</label>
          <input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />

          <label>Дела к передаче · выбрано {form.case_ids.length}</label>
          <input value={filter} placeholder="поиск по индексу, заголовку, году"
                 onChange={(e) => setFilter(e.target.value)} />
          <div style={{ maxHeight: 320, overflow: "auto", marginTop: 8 }}>
            <table className="grid">
              <thead>
                <tr><th></th><th>Индекс</th><th>Заголовок</th><th>Год</th><th>Срок хранения</th></tr>
              </thead>
              <tbody>
                {shown.map((c) => (
                  <tr key={c.id} onClick={() => toggle(c.id)}>
                    <td><input type="checkbox" style={{ width: "auto" }} readOnly
                               checked={form.case_ids.includes(c.id)} /></td>
                    <td><b>{c.index || "—"}</b>{c.volume > 1 ? ` т.${c.volume}` : ""}</td>
                    <td>{c.title}</td>
                    <td className="muted">{c.year}</td>
                    <td className="muted">{c.permanent ? "Постоянно" : (c.retention_label || "—")}</td>
                  </tr>
                ))}
                {shown.length === 0 && (
                  <tr><td colSpan={5} className="muted" style={{ textAlign: "center", padding: 20 }}>
                    Закрытых дел не найдено.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
          <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
            <button className="btn primary">Сохранить</button>
            <button type="button" className="btn" onClick={() => setForm(null)}>Отмена</button>
          </div>
        </form>
      )}

      <table className="grid">
        <thead>
          <tr><th>Акт</th><th>Архив</th><th>Дел</th><th>Статус</th><th></th></tr>
        </thead>
        <tbody>
          {rows.map((a) => {
            const draft = a.status === "Проект";
            return (
              <Fragment key={a.id}>
                <tr>
                  <td><b>№ {a.number}</b><div className="muted small">от {fmtD(a.act_date)}</div></td>
                  <td>{a.archive_name}{a.fond && <div className="muted small">фонд {a.fond}</div>}</td>
                  <td className="num">{a.items.length}</td>
                  <td>
                    <span className={`badge ${STATUS_CLASS[a.status] || "b-gray"}`}>{a.status}</span>
                    {a.transferred_at && <div className="muted small">{fmtD(a.transferred_at)} · {a.transferred_by}</div>}
                  </td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    <button className="btn small" onClick={() => setOpen(open === a.id ? null : a.id)}>
                      {open === a.id ? "Свернуть" : "Состав"}
                    </button>{" "}
                    <button className="btn small" onClick={() =>
                      api.downloadBlob(`/nto/transfers/${a.id}/form?fmt=pdf`, `transfer_${a.number}.pdf`)
                        .catch((e) => onError(e.message))}>Акт PDF</button>{" "}
                    {canEdit && (
                      <button className="btn small" title="Акт и информационные пакеты всех дел"
                              onClick={() => api.downloadBlob(`/nto/transfers/${a.id}/package`, `transfer_${a.number}.zip`)
                                .catch((e) => onError(e.message))}>Пакет ZIP</button>
                    )}{" "}
                    {canEdit && draft && (
                      <button className="icon-btn" title="Изменить" onClick={() => setForm({
                        id: a.id, number: a.number, act_date: a.act_date, archive_name: a.archive_name,
                        fond: a.fond, basis: a.basis, note: a.note, case_ids: a.items.map((i) => i.case_id),
                      })}>✏️</button>
                    )}
                    {isAdmin && draft && (
                      <>
                        <button className="btn small primary" onClick={() => {
                          if (confirm(`Отметить передачу по акту № ${a.number}? Дела получат статус «Передано».`)) {
                            run(() => api.completeTransfer(a.id));
                          }
                        }}>Дела переданы</button>{" "}
                        <button className="icon-btn" title="Удалить" onClick={() => {
                          if (confirm("Удалить проект акта?")) run(() => api.deleteTransfer(a.id));
                        }}>🗑</button>
                      </>
                    )}
                  </td>
                </tr>
                {open === a.id && (
                  <tr>
                    <td colSpan={5}>
                      <table className="grid" style={{ margin: "6px 0 12px" }}>
                        <thead>
                          <tr><th>№</th><th>Индекс</th><th>Заголовок</th><th>Том</th><th>Год</th><th>Документов</th><th>Срок хранения</th></tr>
                        </thead>
                        <tbody>
                          {a.items.map((i) => (
                            <tr key={i.case_id}>
                              <td className="num">{i.order_no}</td>
                              <td><b>{i.case_index || "—"}</b></td>
                              <td>{i.case_title}</td>
                              <td className="num">{i.volume}</td>
                              <td className="muted">{i.year}</td>
                              <td className="num">{i.documents_count}</td>
                              <td className="muted">{i.retention || "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      <h4 style={{ margin: "12px 0 6px" }}>Скан подписанного акта</h4>
                      <Attachments ownerType="transfer_act" ownerId={a.id} canEdit={canEdit} onError={onError} />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
          {rows.length === 0 && (
            <tr><td colSpan={5} className="muted" style={{ textAlign: "center", padding: 30 }}>
              Актов приёма-передачи нет.
            </td></tr>
          )}
        </tbody>
      </table>
    </>
  );
}
