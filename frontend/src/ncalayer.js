// Minimal NCALayer bridge. NCALayer listens on wss://127.0.0.1:13579.
// It must be installed and running on the operator's machine (НУЦ РК client).

const NCALAYER_URL = "wss://127.0.0.1:13579/";

function connect() {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(NCALAYER_URL);
    const timer = setTimeout(() => {
      ws.close();
      reject(new Error("NCALayer не отвечает. Запустите приложение NCALayer."));
    }, 5000);
    ws.onopen = () => {
      clearTimeout(timer);
      resolve(ws);
    };
    ws.onerror = () => {
      clearTimeout(timer);
      reject(new Error("Не удалось подключиться к NCALayer (wss://127.0.0.1:13579)."));
    };
  });
}

// Sign a base64 payload with the user's ЭЦП, returning a base64 CMS.
export async function signCms(base64ToSign) {
  const ws = await connect();
  return new Promise((resolve, reject) => {
    ws.onmessage = (event) => {
      const resp = JSON.parse(event.data);
      ws.close();
      if (resp.code === "200" && resp.responseObject) {
        resolve(resp.responseObject);
      } else {
        reject(new Error(resp.message || "Подписание отменено или не удалось"));
      }
    };
    ws.onerror = () => reject(new Error("Ошибка связи с NCALayer"));

    const request = {
      module: "kz.gov.pki.knca.commonUtils",
      method: "createCMSSignatureFromBase64",
      args: ["PKCS12", "SIGNATURE", base64ToSign, true],
    };
    ws.send(JSON.stringify(request));
  });
}
