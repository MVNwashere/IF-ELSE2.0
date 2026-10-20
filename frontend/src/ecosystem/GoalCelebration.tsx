// The moment a goal is reached: what it delivered, in money and time, and what could come next. Step 5 of the engine
// ("Deliver a measurable outcome") made visible.
import { motion } from "framer-motion";
import { useEur } from "../privacy";
import { hours } from "./bits";
import type { Goal } from "./types";

const CONFETTI = ["#00aeef", "#0d6fb8", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6"];

interface Props {
  goal: Goal;
  onClose: () => void;
  onOpen: () => void;
  onStartNext?: (playbookId: string) => void;
}

export default function GoalCelebration({ goal, onClose, onOpen, onStartNext }: Props) {
  const eur = useEur();
  const verified = (goal.measured ?? []).filter((m) => m.status === "verified" && m.measured_eur);
  const verifiedEur = verified.reduce((n, m) => n + (m.measured_eur ?? 0), 0);
  const money = verifiedEur || goal.outcome.customer_eur;
  return (
    <motion.div className="celebrate" role="dialog" aria-modal="true" aria-label={`Goal reached: ${goal.title}`}
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <div className="celebrate-confetti" aria-hidden="true">
        {Array.from({ length: 28 }, (_, i) => (
          <i key={i} style={{ left: `${(i * 37) % 100}%`, background: CONFETTI[i % CONFETTI.length],
            animationDelay: `${(i % 7) * 0.12}s`, animationDuration: `${1.8 + (i % 5) * 0.25}s` }} />
        ))}
      </div>
      <motion.div className="celebrate-card" initial={{ y: 30, scale: 0.94 }} animate={{ y: 0, scale: 1 }}
        transition={{ type: "spring", stiffness: 300, damping: 22 }}>
        <span className="celebrate-icon" aria-hidden="true">{goal.icon}</span>
        <span className="celebrate-kicker">Goal reached</span>
        <h2>{goal.title}</h2>
        <div className="celebrate-wins">
          {money > 0 && <div><b>{eur(money)}</b><span>{verifiedEur ? "verified in your account" : "estimated for you"}</span></div>}
          {goal.outcome.hours_saved > 0 && <div><b>{hours(goal.outcome.hours_saved)}</b><span>of paperwork saved</span></div>}
          <div><b>{goal.progress.done}/{goal.progress.total}</b><span>steps done</span></div>
        </div>
        <p>KBC and its partners took care of it. You approved every step.</p>
        <div className="celebrate-actions">
          {goal.next_goal && onStartNext
            ? <button type="button" className="btn-primary" onClick={() => onStartNext(goal.next_goal!)}>Next: {goal.next_goal_title ?? goal.next_goal}</button>
            : <button type="button" className="btn-primary" onClick={onOpen}>See what was done</button>}
          <button type="button" className="btn-ghost" onClick={onClose}>Close</button>
        </div>
      </motion.div>
    </motion.div>
  );
}
