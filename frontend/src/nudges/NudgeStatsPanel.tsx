// Advisor console panel: the attention budget KPI. Standalone; place it anywhere in the ecosystem console.
import { useEffect, useState } from "react";
import { nudgeApi } from "./client";
import type { NudgeStats } from "./types";
import { TIER_LABEL } from "./types";
import "./nudges.css";

const pct = (x: number | null) => (x == null ? "—" : `${Math.round(x * 100)}%`);

export default function NudgeStatsPanel() {
  const [s, setS] = useState<NudgeStats | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    nudgeApi.stats().then((r) => { if (alive) setS(r); }).catch((e) => { if (alive) setErr(e instanceof Error ? e.message : String(e)); });
    return () => { alive = false; };
  }, []);

  if (err) return <section className="ns-panel"><h2>Kate nudges · attention budget</h2><div className="ns-err">{err}</div></section>;
  if (!s) return <section className="ns-panel"><h2>Kate nudges · attention budget</h2><div className="ec-sub">Replaying the policy…</div></section>;

  const within = s.max_non_urgent_any_7d <= s.budget_default;
  const maxTier = Math.max(1, ...s.by_tier.map((t) => t.candidates));
  return (
    <section className="ns-panel">
      <h2>Kate nudges · attention budget ({s.customers} customers, last {s.weeks} weeks)</h2>
      <div className="ns-kpis">
        <div className="ns-kpi"><b>{s.pushes_per_customer_week.toFixed(2).replace(".", ",")}</b><span>pushes per customer per week</span></div>
        <div className={`ns-kpi ${within ? "ok" : "warn"}`}><b>{s.max_non_urgent_any_7d} / {s.budget_default}</b><span>most non-urgent pushes in any 7 days</span></div>
        <div className="ns-kpi ok"><b>{Math.round(s.noise_avoided_pct)}%</b><span>noise avoided vs. pushing every card ({s.naive_pushes} → {s.pushes})</span></div>
        <div className="ns-kpi"><b>{pct(s.open_rate)}</b><span>open rate · mute {pct(s.mute_rate)} · dismiss {pct(s.dismiss_rate)}</span></div>
      </div>
      <div className="ns-two">
        <table className="ns-table">
          <thead><tr><th>Tier</th><th>Candidates</th><th>Pushed</th><th>Held</th></tr></thead>
          <tbody>
            {s.by_tier.map((t) => (
              <tr key={t.tier}>
                <td>{TIER_LABEL[t.tier]}</td>
                <td><span className="ns-bar" style={{ width: `${(t.candidates / maxTier) * 60}px` }} />{t.candidates}</td>
                <td>{t.pushed}</td>
                <td>{t.held}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <table className="ns-table">
          <thead><tr><th>Customer</th><th>Pushes</th><th>Urgent</th><th>Held</th><th>Max/7d</th></tr></thead>
          <tbody>
            {s.per_customer.slice(0, 8).map((c, i) => (
              <tr key={`${c.label}-${i}`}>
                <td>{c.label}{c.persona === "retiree" ? " (retiree)" : ""}</td>
                <td>{c.pushes}</td>
                <td>{c.urgent}</td>
                <td>{c.held}</td>
                <td>{c.max_non_urgent_7d} / {c.budget}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="ns-rules">{s.rules.map((r) => <li key={r}>{r}</li>)}</ul>
    </section>
  );
}
