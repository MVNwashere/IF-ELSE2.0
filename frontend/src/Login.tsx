import { useState } from "react";
import { ADVISOR, DEMO_PERSONAS } from "./personas";

interface Props {
  onLogin: (username: string, password: string) => Promise<void>;
  error: string | null;
}

export default function Login({ onLogin, error }: Props) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("demo");
  const [busy, setBusy] = useState(false);

  const submit = async (u = username, p = password) => {
    if (!u) return;
    setBusy(true);
    try { await onLogin(u.toLowerCase(), p); } finally { setBusy(false); }
  };

  return (
    <div className="phone-bezel">
      <div className="phone" style={{ background: "#0d6fb8" }}>
        <div className="login">
          <div className="login-brand"><span className="login-ball" aria-hidden="true" /><h1>KBC Takes Care</h1></div>
          <p>One app that composes itself around your life. Pick a customer to see their home.</p>
          {error && <div className="error" role="alert">{error}</div>}
          <div className="login-personas" role="group" aria-label="Demo customers">
            {DEMO_PERSONAS.map((q) => (
              <button key={q.username} type="button" className="login-persona" disabled={busy} aria-label={`${q.name}: ${q.hint}`}
                onClick={() => { setUsername(q.username); void submit(q.username, password); }}>
                <b><i aria-hidden="true">{q.name[0]}</i>{q.name}</b>
                <span>{q.hint}</span>
              </button>
            ))}
            <button type="button" className="login-persona console" disabled={busy} aria-label={`${ADVISOR.name}: ${ADVISOR.hint}`}
              onClick={() => { setUsername(ADVISOR.username); void submit(ADVISOR.username, password); }}>
              <b>{ADVISOR.name}</b><span>{ADVISOR.hint} ›</span>
            </button>
          </div>
          <details>
            <summary>Sign in with a username</summary>
            <form className="login-form" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
              <div>
                <label htmlFor="u">Username</label>
                <input id="u" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username"
                  placeholder={DEMO_PERSONAS.map((d) => d.username).join(", ")} />
              </div>
              <div>
                <label htmlFor="p">Password</label>
                <input id="p" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
              </div>
              <button className="go" type="submit" disabled={busy || !username}>{busy ? "Signing in…" : "Sign in"}</button>
            </form>
          </details>
          <div className="synthetic">All data is synthetic. No real customer data is used. Demo password: demo.</div>
        </div>
      </div>
    </div>
  );
}
