// Ключи доступа WebAuthn: биометрия или PIN телефона вместо пароля
// (ТС-176 разд. 14 п. 4.2). Сервер отдаёт параметры в JSON с base64url, браузер
// работает с ArrayBuffer — здесь только перевод между ними.

function toBuffer(value) {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(base64 + "=".repeat((4 - (base64.length % 4)) % 4));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

function toBase64url(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

const descriptors = (list) => (list || []).map((c) => ({ ...c, id: toBuffer(c.id) }));

export function passkeysSupported() {
  return typeof window !== "undefined" && Boolean(window.PublicKeyCredential)
    && Boolean(navigator.credentials);
}

function common(credential) {
  return {
    id: credential.id,
    rawId: toBase64url(credential.rawId),
    type: credential.type,
    authenticatorAttachment: credential.authenticatorAttachment || undefined,
    clientExtensionResults: credential.getClientExtensionResults
      ? credential.getClientExtensionResults() : {},
  };
}

// Добавление ключа: устройство создаёт пару ключей после проверки владельца.
export async function createPasskey(options) {
  const credential = await navigator.credentials.create({
    publicKey: {
      ...options,
      challenge: toBuffer(options.challenge),
      user: { ...options.user, id: toBuffer(options.user.id) },
      excludeCredentials: descriptors(options.excludeCredentials),
    },
  });
  return {
    ...common(credential),
    response: {
      clientDataJSON: toBase64url(credential.response.clientDataJSON),
      attestationObject: toBase64url(credential.response.attestationObject),
      transports: credential.response.getTransports ? credential.response.getTransports() : [],
    },
  };
}

// Вход: устройство предлагает сохранённый ключ и подписывает вызов сервера.
export async function getPasskey(options) {
  const credential = await navigator.credentials.get({
    publicKey: {
      ...options,
      challenge: toBuffer(options.challenge),
      allowCredentials: descriptors(options.allowCredentials),
    },
  });
  const { response } = credential;
  return {
    ...common(credential),
    response: {
      clientDataJSON: toBase64url(response.clientDataJSON),
      authenticatorData: toBase64url(response.authenticatorData),
      signature: toBase64url(response.signature),
      userHandle: response.userHandle ? toBase64url(response.userHandle) : null,
    },
  };
}

// Отмена пользователем — не ошибка, о которой стоит кричать.
export function passkeyErrorMessage(err) {
  if (err?.name === "NotAllowedError") return "Подтверждение отменено или время истекло";
  if (err?.name === "InvalidStateError") return "Это устройство уже добавлено";
  return err?.message || "Не удалось использовать ключ доступа";
}
