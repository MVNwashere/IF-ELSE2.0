// The Goals tab: what's in motion and every goal available to start. Tap a goal for its roadmap.
import { maskText, useEur, useMasked } from "../privacy";
import { hours, useWinLine } from "./bits";
import type { Goal, GoalCandidate, GoalsResponse, PlaybookSummary } from "./types";

interface Props {
  data: GoalsResponse | null;
  hidden: Set<string>;
  onOpenGoal: (goalId: number) => void;
  onPreview: (goal: GoalCandidate | PlaybookSummary) => void;
}

function nextStep(goal: Goal) {
  return goal.steps.find((s) => s.status === "in_progress")
    ?? goal.steps.find((s) => s.status === "proposed" || s.status === "blocked");
}

export default function GoalsScreen({ data, hidden, onOpenGoal, onPreview }: Props) {
  const masked = useMasked();
  const eur = useEur();
  const winLine = useWinLine();
  if (!data) return <div className="gs-empty">Loading your goals…</div>;

  const live = data.goals.filter((g) => g.status === "active");
  const achieved = data.goals.filter((g) => g.status === "completed");
  const suggested = data.candidates.filter((c) => !hidden.has(c.playbook_id) && !live.some((g) => g.playbook_id === c.playbook_id));
  const taken = new Set([...data.goals.filter((g) => g.status !== "cancelled").map((g) => g.playbook_id), ...suggested.map((c) => c.playbook_id)]);
  const explore = data.playbooks.filter((p) => !taken.has(p.playbook_id));
  const done = data.goals.reduce((n, g) => n + g.progress.done, 0);
  const total = data.goals.reduce((n, g) => n + g.progress.total, 0);
  const saved = data.goals.reduce((n, g) => n + g.outcome.customer_eur, 0);
  const time = data.goals.reduce((n, g) => n + g.outcome.hours_saved, 0);
  const potential = suggested[0] ? winLine(suggested[0].potential) : "";
  const steps = (id: string, fallback: number) => data.playbooks.find((p) => p.playbook_id === id)?.steps ?? fallback;

  return (
    <div className="goals-screen">
      <section className="gs-hero" aria-label="Goals overview">
        <span className="gs-hero-ball" aria-hidden="true" />
        <svg className="gs-hero-wave" viewBox="0 0 360 100" preserveAspectRatio="none" aria-hidden="true">
          <path d="M0 52 C70 40 130 24 200 13 C260 5 320 3 360 2 V100 H0Z" />
        </svg>
        <span className="gs-eyebrow">LET’S MAKE IT HAPPEN</span>
        <h2>Your goals</h2>
        <p>{live.length
          ? `KBC handles the paperwork. You approve every step.`
          : potential ? `Pick a goal to get started. The top suggestion could mean ${potential}.` : "Pick a goal. KBC lines up every step for you."}</p>
        <div className="gs-stats">
          <div><b>{live.length}</b><span>In motion</span></div>
          <div><b>{total ? <>{done}<small>/{total}</small></> : "—"}</b><span>Steps done</span></div>
          <div><b>{saved > 0 ? eur(saved) : time > 0 ? hours(time) : "—"}</b><span>{saved > 0 ? "Saved so far" : "Time saved"}</span></div>
        </div>
      </section>

      {live.length > 0 && <section className="gs-section" aria-label="In motion">
        <h3>In motion</h3>
        {live.map((goal) => {
          const next = nextStep(goal);
          const pct = goal.progress.total ? goal.progress.done / goal.progress.total * 100 : 0;
          const needsYou = next?.status === "proposed";
          return (
            <button type="button" key={goal.goal_id} className="gs-goal" onClick={() => onOpenGoal(goal.goal_id)}>
              <span className="gs-icon" aria-hidden="true">{goal.icon}</span>
              <span className="gs-goal-body">
                <span className="gs-goal-top"><b>{maskText(goal.title, masked)}</b><span>{goal.progress.done} of {goal.progress.total}</span></span>
                <span className="gs-bar" aria-hidden="true"><span style={{ width: `${pct}%` }} /></span>
                {next && <span className={`gs-next${needsYou ? " needs-you" : ""}`}>
                  {needsYou ? "Your approval needed" : next.status === "in_progress" ? "In progress" : "Next"}: {maskText(next.title, masked)}
                </span>}
              </span>
              <span className="gs-chevron" aria-hidden="true">›</span>
            </button>
          );
        })}
      </section>}

      <section className="gs-section" aria-label="Available goals">
        <h3>Available goals</h3>
        {suggested.length + explore.length === 0 && <p className="gs-empty">You’ve started every goal we offer. Nice work.</p>}
        {suggested.map((c) => (
          <button type="button" key={c.playbook_id} className="gs-option suggested" onClick={() => onPreview(c)}>
            <span className="gs-icon" aria-hidden="true">{c.icon}</span>
            <span className="gs-option-body">
              <span className="gs-badge">Suggested for you</span>
              <b>{maskText(c.title, masked)}</b>
              <span>{maskText(c.why_now, masked)}</span>
              <small>{winLine(c.potential) ? `${winLine(c.potential)} · ` : ""}{steps(c.playbook_id, c.steps_preview.length)} steps</small>
            </span>
            <span className="gs-chevron" aria-hidden="true">›</span>
          </button>
        ))}
        {explore.map((p) => (
          <button type="button" key={p.playbook_id} className="gs-option" onClick={() => onPreview(p)}>
            <span className="gs-icon" aria-hidden="true">{p.icon}</span>
            <span className="gs-option-body">
              <b>{p.title}</b>
              <span>{p.tagline}</span>
              <small>{p.steps} steps</small>
            </span>
            <span className="gs-chevron" aria-hidden="true">›</span>
          </button>
        ))}
      </section>

      {achieved.length > 0 && <section className="gs-section" aria-label="Achieved">
        <h3>Achieved</h3>
        {achieved.map((goal) => (
          <button type="button" key={goal.goal_id} className="gs-goal achieved" onClick={() => onOpenGoal(goal.goal_id)}>
            <span className="gs-icon" aria-hidden="true">{goal.icon}</span>
            <span className="gs-goal-body"><b>{maskText(goal.title, masked)}</b><span className="gs-next">✓ {winLine(goal.outcome) || "Completed"}</span></span>
            <span className="gs-chevron" aria-hidden="true">›</span>
          </button>
        ))}
      </section>}
    </div>
  );
}
