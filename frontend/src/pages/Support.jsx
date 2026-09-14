import { Fragment, useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";

const fmtTs = (t) => (t ? new Date(t).toLocaleString("ru-RU") : "—");
const isoToday = () => new Date().toISOString().slice(0, 10);
const monthStart = () => `${isoToday().slice(0, 8)}01`;
const pct = (v) => (v == null ? "нет данных" : `${String(v).replace(".", ",")} %`);
const money = (v) => Number(v).toLocaleString("ru-RU", { maximumFractionDigits: 2 });

const LEVEL_BADGE = { critical: "b-red", high: "b-amber", medium: "b-gray", low: "b-gray" };
const STATUS_BADGE = {
  "Новое": "b-amber",
  "В работе": "b-amber",
  "Решено": "b-green",
  "Возвращено на доработку": "b-red",
  "Закрыто": "b-gray",
};

// Обращения в поддержку, инциденты с SLA, инциденты ИБ и заявки на
// дополнительные услуги (ТС-176 разд. 13; разд. 14 п. 2.9, 2.10, 6.1, 9).
export default function Support() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const isStaff = isAdmin || user?.role === "auditor";
  const [tab, setTab] = useState("tickets");
  const [meta, setMeta] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.supportMeta().then(setMeta).catch((e) => setError(e.message));
  }, []);

  const tabs = [
    ["tickets", "Обращения"],
    ["new", "Новое обращение или заявка"],
    ...(isStaff ? [["sla", "SLA за период"]] : []),
  ];

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Обращения и SLA</h1>
          <p className="muted">
            Вопросы, инциденты, инциденты ИБ и заявки на дополнительные услуги ·
            сроки реакции и устранения (ТС-176 разд. 13)
          </p>
        </div>
      </header>

      {error && <div className="alert error">{error}</div>}

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {tabs.map(([key, label]) => (
          <button key={key} className={`btn small ${tab === key ? "primary" : ""}`}
                  onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>

      {meta && tab === "tickets" && <Tickets meta={meta} isAdmin={isAdmin} isStaff={isStaff} user={user} />}
      {meta && tab === "new" && <NewTicket meta={meta} onCreated={() => setTab("tickets")} />}
      {tab === "sla" && isStaff && <SlaReport />}
    </div>
  );
}

function NewTicket({ meta, onCreated }) {
  const [form, setForm] = useState({
    kind: "question", service: "", criticality: "medium", subject: "", body: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const isService = form.kind === "service_request";
  const level = meta.levels.find((l) => l.key === form.criticality);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.createTicket(form);
      onCreated();
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  }

  return (
    <form className="card form" onSubmit={submit}>
      {error && <div className="alert error">{error}</div>}
      <div className="row2">
        <div>
          <label>Вид обращения</label>
          <select value={form.kind}
                  onChange={(e) => setForm({ ...form, kind: e.target.value, service: "" })}>
            {meta.kinds.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
          </select>
        </div>
        {isService ? (
          <div>
            <label>Услуга</label>
            <select required value={form.service}
                    onChange={(e) => setForm({ ...form, service: e.target.value })}>
              <option value="">— выберите услугу —</option>
              {meta.services.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          </div>
        ) : (
          <div>
            <label>Уровень критичности</label>
            <select value={form.criticality}
                    onChange={(e) => setForm({ ...form, criticality: e.target.value })}>
              {meta.levels.map((l) => <option key={l.key} value={l.key}>{l.label}</option>)}
            </select>
          </div>
        )}
      </div>
      {!isService && level && (
        <div className="muted small">
          Реакция — до {level.reaction} мин, устранение — до {level.resolution / 60} ч
          {level.business_hours ? " в рабочее время" : " круглосуточно"}.
        </div>
      )}
      {form.kind === "security_incident" && (
        <div className="alert info" style={{ marginTop: 8 }}>
          Об инциденте ИБ ответственные будут уведомлены по электронной почте сразу после регистрации.
        </div>
      )}
      <label>Тема</label>
      <input required value={form.subject} placeholder="кратко о проблеме или услуге"
             onChange={(e) => setForm({ ...form, subject: e.target.value })} />
      <label>Описание</label>
      <textarea rows={5} value={form.body}
                placeholder={isService
                  ? "параметры услуги: например, пользователь и период для выписки из журнала"
                  : "что произошло, в каком разделе, что ожидалось"}
                onChange={(e) => setForm({ ...form, body: e.target.value })} />
      <div style={{ marginTop: 12 }}>
        <button className="btn primary" disabled={busy}>
          {busy ? "Регистрация…" : "Зарегистрировать"}
        </button>
      </div>
    </form>
  );
}

function Tickets({ meta, isAdmin, isStaff, user }) {
  const [scope, setScope] = useState(isStaff ? "all" : "mine");
  const [rows, setRows] = useState([]);
  const [open, setOpen] = useState(null);
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState("");

  const kinds = Object.fromEntries(meta.kinds.map((k) => [k.key, k.label]));
  const services = Object.fromEntries(meta.services.map((s) => [s.key, s.label]));
  const levels = Object.fromEntries(meta.levels.map((l) => [l.key, l.label]));

  const load = useCallback(
    () => api.listTickets(scope === "mine" ? { mine: true } : {})
      .then(setRows).catch((e) => setError(e.message)),
    [scope]
  );
  useEffect(() => { load(); }, [load]);

  async function run(action) {
    setError("");
    try {
      await action();
      setAnswer("");
      load();
    } catch (e) { setError(e.message); }
  }

  return (
    <div className="card">
      {isStaff && (
        <div style={{ marginBottom: 12 }}>
          <select value={scope} onChange={(e) => setScope(e.target.value)}>
            <option value="all">все обращения</option>
            <option value="mine">мои обращения</option>
          </select>
        </div>
      )}
      {error && <div className="alert error">{error}</div>}
      <table className="grid">
        <thead>
          <tr><th>Дата</th><th>Обращение</th><th>Критичность</th><th>Срок устранения</th><th>Статус</th></tr>
        </thead>
        <tbody>
          {rows.map((t) => (
            <Fragment key={t.id}>
              <tr style={{ cursor: "pointer" }} onClick={() => { setOpen(open === t.id ? null : t.id); setAnswer(""); }}>
                <td className="muted" style={{ whiteSpace: "nowrap" }}>{fmtTs(t.created_at)}</td>
                <td>
                  <b>{t.subject}</b>
                  <div className="muted small">
                    {kinds[t.kind] || t.kind}{t.service ? ` · ${services[t.service] || t.service}` : ""} · {t.user_email}
                  </div>
                </td>
                <td>
                  {t.kind === "service_request"
                    ? <span className="muted">—</span>
                    : <span className={`badge ${LEVEL_BADGE[t.criticality] || "b-gray"}`}>{levels[t.criticality] || t.criticality}</span>}
                </td>
                <td className="muted" style={{ whiteSpace: "nowrap" }}>
                  {t.resolution_due ? fmtTs(t.resolution_due) : "—"}
                  {t.overdue && <div><span className="badge b-red">просрочено</span></div>}
                </td>
                <td><span className={`badge ${STATUS_BADGE[t.status] || "b-gray"}`}>{t.status}</span></td>
              </tr>
              {open === t.id && (
                <tr>
                  <td colSpan={5}>
                    <div style={{ whiteSpace: "pre-wrap" }}>
                      {t.body || <span className="muted">без описания</span>}
                    </div>
                    {t.answer && (
                      <div className="annotation" style={{ marginTop: 8 }}>
                        <div className="annotation-label">Ответ{t.assignee ? ` · ${t.assignee}` : ""}</div>
                        <p style={{ whiteSpace: "pre-wrap" }}>{t.answer}</p>
                      </div>
                    )}
                    {t.kind !== "service_request" && (
                      <div className="muted small" style={{ marginTop: 6 }}>
                        Реакция: {fmtTs(t.reacted_at)} (срок {fmtTs(t.reaction_due)}) ·
                        решено: {fmtTs(t.resolved_at)}
                        {t.reopen_count ? ` · возвращалось на доработку: ${t.reopen_count}` : ""}
                      </div>
                    )}

                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
                      {isAdmin && ["Новое", "Возвращено на доработку"].includes(t.status) && (
                        <button className="btn small" onClick={() => run(() => api.takeTicket(t.id))}>
                          Взять в работу
                        </button>
                      )}
                      {t.user_email === user?.email && t.status === "Решено" && (
                        <>
                          <button className="btn small primary" onClick={() => run(() => api.closeTicket(t.id))}>
                            Принять решение
                          </button>
                          <button className="btn small"
                                  onClick={() => {
                                    const reason = prompt("Почему решение не устраивает?");
                                    if (reason !== null) run(() => api.reopenTicket(t.id, reason));
                                  }}>
                            Вернуть на доработку
                          </button>
                        </>
                      )}
                      {isAdmin && t.status !== "Закрыто" && t.user_email !== user?.email && (
                        <button className="btn small ghost" onClick={() => run(() => api.closeTicket(t.id))}>
                          Закрыть
                        </button>
                      )}
                    </div>

                    {isAdmin && t.status !== "Закрыто" && (
                      <div className="form" style={{ marginTop: 10 }}>
                        <textarea rows={3} value={answer} placeholder="ответ инициатору"
                                  onChange={(e) => setAnswer(e.target.value)} />
                        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                          <button className="btn small primary" disabled={!answer.trim()}
                                  onClick={() => run(() => api.answerTicket(t.id, { answer, resolve: true }))}>
                            Ответить и решить
                          </button>
                          <button className="btn small" disabled={!answer.trim()}
                                  onClick={() => run(() => api.answerTicket(t.id, { answer, resolve: false }))}>
                            Промежуточный ответ
                          </button>
                        </div>
                      </div>
                    )}
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={5} className="muted" style={{ textAlign: "center", padding: 30 }}>
              Обращений нет.
            </td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function SlaReport() {
  const [range, setRange] = useState({ date_from: monthStart(), date_to: isoToday(), amount: "" });
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  async function calculate() {
    setError("");
    try { setData(await api.slaReport(range)); } catch (e) { setError(e.message); }
  }
  useEffect(() => { calculate(); }, []);

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
        <div>
          <label>Сумма за отчётный период, ₸</label>
          <input type="number" min="0" value={range.amount} placeholder="для расчёта оплаты"
                 onChange={(e) => setRange({ ...range, amount: e.target.value })} />
        </div>
        <button className="btn primary" onClick={calculate}>Рассчитать</button>
      </div>
      {error && <div className="alert error">{error}</div>}

      {data && (
        <>
          <div className="kpi-row" style={{ marginBottom: 16 }}>
            <div className="card dash-card">
              <div className="kpi-val">{pct(data.availability.percent)}</div>
              <div className="kpi-lbl">доступность (цель {String(data.availability.target).replace(".", ",")} %)</div>
            </div>
            <div className="card dash-card">
              <div className="kpi-val">{pct(data.on_time.percent)}</div>
              <div className="kpi-lbl">устранено в срок (цель {data.on_time.target} %)</div>
            </div>
            <div className="card dash-card">
              <div className="kpi-val">{data.on_time.counted}</div>
              <div className="kpi-lbl">обращений в расчёте · ещё в сроке: {data.on_time.pending}</div>
            </div>
          </div>
          <p className="muted small">
            Минут в периоде: {data.availability.total_minutes}, из них доступно: {data.availability.available_minutes}.
            {data.availability.first_sample && ` Первая отметка доступности: ${fmtTs(data.availability.first_sample)} — период отчёта не должен начинаться раньше ввода в эксплуатацию.`}
          </p>

          <table className="grid">
            <thead><tr><th>Уровень критичности</th><th>Всего</th><th>В срок</th><th>С нарушением</th><th>Срок не наступил</th></tr></thead>
            <tbody>
              {data.by_level.map((l) => (
                <tr key={l.key}>
                  <td>{l.label}</td>
                  <td className="num">{l.total}</td>
                  <td className="num">{l.on_time}</td>
                  <td className="num">{l.late}</td>
                  <td className="num">{l.pending}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {data.payment && (
            <table className="grid" style={{ marginTop: 16 }}>
              <thead><tr><th colSpan={2}>Размер оплаты услуг (ТС-176 п. 13.1.3)</th></tr></thead>
              <tbody>
                <tr><td>Сумма за отчётный период</td><td className="num">{money(data.payment.amount)} ₸</td></tr>
                <tr><td>Уменьшение за доступность</td><td className="num">{money(data.payment.availability_deduction)} ₸</td></tr>
                <tr><td>Уменьшение за сроки устранения</td><td className="num">{money(data.payment.on_time_deduction)} ₸</td></tr>
                <tr><td><b>К оплате</b></td><td className="num"><b>{money(data.payment.payment)} ₸</b></td></tr>
              </tbody>
            </table>
          )}

          {data.late.length > 0 && (
            <>
              <h3>Устранены с нарушением срока</h3>
              <table className="grid">
                <thead><tr><th>Обращение</th><th>Срок</th><th>Решено</th></tr></thead>
                <tbody>
                  {data.late.map((t) => (
                    <tr key={t.id}>
                      <td>{t.subject}</td>
                      <td className="muted">{fmtTs(t.resolution_due)}</td>
                      <td className="muted">{t.resolved_at ? fmtTs(t.resolved_at) : "не решено"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </>
      )}
    </div>
  );
}
