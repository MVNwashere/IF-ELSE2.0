// Goals state for the phone: load per as_of, poll while a partner is working, run the customer's decisions.
import { useCallback, useEffect, useRef, useState } from "react";
import { eco } from "./client";
import type { Goal, GoalsResponse, StallAnswer, StepDecision } from "./types";

const POLL_MS = 1500;
export const ECO_RESET_EVENT = "eco:reset";

export function useGoals(asOf: string, customerKey: string, onError: (msg: string) => void) {
  const [data, setData] = useState<GoalsResponse | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const seq = useRef(0);

  const load = useCallback(async () => {
    const my = ++seq.current;
    try {
      const r = await eco.goals(asOf);
      if (my === seq.current) setData(r);
    } catch (e) {
      if (my === seq.current) setData(null);
      // The ecosystem API may not be deployed yet: keep the rest of the app working.
      console.warn("goals unavailable", e);
    }
  }, [asOf]);

  useEffect(() => { void load(); }, [load, customerKey]);
  useEffect(() => { setHidden(new Set()); }, [customerKey]);
  useEffect(() => {
    const onReset = () => { setHidden(new Set()); void load(); };
    window.addEventListener(ECO_RESET_EVENT, onReset);
    return () => window.removeEventListener(ECO_RESET_EVENT, onReset);
  }, [load]);

  const working = !!data?.goals.some((g) => g.steps.some((s) => s.status === "in_progress"));
  useEffect(() => {
    if (!working) return;
    const t = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(t);
  }, [working, load]);

  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | null> => {
    setBusy(true);
    try {
      const r = await fn();
      await load();
      return r;
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e));
      return null;
    } finally { setBusy(false); }
  }, [load, onError]);

  const start = useCallback((playbookId: string) => run(() => eco.startGoal(playbookId, asOf)), [run, asOf]);
  const decide = useCallback((goalId: number, stepId: string, d: StepDecision, partnerId?: string) =>
    run(() => eco.stepDecision(goalId, stepId, d, asOf, partnerId)), [run, asOf]);
  const connectSource = useCallback((sourceId: string, playbookId: string) => run(() => eco.connectSource(sourceId, playbookId, asOf)), [run, asOf]);
  const cancel = useCallback((goalId: number) => run(() => eco.cancelGoal(goalId)), [run]);
  const reset = useCallback(() => run(() => eco.goalsReset()), [run]);
  const invite = useCallback((goalId: number, username: string) => run(() => eco.invite(goalId, username, asOf)), [run, asOf]);
  const answerInvite = useCallback((goalId: number, accept: boolean) => run(() => eco.answerInvite(goalId, accept, asOf)), [run, asOf]);
  const answerStall = useCallback((goalId: number, answer: StallAnswer) => run(() => eco.stall(goalId, answer, asOf)), [run, asOf]);
  const hide = useCallback((playbookId: string) => setHidden((h) => new Set(h).add(playbookId)), []);

  const goal = useCallback((id: number): Goal | undefined => data?.goals.find((g) => g.goal_id === id), [data]);

  return { data, busy, hidden, load, start, decide, cancel, reset, hide, goal, connectSource, asOf, invite, answerInvite, answerStall };
}

export type GoalsState = ReturnType<typeof useGoals>;
