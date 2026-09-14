const BASE = "/api";

function authHeaders() {
  const t = localStorage.getItem("token");
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function handle(res) {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}

export const api = {
  // Профиль редакции (название, оформление, состав меню). Без токена:
  // запрашивается ещё до входа.
  edition() {
    return fetch(`${BASE}/meta/edition`).then(handle);
  },

  async login(email, password) {
    const form = new URLSearchParams();
    form.set("username", email);
    form.set("password", password);
    const res = await fetch(`${BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form,
    });
    return handle(res);
  },

  me() {
    return fetch(`${BASE}/auth/me`, { headers: authHeaders() }).then(handle);
  },

  // Фильтры модуля «Документы» (ТЗ АГП п. 8): подразделение, вид, дело, год,
  // срок хранения/уничтожения, очередь ручной проверки распознавания.
  listDocuments(params = {}) {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== "" && v != null)
    );
    const qs = q.toString();
    return fetch(`${BASE}/documents${qs ? `?${qs}` : ""}`, {
      headers: authHeaders(),
    }).then(handle);
  },

  dashboard() {
    return fetch(`${BASE}/stats/dashboard`, { headers: authHeaders() }).then(handle);
  },

  documentTypes() {
    return fetch(`${BASE}/documents/meta/types`, { headers: authHeaders() }).then(handle);
  },

  // ---- Nomenclature ----
  listNomenclature() {
    return fetch(`${BASE}/nomenclature`, { headers: authHeaders() }).then(handle);
  },
  createNomenclature(item) {
    return fetch(`${BASE}/nomenclature`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(item),
    }).then(handle);
  },
  deleteNomenclature(id) {
    return fetch(`${BASE}/nomenclature/${id}`, { method: "DELETE", headers: authHeaders() }).then(handle);
  },

  // ---- Cases (дела) ----
  listCases() {
    return fetch(`${BASE}/cases`, { headers: authHeaders() }).then(handle);
  },
  getCase(id) {
    return fetch(`${BASE}/cases/${id}`, { headers: authHeaders() }).then(handle);
  },
  createCase(payload) {
    return fetch(`${BASE}/cases`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },
  updateCase(id, payload) {
    return fetch(`${BASE}/cases/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },
  addDocToCase(caseId, docId) {
    return fetch(`${BASE}/cases/${caseId}/documents/${docId}`, {
      method: "POST", headers: authHeaders(),
    }).then(handle);
  },
  removeDocFromCase(caseId, docId) {
    return fetch(`${BASE}/cases/${caseId}/documents/${docId}`, {
      method: "DELETE", headers: authHeaders(),
    }).then(handle);
  },
  async downloadForm(caseId, kind, fmt, filename) {
    const res = await fetch(`${BASE}/cases/${caseId}/forms/${kind}?fmt=${fmt}`, {
      headers: authHeaders(),
    });
    if (!res.ok) throw new Error("Не удалось сформировать форму");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
  archiveForm(caseId, kind) {
    return fetch(`${BASE}/cases/${caseId}/forms/${kind}/archive`, {
      method: "POST", headers: authHeaders(),
    }).then(handle);
  },

  // ---- Lifecycle: destruction acts, regcards, ledger ----
  listDestructionActs() {
    return fetch(`${BASE}/destruction-acts`, { headers: authHeaders() }).then(handle);
  },
  getDestructionAct(id) {
    return fetch(`${BASE}/destruction-acts/${id}`, { headers: authHeaders() }).then(handle);
  },
  createDestructionAct(documentIds, isElectronic = true, note = "") {
    return fetch(`${BASE}/destruction-acts`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ document_ids: documentIds, is_electronic: isElectronic, note }),
    }).then(handle);
  },
  approveDestructionAct(id) {
    return fetch(`${BASE}/destruction-acts/${id}/approve`, {
      method: "POST", headers: authHeaders(),
    }).then(handle);
  },
  async downloadActPdf(id, number) {
    const res = await fetch(`${BASE}/destruction-acts/${id}/pdf`, { headers: authHeaders() });
    if (!res.ok) throw new Error("Не удалось сформировать акт");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `act_${(number || id).replace("/", "-")}.pdf`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  },
  getRegCard(docId) {
    return fetch(`${BASE}/regcards/${docId}`, { headers: authHeaders() }).then(handle);
  },
  ledger() {
    return fetch(`${BASE}/ledger`, { headers: authHeaders() }).then(handle);
  },

  // ---- Issues (выдача дел) ----
  listIssues() {
    return fetch(`${BASE}/issues`, { headers: authHeaders() }).then(handle);
  },
  createIssue(payload) {
    return fetch(`${BASE}/issues`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },
  markIssued(id) {
    return fetch(`${BASE}/issues/${id}/issue`, { method: "POST", headers: authHeaders() }).then(handle);
  },
  markReturned(id) {
    return fetch(`${BASE}/issues/${id}/return`, { method: "POST", headers: authHeaders() }).then(handle);
  },

  async downloadBlob(path, filename) {
    const res = await fetch(`${BASE}${path}`, { headers: authHeaders() });
    if (!res.ok) {
      let msg = "Не удалось скачать";
      try { msg = (await res.json()).detail || msg; } catch (_) {}
      throw new Error(msg);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    const skipped = res.headers.get("X-Print-Skipped");
    return { skipped: skipped ? Number(skipped) : 0 };
  },
  async postBlob(path, filename) {
    const res = await fetch(`${BASE}${path}`, { method: "POST", headers: authHeaders() });
    if (!res.ok) throw new Error("Не удалось сформировать документ");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  },
  auditLog() {
    return fetch(`${BASE}/audit?limit=100`, { headers: authHeaders() }).then(handle);
  },

  getDocument(id) {
    return fetch(`${BASE}/documents/${id}`, { headers: authHeaders() }).then(handle);
  },

  uploadDocument(formData) {
    return fetch(`${BASE}/documents`, {
      method: "POST",
      headers: authHeaders(),
      body: formData,
    }).then(handle);
  },

  supersedeDocument(id, formData) {
    return fetch(`${BASE}/documents/${id}/supersede`, {
      method: "POST",
      headers: authHeaders(),
      body: formData,
    }).then(handle);
  },

  documentHistory(id) {
    return fetch(`${BASE}/documents/${id}/history`, { headers: authHeaders() }).then(handle);
  },

  deleteDocument(id) {
    return fetch(`${BASE}/documents/${id}`, {
      method: "DELETE",
      headers: authHeaders(),
    }).then(handle);
  },

  async downloadDocument(id, filename) {
    const res = await fetch(`${BASE}/documents/${id}/download`, {
      headers: authHeaders(),
    });
    if (!res.ok) throw new Error("Не удалось скачать файл");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename || "document";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  search(q, mode = "hybrid") {
    const params = new URLSearchParams({ q, mode });
    return fetch(`${BASE}/search?${params}`, { headers: authHeaders() }).then(handle);
  },

  chat(question) {
    return fetch(`${BASE}/search/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ question }),
    }).then(handle);
  },

  agent(messages, { requestId, signal } = {}) {
    return fetch(`${BASE}/search/agent`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ messages, request_id: requestId }),
      signal,
    }).then(handle);
  },

  // Останавливает генерацию на сервере: обрыв соединения сам по себе модель
  // не останавливает, поэтому отмену передаём отдельным запросом.
  cancelAgent(requestId) {
    return fetch(`${BASE}/search/agent/cancel`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ request_id: requestId }),
    }).then(handle);
  },

  verifySignature(cmsBase64, documentId) {
    return fetch(`${BASE}/signatures/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ cms_base64: cmsBase64, document_id: documentId }),
    }).then(handle);
  },

  // ---- Второй фактор и сессии (раздел 14 ТС) ----
  verifyTwoFactor(challengeId, code) {
    return fetch(`${BASE}/auth/2fa`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ challenge_id: challengeId, code }),
    }).then(handle);
  },

  logout() {
    return fetch(`${BASE}/auth/logout`, { method: "POST", headers: authHeaders() })
      .then(handle);
  },

  // ---- Ключи доступа WebAuthn: вход по биометрии (ТС-176 разд. 14 п. 4.2) ----
  passkeyStatus() {
    return fetch(`${BASE}/auth/passkeys/status`).then(handle);
  },

  passkeyLoginOptions() {
    return fetch(`${BASE}/auth/passkeys/login/options`, { method: "POST" }).then(handle);
  },

  passkeyLogin(challengeId, credential) {
    return fetch(`${BASE}/auth/passkeys/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ challenge_id: challengeId, credential }),
    }).then(handle);
  },

  listPasskeys() {
    return fetch(`${BASE}/auth/passkeys`, { headers: authHeaders() }).then(handle);
  },

  passkeyRegisterOptions() {
    return fetch(`${BASE}/auth/passkeys/register/options`, {
      method: "POST", headers: authHeaders(),
    }).then(handle);
  },

  registerPasskey(challengeId, credential, name = "") {
    return fetch(`${BASE}/auth/passkeys/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ challenge_id: challengeId, credential, name }),
    }).then(handle);
  },

  deletePasskey(id) {
    return fetch(`${BASE}/auth/passkeys/${id}`, {
      method: "DELETE", headers: authHeaders(),
    }).then(handle);
  },

  mySessions() {
    return fetch(`${BASE}/auth/me/sessions`, { headers: authHeaders() }).then(handle);
  },

  revokeMySession(id) {
    return fetch(`${BASE}/auth/me/sessions/${id}`, {
      method: "DELETE", headers: authHeaders(),
    }).then(handle);
  },

  allSessions() {
    return fetch(`${BASE}/auth/sessions`, { headers: authHeaders() }).then(handle);
  },

  revokeSession(id) {
    return fetch(`${BASE}/auth/sessions/${id}`, {
      method: "DELETE", headers: authHeaders(),
    }).then(handle);
  },

  updateProfile(payload) {
    return fetch(`${BASE}/auth/me`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },

  changePassword(currentPassword, newPassword) {
    return fetch(`${BASE}/auth/me/password`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    }).then(handle);
  },

  // ---- Пользователи (администрирование, п. 4.9) ----
  listUsers() {
    return fetch(`${BASE}/auth/users`, { headers: authHeaders() }).then(handle);
  },

  createUser(payload) {
    return fetch(`${BASE}/auth/users`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },

  updateUser(id, payload) {
    return fetch(`${BASE}/auth/users/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },

  unlockUser(id) {
    return fetch(`${BASE}/auth/users/${id}/unlock`, {
      method: "POST", headers: authHeaders(),
    }).then(handle);
  },

  // ---- Аудиторский след (раздел 14) ----
  auditTrail(params = {}) {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== "" && v != null)
    );
    return fetch(`${BASE}/audit?${q}`, { headers: authHeaders() }).then(handle);
  },

  auditStats() {
    return fetch(`${BASE}/audit/stats`, { headers: authHeaders() }).then(handle);
  },

  archiveAudit() {
    return fetch(`${BASE}/audit/archive`, { method: "POST", headers: authHeaders() })
      .then(handle);
  },

  // ---- Модуль «Предприятие» (п. 4.8) ----
  getOrganization() {
    return fetch(`${BASE}/enterprise/organization`, { headers: authHeaders() }).then(handle);
  },

  saveOrganization(payload) {
    return fetch(`${BASE}/enterprise/organization`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },

  listDepartments() {
    return fetch(`${BASE}/enterprise/departments`, { headers: authHeaders() }).then(handle);
  },

  createDepartment(payload) {
    return fetch(`${BASE}/enterprise/departments`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },

  updateDepartment(id, payload) {
    return fetch(`${BASE}/enterprise/departments/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },

  deleteDepartment(id) {
    return fetch(`${BASE}/enterprise/departments/${id}`, {
      method: "DELETE", headers: authHeaders(),
    }).then(handle);
  },

  listSigners() {
    return fetch(`${BASE}/enterprise/signers`, { headers: authHeaders() }).then(handle);
  },

  // ---- Модуль «Управление отчетами» (п. 4.4) ----
  listReports() {
    return fetch(`${BASE}/reports`, { headers: authHeaders() }).then(handle);
  },

  getReport(key) {
    return fetch(`${BASE}/reports/${key}`, { headers: authHeaders() }).then(handle);
  },

  // ---- Маршруты согласования (п. 4.10) ----
  listApprovals(objectType, objectId) {
    const q = new URLSearchParams({ object_type: objectType, object_id: objectId });
    return fetch(`${BASE}/approvals?${q}`, { headers: authHeaders() }).then(handle);
  },

  myApprovals() {
    return fetch(`${BASE}/approvals/my`, { headers: authHeaders() }).then(handle);
  },

  createApproval(payload) {
    return fetch(`${BASE}/approvals`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },

  decideApproval(id, approve, comment = "") {
    return fetch(`${BASE}/approvals/${id}/decide`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ approve, comment }),
    }).then(handle);
  },

  approvalsMeta() {
    return fetch(`${BASE}/approvals/meta`, { headers: authHeaders() }).then(handle);
  },

  // Согласующие по шаблону — до запуска маршрута
  previewApproval(payload) {
    return fetch(`${BASE}/approvals/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },

  listRouteTemplates(objectType = "", includeInactive = false) {
    const q = new URLSearchParams();
    if (objectType) q.set("object_type", objectType);
    if (includeInactive) q.set("include_inactive", "true");
    return fetch(`${BASE}/approvals/templates?${q}`, { headers: authHeaders() }).then(handle);
  },

  createRouteTemplate(payload) {
    return fetch(`${BASE}/approvals/templates`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },

  updateRouteTemplate(id, payload) {
    return fetch(`${BASE}/approvals/templates/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },

  deleteRouteTemplate(id) {
    return fetch(`${BASE}/approvals/templates/${id}`, {
      method: "DELETE", headers: authHeaders(),
    }).then(handle);
  },

  // ---- Справочники (п. 4.9) ----
  listDictionaries() {
    return fetch(`${BASE}/dictionaries`, { headers: authHeaders() }).then(handle);
  },

  // Действующие значения одного справочника — для подсказок и выбора в формах
  dictionaryValues(kind) {
    return fetch(`${BASE}/dictionaries`, { headers: authHeaders() })
      .then(handle)
      .then((list) => (list.find((d) => d.kind === kind)?.entries || [])
        .filter((x) => x.is_active)
        .map((x) => x.value));
  },

  addDictionaryEntry(kind, payload) {
    return fetch(`${BASE}/dictionaries/${kind}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },

  updateDictionaryEntry(id, payload) {
    return fetch(`${BASE}/dictionaries/entries/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },

  // ---- НТО, экспертные комиссии, передача в госархив (п. 5.3, 8.2, 10.2–10.5) ----
  ntoMeta() {
    return fetch(`${BASE}/nto/meta`, { headers: authHeaders() }).then(handle);
  },

  listProtocols() {
    return fetch(`${BASE}/nto/protocols`, { headers: authHeaders() }).then(handle);
  },

  createProtocol(payload) {
    return fetch(`${BASE}/nto/protocols`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },

  updateProtocol(id, payload) {
    return fetch(`${BASE}/nto/protocols/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },

  deleteProtocol(id) {
    return fetch(`${BASE}/nto/protocols/${id}`, {
      method: "DELETE", headers: authHeaders(),
    }).then(handle);
  },

  addProtocolDecision(protocolId, payload) {
    return fetch(`${BASE}/nto/protocols/${protocolId}/decisions`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },

  deleteProtocolDecision(protocolId, decisionId) {
    return fetch(`${BASE}/nto/protocols/${protocolId}/decisions/${decisionId}`, {
      method: "DELETE", headers: authHeaders(),
    }).then(handle);
  },

  // Решения комиссий по объекту — для карточек описи и акта
  objectDecisions(objectType, objectId) {
    const q = new URLSearchParams({ object_type: objectType, object_id: objectId });
    return fetch(`${BASE}/nto/decisions?${q}`, { headers: authHeaders() }).then(handle);
  },

  listNtoRecords(kind = "") {
    const q = kind ? `?${new URLSearchParams({ kind })}` : "";
    return fetch(`${BASE}/nto/records${q}`, { headers: authHeaders() }).then(handle);
  },

  createNtoRecord(payload) {
    return fetch(`${BASE}/nto/records`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },

  updateNtoRecord(id, payload) {
    return fetch(`${BASE}/nto/records/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },

  approveNtoRecord(id) {
    return fetch(`${BASE}/nto/records/${id}/approve`, {
      method: "POST", headers: authHeaders(),
    }).then(handle);
  },

  deleteNtoRecord(id) {
    return fetch(`${BASE}/nto/records/${id}`, {
      method: "DELETE", headers: authHeaders(),
    }).then(handle);
  },

  listTransfers() {
    return fetch(`${BASE}/nto/transfers`, { headers: authHeaders() }).then(handle);
  },

  createTransfer(payload) {
    return fetch(`${BASE}/nto/transfers`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },

  updateTransfer(id, payload) {
    return fetch(`${BASE}/nto/transfers/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },

  deleteTransfer(id) {
    return fetch(`${BASE}/nto/transfers/${id}`, {
      method: "DELETE", headers: authHeaders(),
    }).then(handle);
  },

  // Дела приняты госархивом: акт закрывается, дела получают статус «Передано»
  completeTransfer(id) {
    return fetch(`${BASE}/nto/transfers/${id}/complete`, {
      method: "POST", headers: authHeaders(),
    }).then(handle);
  },

  documentUsage(id) {
    return fetch(`${BASE}/documents/${id}/usage`, { headers: authHeaders() }).then(handle);
  },

  // ---- Качество оцифровки и реквизиты (ТЗ АГП п. 12.1, 12.5) ----
  reviewQueue() {
    return fetch(`${BASE}/documents/meta/review`, { headers: authHeaders() }).then(handle);
  },
  acceptReview(id) {
    return fetch(`${BASE}/documents/${id}/review/accept`, {
      method: "POST", headers: authHeaders(),
    }).then(handle);
  },
  documentEntities(id) {
    return fetch(`${BASE}/documents/${id}/entities`, { headers: authHeaders() }).then(handle);
  },
  documentChanges(id) {
    return fetch(`${BASE}/documents/${id}/changes`, { headers: authHeaders() }).then(handle);
  },

  // ---- Архивные запросы (ТЗ АГП п. 8) ----
  listArchiveRequests(params = {}) {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== "" && v != null)
    );
    return fetch(`${BASE}/archive-requests?${q}`, { headers: authHeaders() }).then(handle);
  },
  requestStatuses() {
    return fetch(`${BASE}/archive-requests/meta/statuses`, { headers: authHeaders() }).then(handle);
  },
  createArchiveRequest(payload) {
    return fetch(`${BASE}/archive-requests`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },
  updateArchiveRequest(id, payload) {
    return fetch(`${BASE}/archive-requests/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },
  deleteArchiveRequest(id) {
    return fetch(`${BASE}/archive-requests/${id}`, {
      method: "DELETE", headers: authHeaders(),
    }).then(handle);
  },

  // ---- Описи дел ----
  listInventories(params = {}) {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== "" && v != null)
    );
    return fetch(`${BASE}/inventories?${q}`, { headers: authHeaders() }).then(handle);
  },
  inventoryKinds() {
    return fetch(`${BASE}/inventories/meta/kinds`, { headers: authHeaders() }).then(handle);
  },
  getInventory(id) {
    return fetch(`${BASE}/inventories/${id}`, { headers: authHeaders() }).then(handle);
  },
  createInventory(payload) {
    return fetch(`${BASE}/inventories`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },
  refillInventory(id) {
    return fetch(`${BASE}/inventories/${id}/refill`, {
      method: "POST", headers: authHeaders(),
    }).then(handle);
  },
  deleteInventory(id) {
    return fetch(`${BASE}/inventories/${id}`, {
      method: "DELETE", headers: authHeaders(),
    }).then(handle);
  },

  // ---- Вложения к карточкам описей, актов, запросов, номенклатуры ----
  listAttachments(ownerType, ownerId) {
    const q = new URLSearchParams({ owner_type: ownerType, owner_id: ownerId });
    return fetch(`${BASE}/attachments?${q}`, { headers: authHeaders() }).then(handle);
  },
  uploadAttachment(ownerType, ownerId, file) {
    const q = new URLSearchParams({ owner_type: ownerType, owner_id: ownerId });
    const form = new FormData();
    form.append("file", file);
    return fetch(`${BASE}/attachments?${q}`, {
      method: "POST", headers: authHeaders(), body: form,
    }).then(handle);
  },
  deleteAttachment(id) {
    return fetch(`${BASE}/attachments/${id}`, {
      method: "DELETE", headers: authHeaders(),
    }).then(handle);
  },

  // ---- Импорт пакетов оцифровки и восстановление из копии ----
  listImports() {
    return fetch(`${BASE}/imports`, { headers: authHeaders() }).then(handle);
  },
  getImport(id) {
    return fetch(`${BASE}/imports/${id}`, { headers: authHeaders() }).then(handle);
  },
  uploadImport(file) {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${BASE}/imports`, {
      method: "POST", headers: authHeaders(), body: form,
    }).then(handle);
  },

  // ---- Номенклатура: правка, статусы, сводная форма ----
  updateNomenclature(id, payload) {
    return fetch(`${BASE}/nomenclature/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },
  setNomenclatureStatus(id, status) {
    const q = new URLSearchParams({ status });
    return fetch(`${BASE}/nomenclature/${id}/status?${q}`, {
      method: "POST", headers: authHeaders(),
    }).then(handle);
  },
  nomenclatureStatuses() {
    return fetch(`${BASE}/nomenclature/meta/statuses`, { headers: authHeaders() }).then(handle);
  },

  // ---- Сроки уничтожения: перечни по годам ----
  destructionOverview() {
    return fetch(`${BASE}/destruction-overview`, { headers: authHeaders() }).then(handle);
  },

  // ---- Аннотация дела, составленная ИИ (п. 12.4) ----
  annotateCase(id) {
    return fetch(`${BASE}/cases/${id}/annotate`, {
      method: "POST", headers: authHeaders(),
    }).then(handle);
  },

  // ---- Помощь: обращения в поддержку ----
  listTickets(params = {}) {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== "" && v != null)
    );
    return fetch(`${BASE}/support?${q}`, { headers: authHeaders() }).then(handle);
  },
  createTicket(payload) {
    return fetch(`${BASE}/support`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },
  answerTicket(id, payload) {
    return fetch(`${BASE}/support/${id}/answer`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },
  // Сроки SLA, повторное исполнение и расчёт оплаты (ТС-176 разд. 13)
  supportMeta() {
    return fetch(`${BASE}/support/meta`, { headers: authHeaders() }).then(handle);
  },
  takeTicket(id) {
    return fetch(`${BASE}/support/${id}/take`, {
      method: "POST", headers: authHeaders(),
    }).then(handle);
  },
  closeTicket(id) {
    return fetch(`${BASE}/support/${id}/close`, {
      method: "POST", headers: authHeaders(),
    }).then(handle);
  },
  reopenTicket(id, reason = "") {
    return fetch(`${BASE}/support/${id}/reopen`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ reason }),
    }).then(handle);
  },
  slaReport(params = {}) {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== "" && v != null)
    );
    return fetch(`${BASE}/support/sla?${q}`, { headers: authHeaders() }).then(handle);
  },

  // ---- Администрирование (ТЗ АГП п. 8–9) ----
  changeHistory(params = {}) {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== "" && v != null)
    );
    return fetch(`${BASE}/admin/changes?${q}`, { headers: authHeaders() }).then(handle);
  },
  docAccess() {
    return fetch(`${BASE}/admin/doc-access`, { headers: authHeaders() }).then(handle);
  },
  docAccessGroups() {
    return fetch(`${BASE}/admin/doc-access/groups`, { headers: authHeaders() }).then(handle);
  },
  setDocAccess(role, docGroups) {
    return fetch(`${BASE}/admin/doc-access`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ role, doc_groups: docGroups }),
    }).then(handle);
  },
  listApiKeys() {
    return fetch(`${BASE}/admin/api-keys`, { headers: authHeaders() }).then(handle);
  },
  createApiKey(payload) {
    return fetch(`${BASE}/admin/api-keys`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },
  revokeApiKey(id) {
    return fetch(`${BASE}/admin/api-keys/${id}`, {
      method: "DELETE", headers: authHeaders(),
    }).then(handle);
  },
  agentLog(params = {}) {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== "" && v != null)
    );
    return fetch(`${BASE}/admin/agent-log?${q}`, { headers: authHeaders() }).then(handle);
  },
  agentStats() {
    return fetch(`${BASE}/admin/agent-log/stats`, { headers: authHeaders() }).then(handle);
  },

  // ---- Сканирование (ТС-176 п. 4.5) и учёт работ оцифровки ----
  scanningArticles(year) {
    const q = new URLSearchParams({ year: String(year) });
    return fetch(`${BASE}/scanning/articles?${q}`, { headers: authHeaders() }).then(handle);
  },
  scanningCreateCase(payload) {
    return fetch(`${BASE}/scanning/cases`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },
  scanningUpload(caseId, formData) {
    return fetch(`${BASE}/scanning/cases/${caseId}/documents`, {
      method: "POST", headers: authHeaders(), body: formData,
    }).then(handle);
  },
  scanningStages(caseId) {
    return fetch(`${BASE}/scanning/cases/${caseId}/stages`, { headers: authHeaders() }).then(handle);
  },
  scanningSetStage(caseId, stage, payload) {
    return fetch(`${BASE}/scanning/cases/${caseId}/stages/${stage}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },
  scanningVolume(params = {}) {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== "" && v != null)
    );
    return fetch(`${BASE}/scanning/volume?${q}`, { headers: authHeaders() }).then(handle);
  },

  // ---- Электронные копии (ТС-176 п. 11.6–11.7) ----
  listCopies(params = {}) {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== "" && v != null)
    );
    return fetch(`${BASE}/ecopies?${q}`, { headers: authHeaders() }).then(handle);
  },
  markCopy(id, isCopy) {
    return fetch(`${BASE}/ecopies/${id}/mark`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ is_copy: isCopy }),
    }).then(handle);
  },
  certifyCopy(id, cmsBase64, note = "") {
    return fetch(`${BASE}/ecopies/${id}/certify`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ cms_base64: cmsBase64, note }),
    }).then(handle);
  },
  reconcileCopy(id, result, note = "") {
    return fetch(`${BASE}/ecopies/${id}/reconcile`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ result, note }),
    }).then(handle);
  },
  createCopyAct(documentIds, commissionProtocol = "", note = "") {
    return fetch(`${BASE}/ecopies/destruction-acts`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        document_ids: documentIds, commission_protocol: commissionProtocol, note,
      }),
    }).then(handle);
  },
  updateDestructionAct(id, payload) {
    return fetch(`${BASE}/destruction-acts/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    }).then(handle);
  },
};
