// Jury mode: what a judge sees after scanning the QR code. A persona picker instead of a login, the phone app full
// screen, and a small guide that follows the judge's progress through the demo state.
import { useEffect, useState, useSyncExternalStore } from "react";
import { fixtures, saved, STORAGE_KEY, subscribe, type CustomerName } from "../demo/store";
import "./jury.css";

const PERSONAS: { username: CustomerName; name: string; age: string; story: string }[] = [
  { username: "lotte", name: "Juliette", age: "26", story: "Going freelance. Her first client just paid, and KBC noticed." },
  { username: "sara", name: "Sara", age: "34", story: "Freelancer and young mother. Her car insurance renews in 12 days." },
  { username: "jan", name: "Jan", age: "71", story: "Retired. A calm, large layout and a scam shield." },
  { username: "marc", name: "Marc", age: "52", story: "Investor, thinking about retirement and a long trip." },
];

export function JuryPicker({ onPick, error }: { onPick: (username: string) => Promise<void>; error: string | null }) {
  const [busy, setBusy] = useState<string | null>(null);
  const pick = async (username: string) => {
    setBusy(username);
    try { await onPick(username); } finally { setBusy(null); }
  };
  return (
    <div className="jury-picker">
      <header>
        <div className="jury-brand">KBC Takes Care</div>
        <h1>Step into someone's life</h1>
        <p>One banking app that composes itself around each customer. Pick a person and see what KBC takes care of for them.</p>
      </header>
      <div className="jury-personas">
        {PERSONAS.map((p) => (
          <button key={p.username} type="button" disabled={busy !== null} onClick={() => void pick(p.username)}>
            <span className="jury-avatar" aria-hidden>{p.name[0]}</span>
            <span>
              <b>{p.name}, {p.age}</b>
              <span>{busy === p.username ? "Opening…" : p.story}</span>
            </span>
          </button>
        ))}
      </div>
      {error && <div className="jury-error">{error}</div>}
      <footer>Demo with synthetic data. No real customers, partners or offers.</footer>
    </div>
  );
}

interface Step { title: string; hint: string; done: boolean }

/** The guide reads the demo engine's own state, so it ticks off steps however the judge reaches them. */
function useSteps(username: string): Step[] {
  const version = useSyncExternalStore(subscribe, () => JSON.stringify(saved.customers[username as CustomerName] ?? null));
  const state = saved.customers[username as CustomerName];
  const fixture = fixtures[username as CustomerName];
  if (!state || !fixture || !version) return [];
  const goal = fixture.snapshots[fixture.snapshots.length - 1].goals.candidates[0];
  return [
    {
      title: "KBC spots a goal",
      hint: goal ? `Open Goals at the bottom, tap “${goal.title}” and start the plan.` : "Open Goals at the bottom and start a plan.",
      done: state.goals.some((g) => g.status !== "cancelled"),
    },
    {
      title: "You stay in control",
      hint: "In the plan, approve a step with a partner. You see exactly which data they get, and for how long.",
      done: state.grants.length > 0,
    },
    {
      title: "Kate proposes, you confirm",
      hint: "Close the plan, tap Kate at the bottom and ask her to make the text bigger or switch to dark mode.",
      done: state.style !== null,
    },
  ];
}

/** Wipe the demo engine's saved state and start over from the picker. */
export function restartDemo(): void {
  try { window.localStorage.removeItem(STORAGE_KEY); } catch { /* storage blocked */ }
  window.location.reload();
}

export function JuryGuide({ username, onSwitch }: { username: string; onSwitch: () => void }) {
  const steps = useSteps(username);
  const [open, setOpen] = useState(true);
  const done = steps.filter((s) => s.done).length;
  const all = steps.length > 0 && done === steps.length;
  const next = steps.find((s) => !s.done);

  // Fold the guide away while the judge works on a step; bring it back when a step completes.
  useEffect(() => { if (done > 0) setOpen(true); }, [done]);

  if (!open) {
    return (
      <button type="button" className="jury-pill" onClick={() => setOpen(true)}>
        {all ? "Demo complete ✓" : `Demo guide · ${done}/${steps.length}`}
      </button>
    );
  }
  return (
    <div className="jury-guide" role="dialog" aria-label="Demo guide">
      <div className="jury-guide-head">
        <b>{all ? "That's the full loop" : "Try this"}</b>
        <button type="button" className="jury-x" aria-label="Hide guide" onClick={() => setOpen(false)}>✕</button>
      </div>
      {all && <p className="jury-done">Recognise, guide, deliver, and the customer approved every step. Try another person: their app looks completely different.</p>}
      <ol>
        {steps.map((s) => (
          <li key={s.title} className={s.done ? "done" : s === next ? "next" : ""}>
            <span className="jury-check" aria-hidden>{s.done ? "✓" : ""}</span>
            <span><b>{s.title}</b>{s === next && <span>{s.hint}</span>}</span>
          </li>
        ))}
      </ol>
      <div className="jury-actions">
        {!all && <button type="button" className="jury-go" onClick={() => setOpen(false)}>Let's go</button>}
        <button type="button" onClick={onSwitch}>Another person</button>
        <button type="button" onClick={restartDemo}>Restart</button>
      </div>
    </div>
  );
}
