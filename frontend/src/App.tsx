import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";
import type { Card, Component, Decision, HomeResponse, KateAction, KateTurn, LayoutPrefState, StylePrefs, TimelineResponse } from "./api";
import { componentLabel } from "./format";
import { AUTO_STYLE } from "./ui/PersonaliseSheet";
import { data, MOCK } from "./data";
import ControlPanel from "./demo/ControlPanel";
import Login from "./Login";
import Phone from "./Phone";
import PhoneScaler from "./PhoneScaler";

interface Session { role: "customer" | "advisor"; username: string }

const DEMO_PASSWORD = "demo";

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [checked, setChecked] = useState(false);
  const [asOf, setAsOf] = useState<string | null>(null);
  const [home, setHome] = useState<HomeResponse | null>(null);
  const [timeline, setTimeline] = useState<TimelineResponse | null>(null);
  const [explain, setExplain] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const reqSeq = useRef(0);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast((t) => (t === msg ? null : t)), 2200);
  }, []);

  const fail = useCallback((e: unknown) => {
    if (e instanceof ApiError && e.status === 401) {
      setSession(null); setHome(null); setTimeline(null);
      return;
    }
    setError(e instanceof Error ? e.message : String(e));
  }, []);

  const loadHome = useCallback(async (date: string | null) => {
    const seq = ++reqSeq.current;
    setBusy(true); setError(null);
    try {
      const h = await data.home(date ?? undefined);
      if (seq === reqSeq.current) setHome(h);
    } catch (e) { fail(e); } finally { if (seq === reqSeq.current) setBusy(false); }
  }, [fail]);

  const loadAll = useCallback(async (date: string | null) => {
    setBusy(true); setError(null);
    try {
      const [h, t] = await Promise.all([data.home(date ?? undefined), data.timeline()]);
      reqSeq.current++;
      setHome(h); setTimeline(t);
    } catch (e) { fail(e); } finally { setBusy(false); }
  }, [fail]);

  // Initial: is there a session?
  useEffect(() => {
    (async () => {
      try {
        const s = await data.session();
        setSession(s);
        await loadAll(null);
      } catch (e) {
        if (!(e instanceof ApiError && e.status === 401)) fail(e);
      } finally { setChecked(true); }
    })();
  }, [fail, loadAll]);

  const login = useCallback(async (username: string, password: string) => {
    setError(null);
    try {
      const s = await data.login(username, password);
      setSession(s); setAsOf(null);
      await loadAll(null);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }, [loadAll]);

  const switchCustomer = useCallback(async (username: string) => {
    setBusy(true); setError(null);
    try {
      if (session) await data.logout().catch(() => undefined);
      const s = await data.login(username, DEMO_PASSWORD);
      setSession(s); setAsOf(null); setHome(null); setTimeline(null);
      await loadAll(null);
    } catch (e) { fail(e); } finally { setBusy(false); }
  }, [session, loadAll, fail]);

  const logout = useCallback(async () => {
    await data.logout().catch(() => undefined);
    setSession(null); setHome(null); setTimeline(null); setAsOf(null);
  }, []);

  const onAsOf = useCallback((date: string | null) => {
    setAsOf(date);
    void loadHome(date);
  }, [loadHome]);

  /** Run a mutation that returns a fresh home. Resolves true on success. */
  const apply = useCallback(async (fn: () => Promise<HomeResponse>): Promise<boolean> => {
    const seq = ++reqSeq.current;
    setBusy(true); setError(null);
    try {
      const h = await fn();
      if (seq === reqSeq.current) setHome(h);
      return true;
    } catch (e) { fail(e); return false; } finally { if (seq === reqSeq.current) setBusy(false); }
  }, [fail]);

  const onFeedback = useCallback((card: Card, decision: Decision) => {
    const label: Record<Decision, string> = { dismiss: "Dismissed", snooze: "Snoozed for 7 days", less: "Fewer cards like this", accept: "Marked as done", reset: "Feedback reset" };
    showToast(label[decision]);
    void apply(() => data.feedback(card.card_key, card.card_type, decision, asOf ?? undefined));
  }, [apply, asOf, showToast]);

  const onResetFeedback = useCallback(() => {
    showToast("Feedback reset");
    void apply(() => data.feedback("reset", "scam_awareness", "reset", asOf ?? undefined));
  }, [apply, asOf, showToast]);

  const label = useCallback((c: Component) => componentLabel(c, home?.gallery), [home]);

  const onLayoutPref = useCallback((component: Component, state: LayoutPrefState) => {
    showToast(state === "pinned" ? `Pinned ${label(component)}` : state === "hidden" ? `Hid ${label(component)}` : `${label(component)} adapts again`);
    void apply(() => data.layoutPref(component, state, asOf ?? undefined));
  }, [apply, asOf, showToast, label]);

  const onPinAt = useCallback((component: Component, position: number | null) => {
    showToast(position === null ? `Added ${label(component)}` : `Pinned ${label(component)}`);
    void apply(() => data.pinAt(component, position, asOf ?? undefined));
  }, [apply, asOf, showToast, label]);

  const onLayoutReset = useCallback(() => {
    showToast("Back to your adaptive home");
    void apply(() => data.layoutReset(asOf ?? undefined));
  }, [apply, asOf, showToast]);

  const onStyle = useCallback((style: StylePrefs) => {
    void apply(() => data.style(style, asOf ?? undefined));
  }, [apply, asOf]);

  const onSuggestion = useCallback((component: Component, decision: "accept" | "dismiss") => {
    showToast(decision === "accept" ? `Added ${label(component)}` : "Okay, not now");
    void apply(() => data.suggestion(component, decision, asOf ?? undefined));
  }, [apply, asOf, showToast, label]);

  const onKate = useCallback((message: string, cardKey: string | null, history: KateTurn[]) =>
    data.kate(message, cardKey, history, asOf ?? undefined), [asOf]);

  /** Kate proposes, the customer taps: run the proposal through the regular endpoint. */
  const onKateAction = useCallback(async (a: KateAction): Promise<boolean> => {
    const at = asOf ?? undefined;
    switch (a.kind) {
      case "pin_tile":
      case "add_tile":
        if (!a.component) return false;
        showToast(`${a.kind === "pin_tile" ? "Pinned" : "Added"} ${label(a.component)}`);
        return apply(() => data.pinAt(a.component!, null, at));
      case "hide_tile":
        if (!a.component) return false;
        showToast(`Hid ${label(a.component)}`);
        return apply(() => data.layoutPref(a.component!, "hidden", at));
      case "snooze_card":
      case "dismiss_card": {
        if (!a.card_key || !a.card_type) return false;
        const d = a.kind === "snooze_card" ? "snooze" : "dismiss";
        showToast(d === "snooze" ? "Snoozed for 7 days" : "Dismissed");
        return apply(() => data.feedback(a.card_key!, a.card_type!, d, at));
      }
      case "set_style":
        if (!a.style) return false;
        showToast("Style updated");
        return apply(() => data.style(a.style!, at));
      case "reset_style":
        showToast("Style back to Auto");
        return apply(() => data.style(AUTO_STYLE, at));
      case "declare":
        if (!a.signal) return false;
        showToast("Thanks, your home adapts");
        return apply(() => data.declare(a.signal!, "set", at));
      case "open_card":
        return true;
    }
  }, [apply, asOf, showToast, label]);

  const onConsent = useCallback((v: boolean) => {
    showToast(v ? "Commercial personalisation on" : "Commercial personalisation off");
    void apply(() => data.consent(v, asOf ?? undefined));
  }, [apply, asOf, showToast]);

  const onCta = useCallback((action: string) => showToast(`Simulated: ${action.replace(/_/g, " ")}`), [showToast]);

  return (
    <div className="shell">
      <ControlPanel
        username={session?.username ?? null}
        home={home}
        timeline={timeline}
        asOf={asOf}
        explain={explain}
        busy={busy}
        error={error}
        mock={MOCK}
        onSwitchCustomer={(u) => void switchCustomer(u)}
        onAsOf={onAsOf}
        onExplain={setExplain}
        onConsent={onConsent}
        onResetFeedback={onResetFeedback}
        onLogout={() => void logout()}
      />
      <main className="stage-area">
        <div className="stage-area-bg" />
        {!checked ? null : (
          <PhoneScaler>
            {!session || !home ? (
              <Login onLogin={login} error={error} />
            ) : (
              <Phone
                home={home}
                asOf={asOf ?? home.as_of}
                explain={explain}
                loading={busy}
                toast={toast}
                onFeedback={onFeedback}
                onCta={onCta}
                onLayoutPref={onLayoutPref}
                onPinAt={onPinAt}
                onLayoutReset={onLayoutReset}
                onStyle={onStyle}
                onSuggestion={onSuggestion}
                onKate={onKate}
                onKateAction={onKateAction}
              />
            )}
          </PhoneScaler>
        )}
      </main>
    </div>
  );
}
