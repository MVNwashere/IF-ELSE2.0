import { useState } from "react";

interface Props {
  onLogin: (username: string, password: string) => Promise<void>;
  error: string | null;
}

const QUICK = [
  { label: "Lotte", username: "lotte" },
  { label: "Sara", username: "sara" },
  { label: "Jan", username: "jan" },
];

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
        <form
          className="login"
          onSubmit={(e) => { e.preventDefault(); void submit(); }}
        >
          <div>
            <h1>KBC Adaptive Home</h1>
            <p>One app that composes itself around your life. Persona sets the stage, moments fill it.</p>
          </div>
          <div>
            <label htmlFor="u">Username</label>
            <input id="u" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" placeholder="lotte, sara or jan" />
          </div>
          <div>
            <label htmlFor="p">Password</label>
            <input id="p" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
          </div>
          {error && <div className="error">{error}</div>}
          <button className="go" type="submit" disabled={busy || !username}>{busy ? "Signing in…" : "Sign in"}</button>
          <div>
            <label>Demo customers</label>
            <div className="quick">
              {QUICK.map((q) => (
                <button key={q.username} type="button" disabled={busy} onClick={() => { setUsername(q.username); void submit(q.username, password); }}>
                  {q.label}
                </button>
              ))}
            </div>
          </div>
          <div className="synthetic">All data is synthetic. No real customer data is used.</div>
        </form>
      </div>
    </div>
  );
}
