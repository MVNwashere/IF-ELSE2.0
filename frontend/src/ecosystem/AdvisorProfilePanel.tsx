// Advisor view of one customer's profile, to prepare a conversation. Only when the customer allowed it
// ("My advisor may see my profile"); every look, allowed or refused, is written to the audit log.
import { useState } from "react";
import { api, ApiError, type ProfileResponse } from "../api";
import { MOCK, profileData } from "../data";

const DEMO_CUSTOMERS = ["lotte", "sara", "jan", "marc"];

export default function AdvisorProfilePanel() {
  const [who, setWho] = useState<string | null>(null);
  const [p, setP] = useState<ProfileResponse | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const look = async (username: string) => {
    setWho(username); setP(null); setMsg(null);
    try {
      setP(MOCK ? await profileData.get() : await api.advisorProfile(username));
    } catch (e) {
      setMsg(e instanceof ApiError && e.status === 403
        ? "This customer has not shared their profile with advisors. Their choice is respected (and the attempt is logged)."
        : e instanceof Error ? e.message : String(e));
    }
  };

  const told = p?.fields.filter((f) => f.value !== null) ?? [];
  return (
    <section className="ec-card">
      <h2>Customer profile · with the customer's permission</h2>
      <div className="ec-profile-pick">
        {DEMO_CUSTOMERS.map((u) => (
          <button key={u} type="button" className={`pbtn small ${who === u ? "active" : ""}`} onClick={() => void look(u)}>{u}</button>
        ))}
      </div>
      {msg && <p className="ec-sub">{msg}</p>}
      {p && (
        <div className="ec-profile">
          <div><b>Told us</b>{told.length ? told.map((f) => <span key={f.key}>{f.label}: {f.value_label}</span>) : <span>Nothing yet</span>}</div>
          <div><b>Engine sees</b>{p.personas.map((x) => <span key={x.persona}>{x.weight_pct}% {x.label}</span>)}</div>
          <div><b>Corrected</b>{p.corrections.length ? p.corrections.map((c) => <span key={`${c.kind}${c.target}`}>{c.label}</span>) : <span>Nothing</span>}</div>
          <div><b>Allows</b>{p.permissions.map((x) => <span key={x.purpose} className={x.allowed ? "" : "off"}>{x.allowed ? "✓" : "✕"} {x.label}</span>)}</div>
        </div>
      )}
    </section>
  );
}
