import { useState, useEffect } from "react";
import { api } from "../api.js";
import { signCms } from "../ncalayer.js";
import { StatusBadge, SignatureBadge } from "./StatusBadge.jsx";

function b64(bytes) {
  let binary = "";
  bytes.forEach((b) => (binary += String.fromCharCode(b)));
  return btoa(binary);
}

const fmtD = (d) => (d ? new Date(d).toLocaleDateString("ru-RU") : "—");

export default function DocumentModal({ doc, onClose, onChanged, canDelete, onOpenDocument }) {
  const [sig, setSig] = useState(null);
  const [signing, setSigning] = useState(false);
  const [sigError, setSigError] = useState("");
  const [history, setHistory] = useState(null);
  const [supersedeOpen, setSupersedeOpen] = useState(false);
  const [supersedeFile, setSupersedeFile] = useState(null);
  const [supersedeForm, setSupersedeForm] = useState({
    counterparty: "", doc_number: "", doc_date: "",
    cadastral_number: "", real_estate_address: "", real_estate_area: "",
  });
  const [supersedeBusy, setSupersedeBusy] = useState(false);
  const [supersedeError, setSupersedeError] = useState("");
  const [deleteError, setDeleteError] = useState("");

  useEffect(() => {
    setHistory(null);
    api.documentHistory(doc.id).then(setHistory).catch(() => setHistory(null));
  }, [doc.id]);

  async function verifyEcp() {
    setSigError("");
    setSigning(true);
    try {
      // Sign the document's checksum with the operator's ЭЦП, then verify server-side.
      const payload = b64(new TextEncoder().encode(doc.checksum_sha256));
      const cms = await signCms(payload);
      const result = await api.verifySignature(cms, doc.id);
      setSig(result);
      onChanged?.();
    } catch (err) {
      setSigError(err.message);
    } finally {
      setSigning(false);
    }
  }

  async function remove() {
    if (!confirm("Удалить запись из каталога? Оригинал останется под WORM-хранением.")) return;
    setDeleteError("");
    try {
      await api.deleteDocument(doc.id);
    } catch (err) {
      // Напр. 409: документ включён в акт о выделении к уничтожению.
      setDeleteError(err.message);
      return;
    }
    onChanged?.();
    onClose();
  }

  async function submitSupersede(e) {
    e.preventDefault();
    if (!supersedeFile) {
      setSupersedeError("Выберите новый файл документа");
      return;
    }
    setSupersedeError("");
    setSupersedeBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", supersedeFile);
      Object.entries(supersedeForm).forEach(([k, v]) => fd.append(k, v));
      const newDoc = await api.supersedeDocument(doc.id, fd);
      setSupersedeOpen(false);
      onChanged?.();
      onOpenDocument?.(newDoc.id);
    } catch (err) {
      setSupersedeError(err.message);
    } finally {
      setSupersedeBusy(false);
    }
  }

  const isRealEstate = doc.cadastral_number || doc.real_estate_address;
  // Кадастровый паспорт — технический документ об объекте (площадь, этажность),
  // а не о собственнике: право им не устанавливается. Поэтому при замене
  // паспорта поле «правообладатель» не показываем — собственник меняется через
  // правоустанавливающий документ / справку о зарегистрированных правах.
  const isObjectOnlyDoc = doc.doc_type === "Кадастровый паспорт";
  const isCurrent = !doc.superseded_at;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>{doc.title}</h2>
          <button className="icon-btn" onClick={onClose}>✕</button>
        </div>

        <div className="badges">
          <StatusBadge status={doc.status} />
          <SignatureBadge status={doc.signature_status} />
          {!isCurrent && (
            <span className="badge b-gray" title={`Заменён ${fmtD(doc.superseded_at)}`}>
              🔁 заменён {fmtD(doc.superseded_at)}
            </span>
          )}
          {isCurrent && doc.replaces_id && (
            <span className="badge b-green">актуальная версия</span>
          )}
        </div>

        <div className="meta-grid">
          <div><span>Тип</span>{doc.doc_type || "—"}</div>
          <div><span>Номер</span>{doc.doc_number || "—"}</div>
          <div><span>Контрагент{isRealEstate ? " / правообладатель" : ""}</span>{doc.counterparty || "—"}</div>
          <div><span>Дата документа</span>{fmtD(doc.doc_date)}</div>
          <div><span>Сумма</span>{doc.amount != null ? `${Number(doc.amount).toLocaleString("ru-RU")} ${doc.currency || "₸"}` : "—"}</div>
          <div><span>Фонд/Опись/Дело</span>{[doc.fond, doc.opis, doc.delo].filter(Boolean).join(" / ") || "—"}</div>
          <div><span>Срок хранения</span>{doc.permanent ? "Постоянно" : (doc.retention_label || "—")}{!doc.permanent && doc.retention_until ? ` · до ${fmtD(doc.retention_until)}` : ""}</div>
          <div><span>Файл</span>{doc.original_filename} · {(doc.size / 1024).toFixed(1)} КБ</div>
          <div><span>SHA-256</span><code className="hash">{doc.checksum_sha256.slice(0, 24)}…</code></div>
          {isRealEstate && (
            <>
              <div><span>Кадастровый номер</span>{doc.cadastral_number || "—"}</div>
              <div><span>Адрес объекта</span>{doc.real_estate_address || "—"}</div>
              {doc.real_estate_area != null && <div><span>Площадь</span>{doc.real_estate_area} м²</div>}
            </>
          )}
        </div>

        {doc.annotation && (
          <div className="annotation">
            <div className="annotation-label">📝 Опись (авто-аннотация)</div>
            <p>{doc.annotation}</p>
          </div>
        )}
        {doc.description && <p className="desc">{doc.description}</p>}
        {doc.status_detail && doc.status !== "ready" && (
          <div className="alert info">{doc.status_detail}</div>
        )}

        {doc.ocr_text && (
          <details className="ocr">
            <summary>Распознанный текст (OCR) · {doc.ocr_text.length} симв.</summary>
            <pre>{doc.ocr_text.slice(0, 4000)}</pre>
          </details>
        )}

        {history && history.chain.length > 1 && (
          <div className="version-history">
            <div className="annotation-label">🔁 История версий документа</div>
            {history.chain.map((h, i) => (
              <div key={h.id} className={`version-row ${h.id === doc.id ? "current" : ""}`}>
                <span className="muted small">{i + 1}.</span>
                {h.id === doc.id ? (
                  <span className="version-title">{h.title}</span>
                ) : (
                  <button className="linklike" onClick={() => onOpenDocument?.(h.id)}>{h.title}</button>
                )}
                <span className="muted small">{fmtD(h.doc_date)}</span>
                {h.is_current ? (
                  <span className="badge b-green">текущая</span>
                ) : (
                  <span className="badge b-gray">до {fmtD(h.superseded_at)}</span>
                )}
              </div>
            ))}
          </div>
        )}

        {doc.signer_info && (
          <div className="alert info"><b>Подписант:</b> {doc.signer_info}</div>
        )}
        {sig && (
          <div className={`alert ${sig.status === "valid" ? "success" : "error"}`}>
            {sig.detail} {sig.signer_info && `· ${sig.signer_info}`}
          </div>
        )}
        {sigError && <div className="alert error">{sigError}</div>}

        {supersedeOpen && (
          <form className="supersede-form" onSubmit={submitSupersede}>
            <div className="annotation-label">🔁 Новая версия документа</div>
            <p className="muted small">
              Оригинал в архиве не изменяется — регистрируется новый документ, а
              текущий помечается заменённым. Незаполненные поля наследуются от
              текущей версии{isRealEstate ? " (кадастровый номер, адрес, площадь, дело)" : ""}.
            </p>
            <input type="file" required onChange={(e) => setSupersedeFile(e.target.files[0])} />
            {isObjectOnlyDoc && (
              <p className="muted small" style={{ marginTop: 8 }}>
                Кадастровый паспорт описывает объект, а не собственника. Смена
                правообладателя оформляется заменой правоустанавливающего
                документа или справки о зарегистрированных правах.
              </p>
            )}
            <div className="row3" style={{ marginTop: 10 }}>
              {!isObjectOnlyDoc && (
                <div>
                  <label>{isRealEstate ? "Новый правообладатель" : "Контрагент"}</label>
                  <input value={supersedeForm.counterparty}
                    onChange={(e) => setSupersedeForm({ ...supersedeForm, counterparty: e.target.value })}
                    placeholder={doc.counterparty || "оставьте пустым — без изменений"} />
                </div>
              )}
              <div>
                <label>Номер документа</label>
                <input value={supersedeForm.doc_number}
                  onChange={(e) => setSupersedeForm({ ...supersedeForm, doc_number: e.target.value })} />
              </div>
              <div>
                <label>Дата документа</label>
                <input type="date" value={supersedeForm.doc_date}
                  onChange={(e) => setSupersedeForm({ ...supersedeForm, doc_date: e.target.value })} />
              </div>
            </div>
            {isRealEstate && (
              <>
                <p className="muted small" style={{ marginTop: 12 }}>
                  Характеристики объекта — заполните, если изменились (напр.
                  переоформление кадастрового паспорта после реконструкции):
                </p>
                <div className="row3" style={{ marginTop: 6 }}>
                  <div>
                    <label>Кадастровый номер</label>
                    <input value={supersedeForm.cadastral_number}
                      onChange={(e) => setSupersedeForm({ ...supersedeForm, cadastral_number: e.target.value })}
                      placeholder={doc.cadastral_number || "без изменений"} />
                  </div>
                  <div>
                    <label>Площадь, м²</label>
                    <input type="number" step="0.01" value={supersedeForm.real_estate_area}
                      onChange={(e) => setSupersedeForm({ ...supersedeForm, real_estate_area: e.target.value })}
                      placeholder={doc.real_estate_area != null ? String(doc.real_estate_area) : "без изменений"} />
                  </div>
                  <div>
                    <label>Адрес объекта</label>
                    <input value={supersedeForm.real_estate_address}
                      onChange={(e) => setSupersedeForm({ ...supersedeForm, real_estate_address: e.target.value })}
                      placeholder={doc.real_estate_address || "без изменений"} />
                  </div>
                </div>
              </>
            )}
            {supersedeError && <div className="alert error">{supersedeError}</div>}
            <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
              <button className="btn primary" disabled={supersedeBusy}>
                {supersedeBusy ? "Загрузка…" : "Зарегистрировать новую версию"}
              </button>
              <button type="button" className="btn" onClick={() => setSupersedeOpen(false)}>Отмена</button>
            </div>
          </form>
        )}

        {deleteError && <div className="alert error">{deleteError}</div>}

        <div className="modal-actions">
          <button
            className="btn"
            onClick={() => api.downloadDocument(doc.id, doc.original_filename).catch((e) => setSigError(e.message))}
          >
            ⬇️ Скачать
          </button>
          <button className="btn" onClick={verifyEcp} disabled={signing}>
            {signing ? "Подписание…" : "🔏 Подписать и проверить ЭЦП"}
          </button>
          <button className="btn" title="Заверенная бумажная копия ЭД (п. 38/44 приказа № 236)"
            onClick={() => api.downloadBlob(`/documents/${doc.id}/certified-copy`, "certified_copy.pdf").catch((e) => setSigError(e.message))}>
            📄 Заверенная копия
          </button>
          {isCurrent && !doc.destroyed_at && (
            <button className="btn"
              title={isRealEstate
                ? "Новая версия: смена собственника или переоформление кадастровых характеристик"
                : "Зарегистрировать новую версию (оригинал в WORM неизменяем)"}
              onClick={() => setSupersedeOpen((v) => !v)}>
              🔁 Заменить документ
            </button>
          )}
          {canDelete && (
            <button className="btn danger" onClick={remove}>🗑 Удалить запись</button>
          )}
        </div>
      </div>
    </div>
  );
}
