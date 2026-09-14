import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { useEdition } from "../edition.jsx";
import { passkeyErrorMessage, passkeysSupported } from "../webauthn.js";

export default function Login() {
  const { login, verifyTwoFactor, loginWithPasskey, user } = useAuth();
  const edition = useEdition();
  const navigate = useNavigate();
  // Демонстрационная учётная запись подставляется только в локальной работе:
  // в контуре заказчика форма входа не должна подсказывать логин и пароль.
  const [email, setEmail] = useState(edition.demo ? "admin@earchive.kz" : "");
  const [password, setPassword] = useState(edition.demo ? "admin12345" : "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // Второй фактор (п. 3.3 ТС): challenge выдаётся при входе с нового
  // устройства либо при наличии второй активной сессии.
  const [challenge, setChallenge] = useState(null);
  const [code, setCode] = useState("");
  // Вход по биометрии (разд. 14 п. 4.2) — если включён на сервере и браузер
  // поддерживает ключи доступа.
  const [passkeyReady, setPasskeyReady] = useState(false);

  useEffect(() => {
    if (user) navigate("/", { replace: true });
  }, [user, navigate]);

  useEffect(() => {
    if (!passkeysSupported()) return;
    api.passkeyStatus().then((s) => setPasskeyReady(Boolean(s.enabled))).catch(() => {});
  }, []);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const res = await login(email, password);
      if (res.twofaRequired) {
        setChallenge(res);
        setCode("");
      } else {
        navigate("/", { replace: true });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function onVerify(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await verifyTwoFactor(challenge.challengeId, code.trim());
      navigate("/", { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function onPasskey() {
    setError("");
    setBusy(true);
    try {
      await loginWithPasskey();
      navigate("/", { replace: true });
    } catch (err) {
      setError(passkeyErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <div className="brand big">
          <span className="brand-mark">{edition.mark}</span>
          <div>
            <div className="brand-name">{edition.product}</div>
            <div className="brand-sub">{edition.tagline || edition.subtitle}</div>
          </div>
        </div>

        {!challenge ? (
          <>
            <form onSubmit={onSubmit}>
              <label>Email</label>
              <input value={email} onChange={(e) => setEmail(e.target.value)} type="email"
                     autoComplete="username webauthn" required />
              <label>Пароль</label>
              <input value={password} onChange={(e) => setPassword(e.target.value)} type="password"
                     autoComplete="current-password" required />
              {error && <div className="alert error">{error}</div>}
              <button className="btn primary block" disabled={busy}>
                {busy ? "Вход…" : "Войти"}
              </button>
            </form>
            {passkeyReady && (
              <button className="btn ghost block" style={{ marginTop: 10 }}
                      disabled={busy} onClick={onPasskey}>
                🔑 Войти по биометрии
              </button>
            )}
            {edition.demo && (
              <div className="login-hint">По умолчанию: admin@earchive.kz / admin12345</div>
            )}
          </>
        ) : (
          <>
            <form onSubmit={onVerify}>
              <div className="alert info" style={{ marginBottom: 12 }}>
                🔐 Подтверждение входа. {challenge.delivery === "email"
                  ? `Код отправлен на ${email}.`
                  : challenge.delivery === "throttled"
                    ? "Исчерпан лимит попыток ввода кода. Новый код будет выслан позже — дождитесь истечения текущего."
                    : "SMTP не настроен — код записан в журнал сервера (docker compose logs backend)."}
              </div>
              <label>Код подтверждения</label>
              <input
                value={code}
                onChange={(e) => setCode(e.target.value)}
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                placeholder="6 цифр"
                autoFocus
                required
              />
              {error && <div className="alert error">{error}</div>}
              <button className="btn primary block" disabled={busy || code.trim().length < 4}>
                {busy ? "Проверка…" : "Подтвердить"}
              </button>
            </form>
            <button
              className="btn ghost block"
              style={{ marginTop: 10 }}
              onClick={() => { setChallenge(null); setError(""); }}
            >
              ← Назад
            </button>
          </>
        )}
      </div>
    </div>
  );
}
