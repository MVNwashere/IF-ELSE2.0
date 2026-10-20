// One goal as a checklist: every step shows who does it, why them, what it wins, and what came back.
import { motion } from "framer-motion";
import { longDate } from "../format";
import { useEur } from "../privacy";
import Sheet from "../ui/Sheet";
import { hours, KindBadge, ProductChips, ProgressRing, StatusPill } from "./bits";
import { useState } from "react";
import type { Goal, MeasuredOutcome, StallAnswer, Step, WinTotals } from "./types";

interface Props {
  goal: Goal;
  busy: boolean;
  onReview: (step: Step) => void;
  onReset: (step: Step) => void;
  onPassport: () => void;
  onCancel: () => void;
  onClose: () => void;
  onConnectSource?: (sourceId: string) => void;
  onStartNext?: (playbookId: string) => void;
  onInvite?: (username: string) => void;
  onStall?: (answer: StallAnswer) => void;
}

const STALL_LABEL: Record<"keep" | "pause" | "stop", string> = { keep: "Keep going", pause: "Pause it", stop: "Stop it" };

/** Shared with a household member: who is in, and a way to invite one (owner only, shareable goals). */
function Household({ goal, busy, onInvite }: { goal: Goal; busy: boolean; onInvite?: (username: string) => void }) {
  const [name, setName] = useState("");
  const members = goal.household ?? [];
  if (!members.length && (!onInvite || goal.role === "member")) return null;
  return (
    <div className="eco-household" aria-label="Household">
      {members.length > 0 && (
        <p className="muted-note">
          👥 Shared goal: {members.map((m) => `${m.you ? "you" : m.first_name}${m.status === "invited" ? " (invited)" : ""}`).join(" & ")}.
          {" "}Steps that share data with a partner need everyone's OK.
        </p>
      )}
      {onInvite && goal.role !== "member" && goal.status === "active" && (
        <form className="eco-invite" onSubmit={(e) => { e.preventDefault(); if (name.trim()) { onInvite(name.trim().toLowerCase()); setName(""); } }}>
          <input aria-label="Username of your partner" placeholder="Share with your partner (username)" value={name}
            maxLength={40} pattern="[a-z0-9_]{2,40}" onChange={(e) => setName(e.target.value)} />
          <button type="submit" className="btn-ghost small" disabled={busy || !name.trim()}>Invite</button>
        </form>
      )}
    </div>
  );
}

/** Journey step 5: what KBC verified in your own transactions, next to what was estimated. */
function Measured({ items }: { items: MeasuredOutcome[] }) {
  const eur = useEur();
  if (!items.length) return null;
  const verified = items.filter((m) => m.status === "verified");
  const verifiedEur = verified.reduce((n, m) => n + (m.unit.startsWith("€") ? m.measured_eur ?? 0 : 0), 0);
  const estimatedEur = items.reduce((n, m) => n + (m.estimate_eur ?? 0), 0);
  return (
    <div className="eco-measured" aria-label="Measured outcome">
      <div className="eco-measured-h">
        {verified.length > 0
          ? <><span className="eco-pill done">✓ Verified</span>{verifiedEur > 0 ? <b>{eur(verifiedEur)} saved or received</b> : <b>Outcome confirmed</b>}</>
          : <><span className="eco-pill proposed">Estimated</span><b>{estimatedEur > 0 ? `${eur(estimatedEur)} expected` : "Waiting for your data"}</b></>}
        {verified.length > 0 && estimatedEur > 0 && <small> · estimated {eur(estimatedEur)}</small>}
      </div>
      <ul>
        {items.map((m) => (
          <li key={m.metric} className={`eco-measured-row ${m.status}`}>
            <span className={`eco-pill ${m.status === "verified" ? "done" : m.status === "pending" ? "proposed" : "blocked"}`}>
              {m.status === "verified" ? "verified" : m.status === "pending" ? "pending" : "not met"}
            </span>
            <span><b>{m.label}.</b> {m.summary}{m.check_on && m.status === "pending" ? ` (${longDate(m.check_on)})` : ""}</span>
            {m.evidence.length > 0 && <small className="muted-note">{m.evidence.join(" · ")}</small>}
          </li>
        ))}
      </ul>
      <div className="eco-assume">Measured from your own transactions after the steps were done. Synthetic data.</div>
    </div>
  );
}

function TripleWin({ outcome, potential }: { outcome: WinTotals; potential: WinTotals }) {
  const eur = useEur();
  const rows = [
    { who: "You", now: `${eur(outcome.customer_eur)} · ${hours(outcome.hours_saved)}`, max: `${eur(potential.customer_eur)} · ${hours(potential.hours_saved)}`, frac: potential.customer_eur + potential.hours_saved > 0 ? (outcome.customer_eur + outcome.hours_saved) / (potential.customer_eur + potential.hours_saved) : 0 },
    { who: "KBC", now: eur(outcome.kbc_revenue_eur), max: eur(potential.kbc_revenue_eur), frac: potential.kbc_revenue_eur > 0 ? outcome.kbc_revenue_eur / potential.kbc_revenue_eur : 0 },
    { who: "Partners", now: eur(outcome.partner_fees_eur), max: eur(potential.partner_fees_eur), frac: potential.partner_fees_eur > 0 ? outcome.partner_fees_eur / potential.partner_fees_eur : 0 },
  ];
  return (
    <div className="eco-triple" aria-label="Triple win">
      <div className="eco-triple-h">Triple win · realised <span>of potential</span></div>
      {rows.map((r) => (
        <div key={r.who} className="eco-triple-row">
          <span className="who">{r.who}</span>
          <span className="bar"><motion.i initial={{ width: 0 }} animate={{ width: `${Math.round(r.frac * 100)}%` }} /></span>
          <span className="val"><b>{r.now}</b> <small>/ {r.max}</small></span>
        </div>
      ))}
      <div className="eco-assume">Illustrative estimates.</div>
    </div>
  );
}

function StepRow({ step, busy, onReview, onReset, onConnect }: { step: Step; busy: boolean; onReview: () => void; onReset: () => void; onConnect?: (id: string) => void }) {
  const eur = useEur();
  const held = step.already_held;
  const win = [step.estimates.customer_eur > 0 ? `${eur(step.estimates.customer_eur)} for you` : "", step.estimates.hours_saved > 0 ? hours(step.estimates.hours_saved) + " saved" : ""].filter(Boolean).join(" · ");
  return (
    <li className={`eco-step ${step.status} ${held ? "held" : ""}`}>
      <span className="eco-dot" aria-hidden="true">{step.status === "done" ? "✓" : step.order}</span>
      <div className="eco-step-body">
        <div className="eco-step-top">
          <b>{step.title}</b>
          <StatusPill status={step.status} held={held} />
        </div>
        <div className="eco-provider">
          <span>{step.provider.name}</span>
          <KindBadge provider={step.provider} />
        </div>
        {!held && step.why_this_provider && <p className="eco-whyp">{step.why_this_provider}</p>}
        <ProductChips products={step.products} />
        {!held && win && <div className="eco-steps-win">{win}</div>}
        {step.status === "in_progress" && (
          <div className="eco-waiting"><i className="eco-spin" aria-hidden="true" />Waiting for {step.provider.name}…</div>
        )}
        {step.result && step.status === "done" && !held && (
          <motion.div className="eco-result" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
            <span className="from">{step.provider.kind === "partner" ? `${step.provider.name} replied` : "KBC"}</span>
            {step.result}
          </motion.div>
        )}
        {step.status === "blocked" && (
          <p className="eco-blocked">{step.fallback ? step.fallback.message : "You revoked access. Approve again to continue."}</p>
        )}
        {step.joint && (step.waiting_for?.length ?? 0) > 0 && (step.approved_by?.length ?? 0) > 0 && (
          <div className="eco-waiting">👥 Waiting for {step.waiting_for!.join(" and ")} to approve. Nothing is shared until then.</div>
        )}
        {step.source_hint && !held && (
          step.source_hint.connected
            ? <div className="eco-source-hint ok">🔌 Using {step.source_hint.name} (connected with your OK)</div>
            : (
              <button type="button" className="eco-source-hint" disabled={busy || !onConnect} onClick={() => onConnect?.(step.source_hint!.source_id)}>
                🔌 {step.source_hint.prompt}
              </button>
            )
        )}
        <div className="eco-step-actions">
          {(step.status === "proposed" || step.status === "blocked") && (
            <button type="button" className="btn-primary small" disabled={busy} onClick={onReview}>
              {step.provider.kind === "advisor" ? "Book a meeting"
                : step.fallback?.partner_name ? `Review ${step.fallback.partner_name}`
                : step.alternatives && step.alternatives.length > 1 ? "Compare & approve" : "Review & approve"}
            </button>
          )}
          {step.status === "declined" && (
            <button type="button" className="btn-ghost small" disabled={busy} onClick={onReset}>Reconsider</button>
          )}
        </div>
      </div>
    </li>
  );
}

export default function JourneySheet({ goal, busy, onReview, onReset, onPassport, onCancel, onClose, onConnectSource, onStartNext, onInvite, onStall }: Props) {
  const steps = [...goal.steps].sort((a, b) => a.order - b.order);
  const measured = goal.measured ?? [];
  return (
    <Sheet full title={<span className="eco-sheet-title"><span aria-hidden="true">{goal.icon}</span>{goal.title}</span>} onClose={onClose}>
      <div className="eco-journey-head">
        <ProgressRing done={goal.progress.done} total={goal.progress.total} size={64} />
        <div>
          <p className="eco-tagline">{goal.tagline}</p>
          <p className="muted-note">
            {goal.origin === "detected" ? "Spotted by KBC" : "Your goal"} · started {longDate(goal.created_on)}
            {goal.target_date ? ` · target ${longDate(goal.target_date)}` : ""}
          </p>
        </div>
      </div>
      {goal.status === "completed" && goal.next_goal && onStartNext && (
        <div className="eco-next-goal">
          <span>🎉 Goal reached. <b>Next: {goal.next_goal_title ?? goal.next_goal}</b></span>
          <button type="button" className="btn-primary small" disabled={busy} onClick={() => onStartNext(goal.next_goal!)}>Start</button>
        </div>
      )}
      {goal.stall && onStall && (
        <div className="eco-next-goal" role="status">
          <span>{goal.stall.question}</span>
          <span className="eco-stall-actions">
            {goal.stall.options.filter((o) => o !== "stop" || goal.role !== "member").map((o) => (
              <button key={o} type="button" className={o === "keep" ? "btn-primary small" : "btn-ghost small"} disabled={busy}
                onClick={() => onStall(o)}>{STALL_LABEL[o]}</button>
            ))}
          </span>
        </div>
      )}
      {goal.paused && (
        <div className="eco-next-goal">
          <span>⏸ Paused: no reminders until you pick it up again.</span>
          {onStall && <button type="button" className="btn-ghost small" disabled={busy} onClick={() => onStall("resume")}>Resume</button>}
        </div>
      )}
      <Household goal={goal} busy={busy} onInvite={onInvite} />
      <Measured items={measured} />
      <TripleWin outcome={goal.outcome} potential={goal.potential} />
      <ol className="eco-steps">
        {steps.map((s) => (
          <StepRow key={s.step_id} step={s} busy={busy} onReview={() => onReview(s)} onReset={() => onReset(s)} onConnect={onConnectSource} />
        ))}
      </ol>
      {goal.evidence.length > 0 && (
        <div className="eco-evidence small">
          <div className="eco-evidence-h">Why this goal</div>
          <ul>{goal.evidence.map((e, i) => <li key={i}>{e}</li>)}</ul>
        </div>
      )}
      <div className="eco-journey-foot">
        <button type="button" className="btn-ghost" onClick={onPassport}>🔐 Consent passport</button>
        {goal.status === "active" && goal.role !== "member" && <button type="button" className="link danger" onClick={onCancel}>Stop this goal</button>}
      </div>
    </Sheet>
  );
}
