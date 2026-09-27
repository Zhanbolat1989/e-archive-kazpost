import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";

const FALLBACK_TYPES = [
  { group: "Основные", types: ["Договор", "Счёт-фактура", "Акт", "Приказ", "Прочее"] },
];

export default function Upload() {
  const navigate = useNavigate();
  const [file, setFile] = useState(null);
  const [meta, setMeta] = useState({
    title: "", description: "", fond: "", opis: "", delo: "",
    doc_type: "Прочее", doc_number: "", counterparty: "", doc_date: "", amount: "",
    case_id: "", cadastral_number: "", real_estate_address: "", real_estate_area: "",
    department_id: "", is_copy: false,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [drag, setDrag] = useState(false);
  const [typeGroups, setTypeGroups] = useState(FALLBACK_TYPES);
  const [cases, setCases] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [fonds, setFonds] = useState([]);
  const inputRef = useRef();

  useEffect(() => {
    api.documentTypes().then(setTypeGroups).catch(() => {});
    api.listCases().then((cs) => setCases(cs.filter((c) => c.status === "Формируется"))).catch(() => {});
    api.listDepartments().then(setDepartments).catch(() => {});
    // Справочник фондов (ТС-176 п. 4.9) — подсказки, ввод остаётся свободным.
    api.dictionaryValues("fonds").then(setFonds).catch(() => {});
  }, []);

  const isRealEstate = typeGroups
    .find((g) => g.group === "Недвижимость")?.types.includes(meta.doc_type) ?? false;

  function pick(f) {
    if (!f) return;
    setFile(f);
    setMeta((m) => ({ ...m, title: m.title || f.name }));
  }

  async function submit(e) {
    e.preventDefault();
    if (!file) {
      setError("Выберите файл");
      return;
    }
    setError("");
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      Object.entries(meta).forEach(([k, v]) => fd.append(k, v));
      await api.uploadDocument(fd);
      navigate("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page narrow">
      <header className="page-head">
        <div>
          <h1>Приём документа</h1>
          <p className="muted">Файл проходит антивирус → WORM-хранение → OCR → индексацию</p>
        </div>
      </header>

      <form onSubmit={submit} className="card form">
        <div
          className={`dropzone ${drag ? "over" : ""} ${file ? "filled" : ""}`}
          onClick={() => inputRef.current.click()}
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files[0]); }}
        >
          <input
            ref={inputRef}
            type="file"
            hidden
            onChange={(e) => pick(e.target.files[0])}
          />
          {file ? (
            <div>
              <div className="dz-icon">📄</div>
              <div className="dz-name">{file.name}</div>
              <div className="muted">{(file.size / 1024).toFixed(1)} КБ · нажмите, чтобы заменить</div>
            </div>
          ) : (
            <div>
              <div className="dz-icon">⬆️</div>
              <div>Перетащите файл сюда или нажмите для выбора</div>
              <div className="muted">PDF, изображения (скан), текст</div>
            </div>
          )}
        </div>

        <label>Наименование</label>
        <input value={meta.title} onChange={(e) => setMeta({ ...meta, title: e.target.value })} required />

        <div className="row3">
          <div>
            <label>Тип документа</label>
            <select value={meta.doc_type} onChange={(e) => setMeta({ ...meta, doc_type: e.target.value })}>
              {typeGroups.map((g) => (
                <optgroup key={g.group} label={g.group}>
                  {g.types.map((t) => <option key={t} value={t}>{t}</option>)}
                </optgroup>
              ))}
            </select>
          </div>
          <div>
            <label>Номер</label>
            <input value={meta.doc_number} onChange={(e) => setMeta({ ...meta, doc_number: e.target.value })} placeholder="№ с оригинала (для приказов и т.п. — автоматически)" />
          </div>
          <div>
            <label>Дата документа</label>
            <input type="date" value={meta.doc_date} onChange={(e) => setMeta({ ...meta, doc_date: e.target.value })} />
          </div>
        </div>

        <div className="row2">
          <div>
            <label>Контрагент</label>
            <input value={meta.counterparty} onChange={(e) => setMeta({ ...meta, counterparty: e.target.value })} placeholder="ТОО «…»" />
          </div>
          <div>
            <label>Сумма, ₸</label>
            <input type="number" value={meta.amount} onChange={(e) => setMeta({ ...meta, amount: e.target.value })} placeholder="0" />
          </div>
        </div>

        {isRealEstate && (
          <div className="card" style={{ background: "#f8fafc", padding: 14, margin: "6px 0 14px" }}>
            <div className="muted small" style={{ marginBottom: 8 }}>
              Объект недвижимости (правовой кадастр РК)
            </div>
            <div className="row3">
              <div>
                <label>Кадастровый номер</label>
                <input value={meta.cadastral_number} onChange={(e) => setMeta({ ...meta, cadastral_number: e.target.value })} placeholder="напр. 20:312:001:001" />
              </div>
              <div>
                <label>Адрес объекта</label>
                <input value={meta.real_estate_address} onChange={(e) => setMeta({ ...meta, real_estate_address: e.target.value })} placeholder="г. Астана, ул. …" />
              </div>
              <div>
                <label>Площадь, м²</label>
                <input type="number" value={meta.real_estate_area} onChange={(e) => setMeta({ ...meta, real_estate_area: e.target.value })} placeholder="0" />
              </div>
            </div>
            <div className="muted small">Поле «Контрагент» выше используется как текущий правообладатель.</div>
          </div>
        )}

        {/* Подразделение — атрибут индексирования */}
        <label>Подразделение</label>
        <select value={meta.department_id}
                onChange={(e) => setMeta({ ...meta, department_id: e.target.value })}>
          <option value="">— не указано —</option>
          {departments.map((d) => (
            <option key={d.id} value={d.id}>{d.index ? `${d.index} · ` : ""}{d.name}</option>
          ))}
        </select>

        <label>Дело (единица хранения)</label>
        <select value={meta.case_id} onChange={(e) => setMeta({ ...meta, case_id: e.target.value })}>
          <option value="">— без дела (срок по типу документа) —</option>
          {cases.map((c) => (
            <option key={c.id} value={c.id}>
              {c.index ? `${c.index} · ` : ""}{c.title} ({c.year}{c.retention_label ? ` · ${c.retention_label}` : ""})
            </option>
          ))}
        </select>

        {/* ТС-176 п. 11.6: скан бумажного документа — электронная копия; такие
            копии учитываются отдельной описью и сверяются с подлинником. */}
        <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12 }}>
          <input type="checkbox" style={{ width: "auto" }} checked={meta.is_copy}
                 onChange={(e) => setMeta({ ...meta, is_copy: e.target.checked })} />
          Электронная копия бумажного документа (скан без ЭЦП автора)
        </label>

        <label>Описание</label>
        <textarea value={meta.description} onChange={(e) => setMeta({ ...meta, description: e.target.value })} rows={2} />

        <div className="row3">
          <div>
            <label>Фонд</label>
            <input value={meta.fond} list="fonds-dictionary"
              onChange={(e) => setMeta({ ...meta, fond: e.target.value })} placeholder="Ф-1" />
            <datalist id="fonds-dictionary">
              {fonds.map((f) => <option key={f} value={f} />)}
            </datalist>
          </div>
          <div>
            <label>Опись</label>
            <input value={meta.opis} onChange={(e) => setMeta({ ...meta, opis: e.target.value })} placeholder="Оп-2" />
          </div>
          <div>
            <label>Дело</label>
            <input value={meta.delo} onChange={(e) => setMeta({ ...meta, delo: e.target.value })} placeholder="Д-15" />
          </div>
        </div>

        {error && <div className="alert error">{error}</div>}
        <button className="btn primary block" disabled={busy}>
          {busy ? "Загрузка…" : "Принять в архив"}
        </button>
      </form>
    </div>
  );
}
