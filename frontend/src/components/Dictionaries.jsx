import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";

// Редактируемые справочники (ТС-176 п. 4.9). Значения не удаляются, а
// выводятся из употребления: в заведённых записях они должны остаться.
export default function Dictionaries({ onError }) {
  const [rows, setRows] = useState([]);
  const [kind, setKind] = useState("");
  const [value, setValue] = useState("");

  const load = useCallback(() => {
    api.listDictionaries().then((list) => {
      setRows(list);
      setKind((k) => k || list[0]?.kind || "");
    }).catch((e) => onError(e.message));
  }, [onError]);
  useEffect(() => { load(); }, [load]);

  const current = rows.find((d) => d.kind === kind);
  const entries = current?.entries || [];

  async function run(action) {
    onError("");
    try {
      await action();
    } catch (e) {
      onError(e.message);
    }
    load();
  }

  function add(e) {
    e.preventDefault();
    const sortOrder = entries.reduce((m, x) => Math.max(m, x.sort_order), 0) + 1;
    run(async () => {
      await api.addDictionaryEntry(kind, { value, sort_order: sortOrder });
      setValue("");
    });
  }

  function rename(entry) {
    const next = prompt("Новое значение (в уже заведённых записях останется прежнее)", entry.value);
    if (next === null || next.trim() === entry.value) return;
    run(() => api.updateDictionaryEntry(entry.id, { value: next }));
  }

  // Порядок хранится номерами: после перестановки перенумеровываем то, что сдвинулось.
  function move(i, delta) {
    const order = [...entries];
    [order[i], order[i + delta]] = [order[i + delta], order[i]];
    run(() => Promise.all(order
      .map((x, j) => (x.sort_order === j + 1
        ? null
        : api.updateDictionaryEntry(x.id, { sort_order: j + 1 })))
      .filter(Boolean)));
  }

  return (
    <>
      <div className="card" style={{ marginBottom: 14 }}>
        <label>Справочник</label>
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          {rows.map((d) => <option key={d.kind} value={d.kind}>{d.label}</option>)}
        </select>
        {current && <p className="muted" style={{ marginBottom: 0 }}>{current.hint}</p>}
      </div>

      <form className="card form" onSubmit={add}
            style={{ marginBottom: 14, display: "flex", gap: 10, alignItems: "flex-end" }}>
        <div style={{ flex: 1 }}>
          <label>Новое значение</label>
          <input value={value} required maxLength={255}
                 onChange={(e) => setValue(e.target.value)} />
        </div>
        <button className="btn primary" disabled={!kind}>Добавить</button>
      </form>

      <table className="grid">
        <thead>
          <tr><th>№</th><th>Значение</th><th>Статус</th><th></th></tr>
        </thead>
        <tbody>
          {entries.map((x, i) => (
            <tr key={x.id}>
              <td className="muted">{i + 1}</td>
              <td className={x.is_active ? "" : "muted"}>{x.value}</td>
              <td>
                {x.is_active
                  ? <span className="badge b-green">действует</span>
                  : <span className="badge b-gray">не используется</span>}
              </td>
              <td style={{ whiteSpace: "nowrap" }}>
                <button className="icon-btn" title="Выше" disabled={i === 0}
                        onClick={() => move(i, -1)}>↑</button>
                <button className="icon-btn" title="Ниже" disabled={i === entries.length - 1}
                        onClick={() => move(i, 1)}>↓</button>
                <button className="icon-btn" title="Переименовать"
                        onClick={() => rename(x)}>✏️</button>
                <button className="btn small"
                        onClick={() => run(() => api.updateDictionaryEntry(x.id, { is_active: !x.is_active }))}>
                  {x.is_active ? "Вывести из употребления" : "Вернуть"}
                </button>
              </td>
            </tr>
          ))}
          {entries.length === 0 && (
            <tr><td colSpan={4} className="muted" style={{ textAlign: "center", padding: 30 }}>
              Справочник пуст{current?.strict ? " — при вводе принимается любое значение" : ""}.
            </td></tr>
          )}
        </tbody>
      </table>
    </>
  );
}
