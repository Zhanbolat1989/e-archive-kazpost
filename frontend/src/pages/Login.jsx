import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";

export default function Login() {
  const { login, verifyTwoFactor, user } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("admin@earchive.kz");
  const [password, setPassword] = useState("admin12345");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // Второй фактор (п. 3.3 ТС): challenge выдаётся при входе с нового
  // устройства либо при наличии второй активной сессии.
  const [challenge, setChallenge] = useState(null);
  const [code, setCode] = useState("");

  useEffect(() => {
    if (user) navigate("/", { replace: true });
  }, [user, navigate]);

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

  return (
    <div className="login-wrap">
      <div className="login-card">
        <div className="brand big">
          <span className="brand-mark">e</span>
          <div>
            <div className="brand-name">e-archive</div>
            <div className="brand-sub">Электронный архив · AI-поиск · ЭЦП РК</div>
          </div>
        </div>

        {!challenge ? (
          <>
            <form onSubmit={onSubmit}>
              <label>Email</label>
              <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required />
              <label>Пароль</label>
              <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" required />
              {error && <div className="alert error">{error}</div>}
              <button className="btn primary block" disabled={busy}>
                {busy ? "Вход…" : "Войти"}
              </button>
            </form>
            <div className="login-hint">По умолчанию: admin@earchive.kz / admin12345</div>
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
