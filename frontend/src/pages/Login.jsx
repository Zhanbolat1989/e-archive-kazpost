import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";

export default function Login() {
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("admin@earchive.kz");
  const [password, setPassword] = useState("admin12345");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (user) navigate("/", { replace: true });
  }, [user, navigate]);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(email, password);
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
      </div>
    </div>
  );
}
