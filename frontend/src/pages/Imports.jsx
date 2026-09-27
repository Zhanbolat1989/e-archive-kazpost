import { useEffect, useState, useCallback, useRef } from "react";
import { api } from "../api.js";

// Модуль импорта и восстановление из резервной копии.
const STATUS_CLASS = {
  "В обработке": "b-amber",
  "Загружен": "b-green",
  "Загружен с ошибками": "b-amber",
  "Ошибка": "b-red",
};

export default function Imports() {
  const [jobs, setJobs] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);

  const load = useCallback(() => {
    api.listImports().then(setJobs).catch((e) => setError(e.message));
  }, []);

  useEffect(() => { load(); }, [load]);

  // Пока пакет разбирается, обновляем список: загрузка идёт в фоне и может
  // занимать часы — пользователь должен видеть ход, не нажимая «обновить».
  useEffect(() => {
    if (!jobs.some((j) => j.status === "В обработке")) return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [jobs, load]);

  async function upload(file) {
    if (!file) return;
    setError("");
    setBusy(true);
    try {
      await api.uploadImport(file);
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Импорт и восстановление</h1>
          <p className="muted">
            Загрузка пакетов оцифровки (ZIP + manifest.xml) и восстановление архива
            из резервной копии
          </p>
        </div>
        <button className="btn"
                onClick={() => api.downloadBlob("/export/package.zip", "earchive_backup.zip")
                  .catch((e) => setError(e.message))}>
          Выгрузить резервную копию
        </button>
      </header>

      {error && <div className="alert error">{error}</div>}

      <div className="card" style={{ marginBottom: 18 }}>
        <h3 style={{ marginTop: 0 }}>Загрузить пакет</h3>
        <p className="muted">
          Пакет содержит manifest.xml с описанием дел и документов и сами файлы.
          Документы, уже принятые в архив, повторно не заводятся — они
          учитываются в отчёте как пропущенные дубли. После разбора пакета каждый
          документ проходит обычный приём: антивирус, распознавание, индексация.
        </p>
        <input ref={fileRef} type="file" accept=".zip"
               disabled={busy}
               onChange={(e) => upload(e.target.files[0])} />
        {busy && <span className="muted"> Проверка пакета…</span>}
      </div>

      <table className="grid">
        <thead>
          <tr>
            <th>Пакет</th><th>Загружен</th><th>Статус</th>
            <th>Документов</th><th>Дел</th><th>Дубли</th><th>Ошибки</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.id}>
              <td>
                <div className="doc-title">{j.filename}</div>
                <div className="doc-file muted">{j.created_by}</div>
              </td>
              <td className="muted">{new Date(j.created_at).toLocaleString("ru-RU")}</td>
              <td><span className={`badge ${STATUS_CLASS[j.status] || ""}`}>{j.status}</span></td>
              <td className="num">{j.created_documents} из {j.total}</td>
              <td className="num">{j.created_cases}</td>
              <td className="num">{j.skipped_duplicates}</td>
              <td className="muted">
                {j.errors.length === 0 ? "—" : (
                  <details>
                    <summary>{j.errors.length}</summary>
                    <ul style={{ lineHeight: 1.6 }}>
                      {j.errors.slice(0, 50).map((e, i) => <li key={i}>{e}</li>)}
                    </ul>
                  </details>
                )}
              </td>
            </tr>
          ))}
          {jobs.length === 0 && (
            <tr><td colSpan={7} className="muted" style={{ textAlign: "center", padding: 30 }}>
              Пакеты пока не загружались.
            </td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
