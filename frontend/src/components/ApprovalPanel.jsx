import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";

// Согласование объекта (ТС-176 п. 4.10): история маршрутов и отправка на
// согласование по шаблону оргструктуры с предпросмотром согласующих.
const STATUS_CLASS = {
  "На согласовании": "b-amber",
  "Согласовано": "b-green",
  "Отклонено": "b-red",
};

const fmtTs = (t) => (t ? new Date(t).toLocaleString("ru-RU") : "");

function StepList({ steps }) {
  return (
    <ol className="small" style={{ margin: "6px 0 0", paddingLeft: 20 }}>
      {steps.map((s) => (
        <li key={s.id || s.order_no}>
          <b>{s.approver_name || s.approver_email}</b>
          {s.basis && <span className="muted"> · {s.basis}</span>}
          {s.status && (
            <>
              {" — "}
              <span className={`badge ${STATUS_CLASS[s.status] || "b-gray"}`}>{s.status}</span>
              {s.decided_at && <span className="muted"> {fmtTs(s.decided_at)}</span>}
            </>
          )}
          {s.comment && <div className="muted">«{s.comment}»</div>}
        </li>
      ))}
    </ol>
  );
}

export default function ApprovalPanel({ objectType, objectId, canStart, onStarted }) {
  const [routes, setRoutes] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [templateId, setTemplateId] = useState("");
  const [plan, setPlan] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // Предпросмотр по шаблону, выбранному раньше, не должен перезаписать текущий.
  const latest = useRef("");

  const load = useCallback(() => {
    api.listApprovals(objectType, objectId).then(setRoutes).catch((e) => setError(e.message));
  }, [objectType, objectId]);

  useEffect(() => {
    setTemplateId("");
    setPlan(null);
    setError("");
    load();
  }, [load]);

  useEffect(() => {
    if (canStart) api.listRouteTemplates(objectType).then(setTemplates).catch(() => {});
  }, [canStart, objectType]);

  const pending = routes.some((r) => r.status === "На согласовании");

  async function preview(id) {
    latest.current = id;
    setTemplateId(id);
    setPlan(null);
    setError("");
    if (!id) return;
    try {
      const steps = await api.previewApproval({
        object_type: objectType, object_id: objectId, template_id: id,
      });
      if (latest.current === id) setPlan(steps);
    } catch (e) {
      if (latest.current === id) setError(e.message);
    }
  }

  async function start() {
    setBusy(true);
    setError("");
    try {
      await api.createApproval({
        object_type: objectType, object_id: objectId, template_id: templateId,
      });
      latest.current = "";
      setTemplateId("");
      setPlan(null);
      load();
      onStarted?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (!canStart && routes.length === 0) return null;

  return (
    <div className="annotation">
      <div className="annotation-label">📝 Согласование</div>

      {routes.map((r) => (
        <div key={r.id} style={{ margin: "6px 0 10px" }}>
          <span className={`badge ${STATUS_CLASS[r.status] || "b-gray"}`}>{r.status}</span>
          <span className="muted small">
            {" "}{r.template_name ? `по шаблону «${r.template_name}» · ` : ""}
            {r.created_by} · {fmtTs(r.created_at)}
          </span>
          <StepList steps={r.steps} />
        </div>
      ))}

      {canStart && !pending && (templates.length === 0 ? (
        <p className="muted small" style={{ margin: "4px 0" }}>
          Шаблонов маршрутов нет — администратор настраивает их в разделе «Предприятие».
        </p>
      ) : (
        <div style={{ marginTop: 6 }}>
          <select value={templateId} onChange={(e) => preview(e.target.value)}>
            <option value="">Отправить на согласование по шаблону…</option>
            {templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          {plan && (
            <>
              <div className="muted small" style={{ marginTop: 8 }}>Маршрут пройдёт по порядку:</div>
              <StepList steps={plan} />
              <button className="btn small primary" style={{ marginTop: 8 }}
                      disabled={busy} onClick={start}>
                {busy ? "Отправка…" : "Отправить на согласование"}
              </button>
            </>
          )}
        </div>
      ))}

      {error && <div className="alert error" style={{ marginTop: 8 }}>{error}</div>}
    </div>
  );
}
