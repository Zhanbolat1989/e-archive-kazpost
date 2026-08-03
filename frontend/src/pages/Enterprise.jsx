import { useEffect, useState, useCallback } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";

const EMPTY_ORG = {
  name: "", short_name: "", bin: "", address: "", phone: "", email: "",
  head_name: "", head_position: "",
};

export default function Enterprise() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [org, setOrg] = useState(EMPTY_ORG);
  const [departments, setDepartments] = useState([]);
  const [signers, setSigners] = useState([]);
  const [dep, setDep] = useState({ name: "", index: "", parent_id: "", head_name: "", head_position: "" });
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");

  const load = useCallback(() => {
    api.getOrganization().then((o) => o && setOrg({ ...EMPTY_ORG, ...o })).catch(() => {});
    api.listDepartments().then(setDepartments).catch((e) => setError(e.message));
    api.listSigners().then(setSigners).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  async function saveOrg(e) {
    e.preventDefault();
    setError(""); setSaved("");
    try {
      const { id, updated_at, ...payload } = org;
      await api.saveOrganization(payload);
      setSaved("Сведения об организации сохранены");
      load();
    } catch (e2) { setError(e2.message); }
  }

  async function addDepartment(e) {
    e.preventDefault();
    setError("");
    try {
      await api.createDepartment({ ...dep, parent_id: dep.parent_id || null });
      setDep({ name: "", index: "", parent_id: "", head_name: "", head_position: "" });
      setCreating(false);
      load();
    } catch (e2) { setError(e2.message); }
  }

  async function removeDepartment(id) {
    if (!confirm("Удалить подразделение?")) return;
    setError("");
    try {
      await api.deleteDepartment(id);
      load();
    } catch (e2) { setError(e2.message); }
  }

  // Отступ по уровню вложенности — оргструктура это дерево.
  const depth = (d, seen = 0) => {
    const parent = departments.find((x) => x.id === d.parent_id);
    return parent && seen < 6 ? depth(parent, seen + 1) : seen;
  };

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Предприятие</h1>
          <p className="muted">Сведения об организации, оргструктура и подписанты (п. 4.8 ТС)</p>
        </div>
      </header>

      {error && <div className="alert error">{error}</div>}
      {saved && <div className="alert success">{saved}</div>}

      <form className="card form" onSubmit={saveOrg} style={{ marginBottom: 18 }}>
        <h3 style={{ marginTop: 0 }}>Организация</h3>
        <div className="row2">
          <div>
            <label>Полное наименование</label>
            <input value={org.name} disabled={!isAdmin} required
              onChange={(e) => setOrg({ ...org, name: e.target.value })}
              placeholder="Акционерное общество «Казпочта»" />
          </div>
          <div>
            <label>БИН</label>
            <input value={org.bin} disabled={!isAdmin} maxLength={12}
              onChange={(e) => setOrg({ ...org, bin: e.target.value })} />
          </div>
        </div>
        <div className="row2">
          <div>
            <label>Краткое наименование</label>
            <input value={org.short_name} disabled={!isAdmin}
              onChange={(e) => setOrg({ ...org, short_name: e.target.value })} />
          </div>
          <div>
            <label>Телефон</label>
            <input value={org.phone} disabled={!isAdmin}
              onChange={(e) => setOrg({ ...org, phone: e.target.value })} />
          </div>
        </div>
        <label>Адрес</label>
        <input value={org.address} disabled={!isAdmin}
          onChange={(e) => setOrg({ ...org, address: e.target.value })} />
        <div className="row2">
          <div>
            <label>Руководитель</label>
            <input value={org.head_name} disabled={!isAdmin}
              onChange={(e) => setOrg({ ...org, head_name: e.target.value })} />
          </div>
          <div>
            <label>Должность руководителя</label>
            <input value={org.head_position} disabled={!isAdmin}
              onChange={(e) => setOrg({ ...org, head_position: e.target.value })} />
          </div>
        </div>
        {isAdmin && (
          <div style={{ marginTop: 14 }}>
            <button className="btn primary">Сохранить</button>
          </div>
        )}
      </form>

      <header className="page-head">
        <div>
          <h2 style={{ margin: 0 }}>Организационная структура</h2>
          <p className="muted">Подразделений: {departments.length}</p>
        </div>
        {isAdmin && (
          <button className="btn primary" onClick={() => setCreating(true)}>
            + Подразделение
          </button>
        )}
      </header>

      {creating && (
        <form className="card form" onSubmit={addDepartment} style={{ marginBottom: 18 }}>
          <div className="row3">
            <div>
              <label>Индекс</label>
              <input value={dep.index} onChange={(e) => setDep({ ...dep, index: e.target.value })}
                placeholder="01-02" />
            </div>
            <div>
              <label>Наименование</label>
              <input value={dep.name} required
                onChange={(e) => setDep({ ...dep, name: e.target.value })} />
            </div>
            <div>
              <label>Вышестоящее</label>
              <select value={dep.parent_id}
                onChange={(e) => setDep({ ...dep, parent_id: e.target.value })}>
                <option value="">— верхний уровень —</option>
                {departments.map((d) => (
                  <option key={d.id} value={d.id}>{d.index} {d.name}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="row2">
            <div>
              <label>Руководитель</label>
              <input value={dep.head_name}
                onChange={(e) => setDep({ ...dep, head_name: e.target.value })} />
            </div>
            <div>
              <label>Должность</label>
              <input value={dep.head_position}
                onChange={(e) => setDep({ ...dep, head_position: e.target.value })} />
            </div>
          </div>
          <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
            <button className="btn primary">Добавить</button>
            <button type="button" className="btn" onClick={() => setCreating(false)}>Отмена</button>
          </div>
        </form>
      )}

      <table className="grid" style={{ marginBottom: 22 }}>
        <thead>
          <tr>
            <th>Индекс</th>
            <th>Подразделение</th>
            <th>Руководитель</th>
            <th>Сотрудников</th>
            {isAdmin && <th></th>}
          </tr>
        </thead>
        <tbody>
          {departments.map((d) => (
            <tr key={d.id}>
              <td><b>{d.index || "—"}</b></td>
              <td style={{ paddingLeft: 16 + depth(d) * 22 }}>
                {depth(d) > 0 && <span className="muted">└ </span>}{d.name}
              </td>
              <td className="muted">
                {d.head_name || "—"}
                {d.head_position && <span className="small"> · {d.head_position}</span>}
              </td>
              <td>{d.users_count}</td>
              {isAdmin && (
                <td>
                  <button className="icon-btn" title="Удалить"
                    onClick={() => removeDepartment(d.id)}>🗑</button>
                </td>
              )}
            </tr>
          ))}
          {departments.length === 0 && (
            <tr><td colSpan={isAdmin ? 5 : 4} className="muted"
                    style={{ textAlign: "center", padding: 30 }}>
              Оргструктура не заполнена. Подразделения нужны для маршрутов согласования.
            </td></tr>
          )}
        </tbody>
      </table>

      <h2>Подписанты</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        Сотрудники с правом подписи документов архива
      </p>
      <table className="grid">
        <thead>
          <tr>
            <th>ФИО</th><th>Должность</th><th>Подразделение</th><th>Email</th>
          </tr>
        </thead>
        <tbody>
          {signers.map((s) => (
            <tr key={s.id}>
              <td><b>{s.full_name || "—"}</b></td>
              <td className="muted">{s.position || "—"}</td>
              <td className="muted">{s.department_name || "—"}</td>
              <td className="muted">{s.email}</td>
            </tr>
          ))}
          {signers.length === 0 && (
            <tr><td colSpan={4} className="muted" style={{ textAlign: "center", padding: 30 }}>
              Подписанты не назначены. Включите «право подписи» сотруднику в разделе «Безопасность».
            </td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
