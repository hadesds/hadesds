import { FormEvent, useState } from "react";
import { post, setToken } from "../api";

export default function Login({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { token } = await post<{ token: string }>("/auth/login", { username, password });
      setToken(token);
      onLogin();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <form className="card" onSubmit={submit}>
        <h1>DevPulse <strong>AI</strong></h1>
        <p className="muted">Painel local</p>
        <label>Usuário<input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" /></label>
        <label>Senha<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></label>
        {error && <div className="alert alert-bad" role="alert">{error}</div>}
        <button type="submit" disabled={busy || !password}>{busy ? "Entrando…" : "Entrar"}</button>
      </form>
    </div>
  );
}
