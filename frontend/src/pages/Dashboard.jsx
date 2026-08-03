import { useEffect, useState } from "react";
import { api } from "../api.js";

const fmt = (n) => Math.round(n).toLocaleString("ru-RU");
const fmtM = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)} млн` : fmt(n));

const STATUS = {
  closed: ["Закрыто", "b-green"],
  partial: ["Частично", "b-amber"],
  unpaid: ["Не оплачено", "b-red"],
};

// Цвет по группе типа (валидированная палитра: CVD-разделение, хрома,
// контраст ≥3:1 на светлой поверхности). Идентичность несут подписи строк.
const GROUP_COLOR = {
  fin: "#0c9c6a",   // финансы и договоры
  hr: "#2563eb",    // кадры
  office: "#d9480f",// канцелярия
  other: "#94a3b8", // прочее (нейтральный «Other» — осознанно)
};
const TYPE_GROUP = {
  "Договор": "fin", "Счёт-фактура": "fin", "Акт": "fin", "Платёжное поручение": "fin",
  "Накладная": "fin", "Авансовый отчёт": "fin", "Бухгалтерская справка": "fin",
  "Налоговая отчётность": "fin", "Банковская выписка": "fin", "Смета": "fin",
  "Трудовой договор": "hr", "Кадровый приказ": "hr", "Заявление": "hr",
  "Личное дело": "hr", "Штатное расписание": "hr", "Табель учёта рабочего времени": "hr",
  "Справка": "hr",
  "Приказ": "office", "Распоряжение": "office", "Протокол": "office",
  "Служебная записка": "office", "Входящее письмо": "office",
  "Исходящее письмо": "office", "Положение": "office", "Письмо": "office",
  "Опись": "office",
};
const typeColor = (t) => GROUP_COLOR[TYPE_GROUP[t] || "other"];

export default function Dashboard() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.dashboard().then(setD).catch((e) => setErr(e.message));
  }, []);

  if (err) return <div className="page"><div className="alert error">{err}</div></div>;
  if (!d) return <div className="page muted">Загрузка…</div>;

  const paidPct = d.total_obligations > 0
    ? Math.round((d.total_paid / d.total_obligations) * 100) : 0;
  const maxType = Math.max(1, ...d.by_type.map((t) => t.count));
  const maxYear = Math.max(1, ...d.payments_by_year.map((y) => y.sum));
  const maxOb = Math.max(1, ...d.counterparties.map((c) => c.contracted));

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Дашборд</h1>
          <p className="muted">
            Сводка по архиву{d.period ? ` · ${d.period.from}–${d.period.to} гг.` : ""}
          </p>
        </div>
      </header>

      {/* KPI row */}
      <div className="kpi-row">
        <div className="kpi">
          <div className="kpi-val">{d.total_documents}</div>
          <div className="kpi-lbl">Документов в архиве</div>
        </div>
        <div className="kpi">
          <div className="kpi-val">{fmtM(d.total_obligations)} ₸</div>
          <div className="kpi-lbl">Обязательства</div>
        </div>
        <div className="kpi accent-green">
          <div className="kpi-val">{fmtM(d.total_paid)} ₸</div>
          <div className="kpi-lbl">Оплачено · {paidPct}%</div>
        </div>
        <div className="kpi accent-coral">
          <div className="kpi-val">{fmtM(d.total_remaining)} ₸</div>
          <div className="kpi-lbl">Остаток к оплате</div>
        </div>
      </div>

      <div className="dash-grid">
        {/* Obligations vs paid */}
        <div className="card dash-card wide">
          <h3>Обязательства vs оплачено</h3>
          <div className="cp-list">
            {d.counterparties.map((c) => {
              // Единая шкала (доля от максимального обязательства): заливка —
              // оплачено, светлый фон — обязательство. Сравнимо между строками.
              const paidW = Math.min(100, (c.paid / maxOb) * 100);
              const obW = Math.min(100, (c.contracted / maxOb) * 100);
              const pct = c.contracted > 0 ? Math.round((c.paid / c.contracted) * 100) : 0;
              const [label, cls] = STATUS[c.status];
              return (
                <div className="cp-row" key={c.name}>
                  <div className="cp-head">
                    <span className="cp-name" title={c.name}>{c.name}</span>
                    <span className={`badge ${cls}`}>{label}</span>
                  </div>
                  <div className="cp-bar-track" style={{ position: "relative" }}>
                    <div className="cp-bar-ghost" style={{ width: `${obW}%` }} />
                    <div className="cp-bar" style={{ width: `${paidW}%` }} />
                  </div>
                  <div className="cp-meta muted">
                    {fmt(c.paid)} / {fmt(c.contracted)} ₸ · {pct}%
                    {c.remaining > 0 && <span> · остаток {fmt(c.remaining)} ₸</span>}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* By type */}
        <div className="card dash-card">
          <h3>По типам документов</h3>
          <div className="bar-list">
            {d.by_type.map((t) => (
              <div className="bar-row" key={t.type}>
                <span className="bar-lbl">{t.type}</span>
                <div className="bar-track">
                  <div className="bar-fill" style={{
                    width: `${(t.count / maxType) * 100}%`,
                    background: typeColor(t.type),
                  }} />
                </div>
                <span className="bar-num">{t.count}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Retention */}
        <div className="card dash-card">
          <h3>⏳ Сроки хранения</h3>
          {d.retention && (d.retention.expired_count > 0 || d.retention.expiring_count > 0) ? (
            <>
              {d.retention.expired_count > 0 && (
                <div className="alert error" style={{ margin: "0 0 10px" }}>
                  Истёк срок: {d.retention.expired_count} док. — подготовьте акт о выделении к уничтожению
                </div>
              )}
              {d.retention.expired.map((r) => (
                <div className="ret-row" key={r.id}>
                  <span>{r.title}</span>
                  <span className="ret-date">{new Date(r.retention_until).toLocaleDateString("ru-RU")}</span>
                </div>
              ))}
              {d.retention.expiring.map((r) => (
                <div className="ret-row" key={r.id}>
                  <span>{r.title}</span>
                  <span className="ret-date soon">{new Date(r.retention_until).toLocaleDateString("ru-RU")}</span>
                </div>
              ))}
            </>
          ) : (
            <p className="muted">Истёкших и истекающих в ближайший год сроков нет.</p>
          )}
        </div>

        {/* Payments by year */}
        <div className="card dash-card">
          <h3>Оплата по годам</h3>
          <div className="col-chart">
            {d.payments_by_year.length === 0 && <div className="muted">Нет платежей</div>}
            {d.payments_by_year.map((y) => (
              <div className="col-item" key={y.year}>
                <div className="col-val">{fmtM(y.sum)}</div>
                <div className="col-bar" style={{ height: `${Math.max(6, (y.sum / maxYear) * 130)}px` }} />
                <div className="col-lbl">{y.year}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
