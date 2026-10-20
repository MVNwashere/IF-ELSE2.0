// State a goal yourself: every playbook KBC can orchestrate.
import { MaskedText } from "../privacy";
import Sheet from "../ui/Sheet";
import type { Goal, PlaybookSummary } from "./types";

interface Props {
  playbooks: PlaybookSummary[];
  goals: Goal[];
  busy: boolean;
  onStart: (playbookId: string) => void;
  onOpenGoal: (goalId: number) => void;
  onClose: () => void;
}

export default function PlaybooksSheet({ playbooks, goals, busy, onStart, onOpenGoal, onClose }: Props) {
  return (
    <Sheet title="What do you want to achieve?" onClose={onClose}>
      <p className="ps-intro">Tell KBC your goal. We line up the right KBC services and vetted partners, and you approve every step.</p>
      {playbooks.map((p) => {
        const existing = goals.find((g) => g.playbook_id === p.playbook_id && g.status !== "cancelled");
        return (
          <div key={p.playbook_id} className="gallery-row">
            <span className="eco-goal-icon" aria-hidden="true">{p.icon}</span>
            <div className="gallery-text">
              <b>{p.title}</b>
              <span><MaskedText text={p.tagline} /></span>
              <span>{p.steps} steps · {p.ecosystems.join(", ")}</span>
            </div>
            {existing
              ? <button type="button" className="btn-ghost small" onClick={() => onOpenGoal(existing.goal_id)}>Open</button>
              : <button type="button" className="btn-primary small" disabled={busy} onClick={() => onStart(p.playbook_id)}>Start</button>}
          </div>
        );
      })}
    </Sheet>
  );
}
