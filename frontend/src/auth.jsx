import { createContext, useContext, useEffect, useState } from "react";
import { api } from "./api.js";
import { getPasskey } from "./webauthn.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then(setUser)
      .catch(() => localStorage.removeItem("token"))
      .finally(() => setLoading(false));
  }, []);

  async function finish(accessToken) {
    localStorage.setItem("token", accessToken);
    setUser(await api.me());
  }

  // Возвращает описание второго фактора, если система запросила код (п. 3.3 ТС).
  async function login(email, password) {
    const res = await api.login(email, password);
    if (res.twofa_required) {
      return { twofaRequired: true, challengeId: res.challenge_id, delivery: res.delivery };
    }
    await finish(res.access_token);
    return { twofaRequired: false };
  }

  async function verifyTwoFactor(challengeId, code) {
    const { access_token } = await api.verifyTwoFactor(challengeId, code);
    await finish(access_token);
  }

  // Вход по ключу доступа — биометрия или PIN устройства (ТС-176 разд. 14 п. 4.2).
  // Email не нужен: устройство само предлагает сохранённый для сайта ключ.
  async function loginWithPasskey() {
    const { challenge_id, options } = await api.passkeyLoginOptions();
    const credential = await getPasskey(options);
    const { access_token } = await api.passkeyLogin(challenge_id, credential);
    await finish(access_token);
  }

  async function logout() {
    // Сессию гасим на сервере, иначе токен остался бы действующим до истечения.
    try {
      await api.logout();
    } catch (_) {}
    localStorage.removeItem("token");
    setUser(null);
  }

  async function refresh() {
    setUser(await api.me());
  }

  return (
    <AuthContext.Provider
      value={{ user, loading, login, verifyTwoFactor, loginWithPasskey, logout, refresh }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
