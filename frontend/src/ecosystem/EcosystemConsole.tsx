// KBC ecosystem console (advisor role): goal funnel, partner network, live partner events, triple win at scale.
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { eur } from "../format";
import { eco } from "./client";
import type { EcosystemOverview, EventRow, FunnelRow, LearningRow, OutcomeSummary, PartnerRow, RuleRow, SimMode, WinTotals } from "./types";
import "./eco.css";
import NudgeStatsPanel from "../nudges/NudgeStatsPanel";

interface Props { username: string; onLogout: () => void; onSwitchCustomer: (u: string) => void }

const POLL_MS = 2000;
const nf = new Intl.NumberFormat("nl-BE");

function big(n: number): string {
  if (Math.abs(n) >= 1e9) return `${(n / 1e9).toFixed(1).replace(".", ",")} bn`;
  if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(1).replace(".", ",")} M`;
  return nf.format(Math.round(n));
}

const SHARE_LABEL: Record<string, string> = {
  lead_fee: "Lead fee", revenue_share: "Revenue share", fee_per_completed_step: "Fee per completed step", subscription: "Subscription",
};

function shareText(p: PartnerRow): string {
  const v = p.value_share;
  const amt = v.model === "revenue_share" ? `${Math.round(v.pct * 1000) / 10}%` : eur(v.amount_eur);
  return `${SHARE_LABEL[v.model] ?? v.model} · ${amt}${v.note ? ` · ${v.note}` : ""}`;
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return <div className="ec-stat"><b>{value}</b><span>{label}</span>{sub && <small>{sub}</small>}</div>;
}

function Funnel({ rows }: { rows: FunnelRow[] }) {
  return (
    <table className="ec-table">
      <thead><tr><th>Goal</th><th>Detected</th><th>Started</th><th>Steps done</th><th>Completed</th><th>At 2.3M customers</th></tr></thead>
      <tbody>
        {rows.map((r) => {
          const max = Math.max(1, r.detected);
          const cell = (n: number) => (
            <td><span className="ec-num">{nf.format(n)}</span><span className="ec-bar"><i style={{ width: `${Math.min(100, (n / max) * 100)}%` }} /></span></td>
          );
          return (
            <tr key={r.playbook_id}>
              <td className="ec-goal"><span aria-hidden="true">{r.icon}</span> {r.title}</td>
              {cell(r.detected)}{cell(r.started)}{cell(r.steps_done)}{cell(r.completed)}
              <td className="ec-proj">{big(r.projected_2_3m)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

const rate = (x: number | null | undefined) => (x == null ? "—" : `${Math.round(x * 100)}%`);

function Learning({ rows, rules }: { rows: LearningRow[]; rules: RuleRow[] }) {
  return (
    <>
      <table className="ec-table">
        <thead><tr><th>Goal</th><th>Rule hit rate</th><th>Avg. confidence</th><th>Shown</th><th>Started</th><th>Completed</th><th>Shown → started</th><th>Started → completed</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.playbook_id}>
              <td className="ec-goal"><span aria-hidden="true">{r.icon}</span> {r.title}</td>
              <td>{rate(r.hit_rate)} <span className="ec-sub">({nf.format(r.detected)})</span></td>
              <td>{rate(r.avg_confidence)}</td>
              <td>{nf.format(r.shown)}</td>
              <td>{nf.format(r.started)}</td>
              <td>{nf.format(r.completed)}</td>
              <td><b>{rate(r.start_rate)}</b></td>
              <td><b>{rate(r.completion_rate)}</b></td>
            </tr>
          ))}
        </tbody>
      </table>
      {rules.length > 0 && (
        <details className="ec-rules">
          <summary>Detection rules: how often each signal fires</summary>
          <table className="ec-table">
            <thead><tr><th>Goal</th><th>Signal (evidence pattern)</th><th>Hits</th><th>Hit rate</th></tr></thead>
            <tbody>
              {rules.map((r, i) => (
                <tr key={`${r.playbook_id}-${i}`}><td className="ec-sub">{r.playbook_id.replace(/_/g, " ")}</td><td>{r.rule}</td><td>{nf.format(r.hits)}</td><td>{rate(r.hit_rate)}</td></tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </>
  );
}

function Outcomes({ o }: { o: OutcomeSummary }) {
  return (
    <div className="ec-triple">
      <div><span>Verified outcomes</span><b>{nf.format(o.verified)}</b><small>{eur(o.verified_eur)} measured vs {eur(o.estimated_eur_for_verified)} estimated</small></div>
      <div><span>Pending checks</span><b>{nf.format(o.pending)}</b><small>KBC looks again on the date set</small></div>
      <div><span>Not met</span><b>{nf.format(o.not_met)}</b><small>advisor follows up</small></div>
    </div>
  );
}

const SIM_MODES: SimMode[] = ["done", "late", "reject", "fail", "timeout"];

function Partners({ rows, onSim }: { rows: PartnerRow[]; onSim?: (partnerId: string, mode: SimMode) => void }) {
  return (
    <table className="ec-table">
      <thead><tr><th>Partner</th><th>Value share</th><th>Leads</th><th>Completed</th><th>Fees paid</th><th>Avg. response</th><th>SLA missed</th><th>Rejected</th><th>Live outcome</th><th>Demo</th></tr></thead>
      <tbody>
        {rows.map((p) => (
          <tr key={p.partner_id}>
            <td><b>{p.name}</b><div className="ec-sub">{p.ecosystems.join(" · ")}</div></td>
            <td className="ec-sub">{shareText(p)}</td>
            <td>{nf.format(p.leads)}</td>
            <td>{nf.format(p.completed)}</td>
            <td>{eur(p.fees_eur)}</td>
            <td>{p.avg_response_s == null ? "—" : `${p.avg_response_s.toFixed(1)} s`}</td>
            <td>{nf.format(p.sla_misses ?? 0)}{p.demoted ? <div className="ec-sub">ranked lower</div> : null}</td>
            <td>{nf.format(p.rejections ?? 0)}</td>
            <td>{p.outcome_rate_live == null ? "—" : `${Math.round(p.outcome_rate_live * 100)}%`}</td>
            <td>
              <select aria-label={`How ${p.name} answers in the demo`} value={p.sim_mode ?? "done"}
                onChange={(e) => onSim?.(p.partner_id, e.target.value as SimMode)}>
                {SIM_MODES.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function timeOf(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString("nl-BE", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function Events({ rows }: { rows: EventRow[] }) {
  if (!rows.length) return <p className="ec-sub">No partner traffic yet. Approve a partner step in the customer app.</p>;
  return (
    <ul className="ec-events">
      <AnimatePresence initial={false}>
        {rows.slice(0, 30).map((e) => (
          <motion.li key={`${e.at}-${e.partner_id}-${e.kind}-${e.summary}`} layout initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }}>
            <span className="ec-time">{timeOf(e.at)}</span>
            <span className={`ec-kind ${e.kind === "outbound" ? "out" : e.kind}`}>{e.kind === "outbound" ? "KBC → partner" : `webhook · ${e.kind}`}</span>
            {e.kind !== "outbound" && (e.verified ? <span className="ec-verified" title="HMAC signature verified">✓ verified</span> : <span className="ec-unverified">unverified</span>)}
            <span className="ec-summary">{e.summary}</span>
          </motion.li>
        ))}
      </AnimatePresence>
    </ul>
  );
}

function Triple({ realised }: { realised: WinTotals }) {
  return (
    <div className="ec-triple">
      <div><span>Customers</span><b>{eur(realised.customer_eur)}</b><small>{nf.format(Math.round(realised.hours_saved))} hours saved</small></div>
      <div><span>KBC</span><b>{eur(realised.kbc_revenue_eur)}</b><small>{realised.kbc_products.length} products · yearly margin</small></div>
      <div><span>Partners</span><b>{eur(realised.partner_fees_eur)}</b><small>{realised.partner_leads} leads</small></div>
    </div>
  );
}

const PROJ_LABEL: Record<string, string> = {
  customer_eur: "Customer value", hours_saved: "Hours saved", kbc_revenue_eur: "KBC revenue", partner_fees_eur: "Partner fees",
};

export default function EcosystemConsole({ username, onLogout, onSwitchCustomer }: Props) {
  const [data, setData] = useState<EcosystemOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try { const d = await eco.overview(); if (alive) { setData(d); setError(null); } } catch (e) { if (alive) setError(e instanceof Error ? e.message : String(e)); }
    };
    void tick();
    const t = window.setInterval(() => void tick(), POLL_MS);
    return () => { alive = false; window.clearInterval(t); };
  }, []);

  return (
    <div className="ec">
      <header className="ec-head">
        <div>
          <h1>KBC Ecosystem Console</h1>
          <p>From intent to impact: every goal, partner and webhook across the network. Synthetic data.</p>
        </div>
        <div className="ec-head-tools">
          <span className="ec-live"><i /> live</span>
          <button type="button" className="pbtn small" onClick={() => onSwitchCustomer("lotte")}>Open customer app (Lotte)</button>
          <button type="button" className="pbtn small" onClick={onLogout}>Log out {username}</button>
        </div>
      </header>
      {error && <div className="ec-error">{error}</div>}
      {!data ? <p className="ec-sub">Loading…</p> : (
        <>
          <div className="ec-stats">
            <Stat label="KBC building blocks in the catalogue" value={nf.format(data.catalogue_items)} />
            <Stat label="Ecosystems" value={nf.format(data.ecosystems)} />
            <Stat label="Building blocks used by goals" value={nf.format(data.building_blocks_used)} />
            <Stat label="Vetted partners" value={nf.format(data.partners)} sub={`portfolio scored in ${data.scoring_ms.toFixed(0)} ms`} />
          </div>
          <div className="ec-grid">
            <div className="ec-main">
              <section className="ec-card">
                <h2>Goal funnel</h2>
                <Funnel rows={data.funnel} />
              </section>
              {data.learning && data.learning.length > 0 && (
                <section className="ec-card">
                  <h2>Learning loop</h2>
                  <Learning rows={data.learning} rules={data.rules ?? []} />
                </section>
              )}
              <NudgeStatsPanel />
              <section className="ec-card">
                <h2>Partner network · live scorecard</h2>
                <Partners rows={data.partner_rows} onSim={(pid, mode) => {
                  void eco.simulatePartner(pid, mode).catch((e) => setError(e instanceof Error ? e.message : String(e)));
                }} />
                <p className="ec-sub">Demo: choose how a simulated partner answers. A partner that misses its SLA twice is ranked
                  below partners that answer (never by fee); the customer is offered the next partner and approves again.</p>
              </section>
              <section className="ec-card">
                <h2>Triple win · realised so far</h2>
                <Triple realised={data.realised} />
                {data.outcomes && (
                  <>
                    <h2 className="ec-h2-gap">Measured outcomes · realised vs estimated</h2>
                    <Outcomes o={data.outcomes} />
                  </>
                )}
                <h2 className="ec-h2-gap">Projected to 2.3M customers</h2>
                <div className="ec-proj-row">
                  {Object.entries(data.projection).map(([k, v]) => (
                    <div key={k}>
                      <span>{PROJ_LABEL[k] ?? k.replace(/_/g, " ")}</span>
                      <b>{k.endsWith("_eur") ? `€${big(v)}` : big(v)}</b>
                    </div>
                  ))}
                </div>
                <div className="ec-assume">
                  <b>Illustrative assumptions</b>
                  <ul>{data.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
                </div>
              </section>
            </div>
            <aside className="ec-card ec-feed">
              <h2>Live partner events</h2>
              <Events rows={data.events} />
            </aside>
          </div>
        </>
      )}
    </div>
  );
}
