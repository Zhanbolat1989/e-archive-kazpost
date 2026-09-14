import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";

// Шаблоны маршрутов согласования по оргструктуре (ТС-176 п. 4.10): шаги
// задаются позициями, согласующие подставляются при отправке.
const NEW_STEP = { kind: "head", value: "" };
const EMPTY = { name: "", object_type: "", steps: [NEW_STEP], is_active: true };

export default function RouteTemplates({ isAdmin, departments, users }) {
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState({ step_kinds: [], object_types: [] });
  const [form, setForm] = useState(null); // шаблон в редактировании; с id — существующий
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api.listRouteTemplates("", isAdmin).then(setRows).catch((e) => setError(e.message));
  }, [isAdmin]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.approvalsMeta().then(setMeta).catch(() => {}); }, []);

  const label = (list, key) => list.find((x) => x.key === key)?.label || key;

  function describe(step) {
    if (step.kind === "department_head") {
      const dep = departments.find((d) => d.id === step.value);
      return `Руководитель: ${dep ? dep.name : "подразделение удалено"}`;
    }
    if (step.kind === "user") {
      const u = users.find((x) => x.email === step.value);
      return u?.full_name || step.value;
    }
    return label(meta.step_kinds, step.kind);
  }

  function setStep(i, patch) {
    setForm((f) => ({ ...f, steps: f.steps.map((s, j) => (j === i ? { ...s, ...patch } : s)) }));
  }

  function moveStep(i, delta) {
    setForm((f) => {
      const steps = [...f.steps];
      [steps[i], steps[i + delta]] = [steps[i + delta], steps[i]];
      return { ...f, steps };
    });
  }

  async function save(e) {
    e.preventDefault();
    setError("");
    const { id, ...payload } = form;
    try {
      if (id) await api.updateRouteTemplate(id, payload);
      else await api.createRouteTemplate(payload);
      setForm(null);
      load();
    } catch (e2) { setError(e2.message); }
  }

  async function remove(t) {
    if (!confirm(`Удалить шаблон «${t.name}»? Запущенные по нему маршруты сохранятся.`)) return;
    setError("");
    try {
      await api.deleteRouteTemplate(t.id);
      load();
    } catch (e) { setError(e.message); }
  }

  return (
    <>
      <header className="page-head">
        <div>
          <h2 style={{ margin: 0 }}>Шаблоны маршрутов согласования</h2>
          <p className="muted">
            Шаги — позиции оргструктуры; согласующие подставляются при отправке (п. 4.10 ТС)
          </p>
        </div>
        {isAdmin && !form && (
          <button className="btn primary" onClick={() => setForm(EMPTY)}>+ Шаблон</button>
        )}
      </header>

      {error && <div className="alert error">{error}</div>}

      {form && (
        <form className="card form" onSubmit={save} style={{ marginBottom: 18 }}>
          <div className="row2">
            <div>
              <label>Название</label>
              <input value={form.name} required maxLength={255}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Согласование номенклатуры дел" />
            </div>
            <div>
              <label>Для объектов</label>
              <select value={form.object_type}
                onChange={(e) => setForm({ ...form, object_type: e.target.value })}>
                {meta.object_types.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
              </select>
            </div>
          </div>

          <label>Шаги по порядку</label>
          {form.steps.map((s, i) => (
            <div key={i} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6, flexWrap: "wrap" }}>
              <span className="muted">{i + 1}.</span>
              <select value={s.kind} style={{ width: "auto" }}
                onChange={(e) => setStep(i, { kind: e.target.value, value: "" })}>
                {meta.step_kinds.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
              </select>
              {s.kind === "department_head" && (
                <select value={s.value} required style={{ width: "auto" }}
                  onChange={(e) => setStep(i, { value: e.target.value })}>
                  <option value="">— подразделение —</option>
                  {departments.map((d) => (
                    <option key={d.id} value={d.id}>{d.index} {d.name}</option>
                  ))}
                </select>
              )}
              {s.kind === "user" && (
                <select value={s.value} required style={{ width: "auto" }}
                  onChange={(e) => setStep(i, { value: e.target.value })}>
                  <option value="">— сотрудник —</option>
                  {users.filter((u) => u.is_active).map((u) => (
                    <option key={u.id} value={u.email}>{u.full_name || u.email}</option>
                  ))}
                </select>
              )}
              <button type="button" className="icon-btn" title="Выше"
                disabled={i === 0} onClick={() => moveStep(i, -1)}>↑</button>
              <button type="button" className="icon-btn" title="Ниже"
                disabled={i === form.steps.length - 1} onClick={() => moveStep(i, 1)}>↓</button>
              <button type="button" className="icon-btn" title="Убрать шаг"
                disabled={form.steps.length === 1}
                onClick={() => setForm({ ...form, steps: form.steps.filter((_, j) => j !== i) })}>✕</button>
            </div>
          ))}
          <button type="button" className="btn small"
            onClick={() => setForm({ ...form, steps: [...form.steps, NEW_STEP] })}>
            + шаг
          </button>

          <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12 }}>
            <input type="checkbox" style={{ width: "auto" }} checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
            Шаблон действует
          </label>
          <p className="muted small">
            Руководитель подразделения определяется по подразделению объекта, а если оно
            не указано — по подразделению отправителя. Шаг, где согласующим оказался бы
            сам отправитель или тот, кто уже есть в маршруте, пропускается.
          </p>
          <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
            <button className="btn primary">Сохранить</button>
            <button type="button" className="btn" onClick={() => setForm(null)}>Отмена</button>
          </div>
        </form>
      )}

      <table className="grid" style={{ marginBottom: 22 }}>
        <thead>
          <tr>
            <th>Шаблон</th>
            <th>Объекты</th>
            <th>Маршрут</th>
            {isAdmin && <th></th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((t) => (
            <tr key={t.id}>
              <td>
                <b>{t.name}</b>
                {!t.is_active && <span className="badge b-gray" style={{ marginLeft: 6 }}>отключён</span>}
              </td>
              <td className="muted">{label(meta.object_types, t.object_type)}</td>
              <td className="muted small">{t.steps.map(describe).join(" → ")}</td>
              {isAdmin && (
                <td style={{ whiteSpace: "nowrap" }}>
                  <button className="icon-btn" title="Изменить"
                    onClick={() => setForm({
                      id: t.id, name: t.name, object_type: t.object_type,
                      steps: t.steps, is_active: t.is_active,
                    })}>✏️</button>
                  <button className="icon-btn" title="Удалить" onClick={() => remove(t)}>🗑</button>
                </td>
              )}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={isAdmin ? 4 : 3} className="muted" style={{ textAlign: "center", padding: 30 }}>
              Шаблонов нет. Назначьте руководителей подразделений и добавьте шаблон —
              документы, дела и номенклатура станут отправляться на согласование по нему.
            </td></tr>
          )}
        </tbody>
      </table>
    </>
  );
}
