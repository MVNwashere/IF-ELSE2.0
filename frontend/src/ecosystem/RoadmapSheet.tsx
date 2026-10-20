import { useEffect, useState } from "react";
import { maskText, useMasked } from "../privacy";
import Sheet from "../ui/Sheet";
import { eco } from "./client";
import type { Goal, GoalCandidate, PlaybookSummary } from "./types";

interface Props {
  candidate: GoalCandidate | PlaybookSummary;
  busy: boolean;
  onStart: (playbookId: string) => void;
  onNotNow: () => void;
  onClose: () => void;
}

/** Any available goal: suggested ones say why KBC noticed them; every one can be started or put aside. */
export default function RoadmapSheet({ candidate, busy, onStart, onNotNow, onClose }: Props) {
  const noticed = "why_now" in candidate ? candidate : null;
  const [preview, setPreview] = useState<Goal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const masked = useMasked();
  const safe = (text: string) => maskText(text, masked);
  useEffect(() => {
    let live = true;
    setPreview(null);
    setError(null);
    void eco.previewGoal(candidate.playbook_id).then(
      (goal) => { if (live) setPreview(goal); },
      () => { if (live) setError("We couldn't load this roadmap. Close it and try again."); },
    );
    return () => { live = false; };
  }, [candidate.playbook_id]);

  return (
    <Sheet title="Your roadmap" onClose={onClose} full className="roadmap-sheet">
      <div className="roadmap-intro">
        <span className="roadmap-kicker">{noticed ? "KBC NOTICED" : "AVAILABLE GOAL"}</span>
        <h3>{safe(candidate.title)}</h3>
        <p>{safe(noticed ? noticed.why_now : candidate.tagline)}</p>
      </div>
      {noticed && noticed.evidence.length > 0 && <details className="roadmap-evidence">
        <summary>Why we noticed this</summary>
        <ul>{noticed.evidence.map((line, i) => <li key={i}>{safe(line)}</li>)}</ul>
      </details>}
      {error && <p role="alert">{error}</p>}
      {!preview && !error && <p role="status">Preparing your roadmap…</p>}
      {preview && <>
        <div className="roadmap-label"><h3>Here’s how we’ll help</h3><span>{preview.steps.length} steps</span></div>
        <ol className="roadmap-steps">
          {[...preview.steps].sort((a, b) => a.order - b.order).map((step, i) => (
            <li key={step.step_id}>
              <span className="roadmap-number">{i + 1}</span>
              <div><span className="roadmap-provider">{step.provider.name}{step.already_held ? " · Already in place" : ""}</span>
                <h4>{safe(step.title)}</h4><p>{safe(step.description)}</p>
                {step.data_shared.length > 0 && <small>With your permission: {step.data_shared.map((field) => field.label).join(", ")}.</small>}
              </div>
            </li>
          ))}
        </ol>
      </>}
      <div className="roadmap-approval">
        <p>One approval to start your goal. You stay in control of each action and any data shared with partners.</p>
        <div className="roadmap-choice">
          <button type="button" className="btn-ghost" onClick={onNotNow}>Not now</button>
          <button type="button" className="btn-primary" disabled={busy || !preview} onClick={() => onStart(candidate.playbook_id)}>
            {busy ? "Starting your goal…" : "Approve & start"}
          </button>
        </div>
      </div>
    </Sheet>
  );
}
