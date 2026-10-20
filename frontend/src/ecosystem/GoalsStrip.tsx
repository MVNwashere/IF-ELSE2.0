// Top of the home: active goals (tap → journey) and what KBC noticed (explainable, nothing happens until Start).
import { AnimatePresence, motion } from "framer-motion";
import { pct } from "../format";
import { ProgressRing, useWinLine } from "./bits";
import type { Goal, GoalCandidate, GoalsResponse } from "./types";

interface Props {
  data: GoalsResponse;
  hidden: Set<string>;
  busy: boolean;
  onOpenGoal: (goalId: number) => void;
  onStart: (playbookId: string) => void;
  onHide: (playbookId: string) => void;
  onPlaybooks: () => void;
  onPassport: () => void;
  onAnswerInvite?: (goalId: number, accept: boolean) => void;
}

function GoalTile({ goal, onOpen }: { goal: Goal; onOpen: () => void }) {
  const next = goal.steps.find((s) => s.status === "in_progress") ?? goal.steps.find((s) => s.status === "proposed" || s.status === "blocked");
  const waiting = next?.status === "in_progress";
  return (
    <button type="button" className="eco-goal" onClick={onOpen}>
      <span className="eco-goal-icon" aria-hidden="true">{goal.icon}</span>
      <span className="eco-goal-text">
        <b>{goal.title}</b>
        <span>{goal.status === "completed" ? "Completed 🎉" : goal.paused ? "Paused" : `${goal.progress.done} of ${goal.progress.total} steps done`}
          {goal.role === "member" ? " · shared with you" : ""}</span>
        {next && (
          <span className={`eco-next ${waiting ? "waiting" : ""}`}>
            {waiting && <i className="eco-spin" aria-hidden="true" />}
            {waiting ? `Waiting for ${next.provider.name}…` : `Next: ${next.title}`}
          </span>
        )}
      </span>
      <ProgressRing done={goal.progress.done} total={goal.progress.total} />
    </button>
  );
}

function CandidateCard({ c, busy, onStart, onHide }: { c: GoalCandidate; busy: boolean; onStart: () => void; onHide: () => void }) {
  const win = useWinLine()(c.potential);
  return (
    <motion.div className="eco-candidate" layout initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, scale: 0.96 }}>
      <div className="eco-cand-top">
        <span className="eco-noticed">KBC noticed…</span>
        <span className="eco-conf" title="How sure KBC is about this">{pct(c.confidence)} sure</span>
      </div>
      <h3><span aria-hidden="true">{c.icon}</span> {c.title}</h3>
      <p className="eco-why">{c.why_now}</p>
      <div className="eco-evidence">
        <div className="eco-evidence-h">Why we think so</div>
        <ul>{c.evidence.map((e, i) => <li key={i}>{e}</li>)}</ul>
      </div>
      {c.partners_preview.length > 0 && (
        <div className="eco-chips">
          {c.partners_preview.map((p) => <span key={p} className="eco-chip">{p}</span>)}
        </div>
      )}
      {win && <div className="eco-win">Potential win: <b>{win}</b></div>}
      <div className="eco-cand-actions">
        <button type="button" className="btn-primary" disabled={busy} onClick={onStart}>Let KBC take care of it</button>
        <button type="button" className="btn-ghost" onClick={onHide}>Not now</button>
      </div>
    </motion.div>
  );
}

export default function GoalsStrip({ data, hidden, busy, onOpenGoal, onStart, onHide, onPlaybooks, onPassport, onAnswerInvite }: Props) {
  const candidates = data.candidates.filter((c) => !hidden.has(c.playbook_id));
  return (
    <section className="eco-strip" aria-label="Your goals">
      <div className="eco-strip-head">
        <h2>Your goals</h2>
        <button type="button" className="link" onClick={onPassport}>Who sees my data?</button>
      </div>
      {onAnswerInvite && (data.invitations ?? []).map((i) => (
        <div key={i.goal_id} className="eco-candidate">
          <h3><span aria-hidden="true">{i.icon}</span> {i.from_name} shared “{i.title}” with you</h3>
          <p className="eco-why">Join to follow the steps together. Steps that share data with a partner will need your OK too.</p>
          <div className="eco-cand-actions">
            <button type="button" className="btn-primary" disabled={busy} onClick={() => onAnswerInvite(i.goal_id, true)}>Join</button>
            <button type="button" className="btn-ghost" disabled={busy} onClick={() => onAnswerInvite(i.goal_id, false)}>No thanks</button>
          </div>
        </div>
      ))}
      {data.goals.map((g) => <GoalTile key={g.goal_id} goal={g} onOpen={() => onOpenGoal(g.goal_id)} />)}
      <AnimatePresence initial={false}>
        {candidates.map((c) => (
          <CandidateCard key={c.playbook_id} c={c} busy={busy} onStart={() => onStart(c.playbook_id)} onHide={() => onHide(c.playbook_id)} />
        ))}
      </AnimatePresence>
      <button type="button" className="eco-add" onClick={onPlaybooks}>+ Start a goal</button>
    </section>
  );
}
