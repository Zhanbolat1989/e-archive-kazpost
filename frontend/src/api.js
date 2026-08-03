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

  listDocuments() {
    return fetch(`${BASE}/documents`, { headers: authHeaders() }).then(handle);
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

  agent(messages) {
    return fetch(`${BASE}/search/agent`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ messages }),
    }).then(handle);
  },

  verifySignature(cmsBase64, documentId) {
    return fetch(`${BASE}/signatures/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ cms_base64: cmsBase64, document_id: documentId }),
    }).then(handle);
  },
};
