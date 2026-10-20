// One goal as a checklist: every step shows who does it, why them, what it wins, and what came back.
import { motion } from "framer-motion";
import { longDate } from "../format";
import { useEur } from "../privacy";
import Sheet from "../ui/Sheet";
import { hours, KindBadge, ProductChips, ProgressRing, StatusPill } from "./bits";
import type { Goal, Step, WinTotals } from "./types";

interface Props {
  goal: Goal;
  busy: boolean;
  onReview: (step: Step) => void;
  onReset: (step: Step) => void;
  onPassport: () => void;
  onCancel: () => void;
  onClose: () => void;
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

function StepRow({ step, busy, onReview, onReset }: { step: Step; busy: boolean; onReview: () => void; onReset: () => void }) {
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
        {step.status === "blocked" && <p className="eco-blocked">You revoked access. Approve again to continue.</p>}
        <div className="eco-step-actions">
          {(step.status === "proposed" || step.status === "blocked") && (
            <button type="button" className="btn-primary small" disabled={busy} onClick={onReview}>Review &amp; approve</button>
          )}
          {step.status === "declined" && (
            <button type="button" className="btn-ghost small" disabled={busy} onClick={onReset}>Reconsider</button>
          )}
        </div>
      </div>
    </li>
  );
}

export default function JourneySheet({ goal, busy, onReview, onReset, onPassport, onCancel, onClose }: Props) {
  const steps = [...goal.steps].sort((a, b) => a.order - b.order);
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
      <TripleWin outcome={goal.outcome} potential={goal.potential} />
      <ol className="eco-steps">
        {steps.map((s) => (
          <StepRow key={s.step_id} step={s} busy={busy} onReview={() => onReview(s)} onReset={() => onReset(s)} />
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
        {goal.status === "active" && <button type="button" className="link danger" onClick={onCancel}>Stop this goal</button>}
      </div>
    </Sheet>
  );
}
