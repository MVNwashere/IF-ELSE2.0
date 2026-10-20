import { useCallback, useEffect, useRef, useState } from "react";
import { abortSessionRequests, ApiError, isAbort } from "./api";
import type { Card, Component, Decision, HomeResponse, KateAction, KateTurn, LayoutPrefState, StylePrefs, TimelineResponse } from "./api";
import { componentLabel } from "./format";
import { AUTO_STYLE } from "./ui/PersonaliseSheet";
import { data, JURY, MOCK, profileData } from "./data";
import ControlPanel from "./demo/ControlPanel";
import { STORAGE_KEY as DEMO_STORAGE_KEY } from "./demo/store";
import Login from "./Login";
import { DEMO_PERSONAS } from "./personas";
import EcosystemConsole from "./ecosystem/EcosystemConsole";
import Phone from "./Phone";
import PhoneScaler from "./PhoneScaler";
import { JuryGuide, JuryPicker } from "./jury/Jury";

interface Session { role: "customer" | "advisor"; username: string }

const DEMO_PASSWORD = "demo";

/** Per-user browser storage must not survive a customer change. The app owns this origin, so clear it all, except,
 * with ?mock=1, the demo engine's own store: there it plays the backend's role. */
function clearClientStorage(): void {
  try { window.sessionStorage.clear(); } catch { /* storage blocked */ }
  try {
    const keep = MOCK ? window.localStorage.getItem(DEMO_STORAGE_KEY) : null;
    window.localStorage.clear();
    if (keep !== null) window.localStorage.setItem(DEMO_STORAGE_KEY, keep);
  } catch { /* storage blocked */ }
}

function OpeningPhone({ name }: { name: string }) {
  const person = DEMO_PERSONAS.find((p) => p.username === name);
  return (
    <div className="phone-bezel">
      <div className="phone phone-switching" role="status" aria-live="polite">
        <span className="switch-ball" aria-hidden="true" />
        <b>{person ? `Opening ${person.name}'s app…` : "Opening the app…"}</b>
        {person && <span>{person.hint}</span>}
      </div>
    </div>
  );
}

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
  // the customer being opened from the demo panel: show their phone loading instead of the login form in between
  const [switching, setSwitching] = useState<string | null>(null);
  // Session generation: bumped whenever the signed-in customer changes or goes away. A response that resolves for an
  // older generation is dropped, so the previous customer's data can never render for the next one.
  const gen = useRef(0);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast((t) => (t === msg ? null : t)), 2200);
  }, []);

  /** Forget everything that belongs to the current customer: in-flight requests, client state and browser storage. */
  const resetClient = useCallback(() => {
    gen.current++;
    reqSeq.current++;
    abortSessionRequests();
    setHome(null); setTimeline(null); setAsOf(null); setError(null); setToast(null); setBusy(false);
    clearClientStorage();
  }, []);

  const fail = useCallback((e: unknown) => {
    if (isAbort(e)) return;
    if (e instanceof ApiError && e.status === 401) {
      resetClient();
      setSession(null);
      return;
    }
    setError(e instanceof Error ? e.message : String(e));
  }, [resetClient]);

  const loadHome = useCallback(async (date: string | null) => {
    const g = gen.current;
    const seq = ++reqSeq.current;
    setBusy(true); setError(null);
    try {
      const h = await data.home(date ?? undefined);
      if (g === gen.current && seq === reqSeq.current) setHome(h);
    } catch (e) { if (g === gen.current) fail(e); } finally { if (g === gen.current && seq === reqSeq.current) setBusy(false); }
  }, [fail]);

  const loadAll = useCallback(async (date: string | null) => {
    const g = gen.current;
    const seq = ++reqSeq.current;
    setBusy(true); setError(null);
    try {
      const [h, t] = await Promise.all([data.home(date ?? undefined), data.timeline()]);
      if (g === gen.current && seq === reqSeq.current) { setHome(h); setTimeline(t); }
    } catch (e) { if (g === gen.current) fail(e); } finally { if (g === gen.current && seq === reqSeq.current) setBusy(false); }
  }, [fail]);

  // Initial: is there a session?
  useEffect(() => {
    const g = gen.current;
    (async () => {
      try {
        const s = await data.session();
        if (g !== gen.current) return;
        setSession(s);
        if (s.role !== "advisor") await loadAll(null);
      } catch (e) {
        if (g === gen.current && !(e instanceof ApiError && e.status === 401)) fail(e);
      } finally { setChecked(true); }
    })();
  }, [fail, loadAll]);

  const login = useCallback(async (username: string, password: string) => {
    resetClient();
    const g = gen.current;
    try {
      const s = await data.login(username, password);
      if (g !== gen.current) return;
      setSession(s);
      if (s.role !== "advisor") await loadAll(null);
    } catch (e) { if (g === gen.current && !isAbort(e)) setError(e instanceof Error ? e.message : String(e)); }
  }, [loadAll, resetClient]);

  const switchCustomer = useCallback(async (username: string) => {
    resetClient();
    setSession(null);
    setSwitching(username);
    const g = gen.current;
    setBusy(true);
    try {
      if (session) await data.logout().catch(() => undefined);
      const s = await data.login(username, DEMO_PASSWORD);
      if (g !== gen.current) return;
      setSession(s);
      if (s.role !== "advisor") await loadAll(null);
    } catch (e) { if (g === gen.current) fail(e); } finally { if (g === gen.current) { setBusy(false); setSwitching(null); } }
  }, [session, loadAll, fail, resetClient]);

  const logout = useCallback(async () => {
    resetClient();
    setSession(null);
    await data.logout().catch(() => undefined);
  }, [resetClient]);

  const onAsOf = useCallback((date: string | null) => {
    setAsOf(date);
    void loadHome(date);
  }, [loadHome]);

  /** Run a mutation that returns a fresh home. Resolves true on success. */
  const apply = useCallback(async (fn: () => Promise<HomeResponse>): Promise<boolean> => {
    const g = gen.current;
    const seq = ++reqSeq.current;
    setBusy(true); setError(null);
    try {
      const h = await fn();
      if (g !== gen.current) return false;
      if (seq === reqSeq.current) setHome(h);
      return true;
    } catch (e) { if (g === gen.current) fail(e); return false; } finally { if (g === gen.current && seq === reqSeq.current) setBusy(false); }
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
    showToast("Back to your home");
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
      // profile: the same endpoints as the profile page (via "kate" when the customer confirmed Kate's proposal);
      // the home depends on the profile, so it is reloaded after each change
      case "update_profile": {
        const key = a.fact_key, value = a.fact_value;
        if (!key || value == null) return false;
        showToast("Saved to your profile");
        return apply(async () => { await profileData.setFact(key, value, "kate", at); return data.home(at); });
      }
      case "forget_fact": {
        const key = a.fact_key;
        if (!key) return false;
        showToast("Deleted from your profile");
        return apply(async () => { await profileData.deleteFact(key, at); return data.home(at); });
      }
      case "forget_kate_facts":
        showToast("Kate forgot what you told her");
        return apply(async () => { await profileData.forgetKate(at); return data.home(at); });
      case "correct_inference": {
        const kind = a.correction_kind, target = a.target;
        if (!kind || !target) return false;
        showToast("Thanks, your home adapts");
        return apply(async () => { await profileData.correction(kind, target, "set", at); return data.home(at); });
      }
      case "set_permission": {
        const purpose = a.purpose, allowed = a.allowed;
        if (!purpose || allowed == null) return false;
        showToast(allowed ? "Switched on" : "Switched off");
        return apply(async () => { await profileData.permission(purpose, allowed, at); return data.home(at); });
      }
      case "open_card":
      case "start_goal":   // handled in Phone (ecosystem, sheets)
      case "open_goal":
      case "open_profile":
      case "open_passport":
      case "revoke_consent":
        return true;
    }
  }, [apply, asOf, showToast, label]);

  const onRefresh = useCallback(() => { void apply(() => data.home(asOf ?? undefined)); }, [apply, asOf]);

  const onConsent = useCallback((v: boolean) => {
    showToast(v ? "Commercial personalisation on" : "Commercial personalisation off");
    void apply(() => data.consent(v, asOf ?? undefined));
  }, [apply, asOf, showToast]);

  const onCta = useCallback((action: string) => showToast(`Simulated: ${action.replace(/_/g, " ")}`), [showToast]);

  if (!JURY && checked && session?.role === "advisor") {
    return <EcosystemConsole key={session.username} username={session.username} onLogout={() => void logout()} onSwitchCustomer={(u) => void switchCustomer(u)} />;
  }

  const phone = session && home && (
    <Phone
      key={session.username}
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
      onRefresh={onRefresh}
    />
  );

  if (JURY) {
    return (
      <div className="jury-stage">
        {!checked ? null : !session || session.role !== "customer" || !phone ? (
          <JuryPicker onPick={(u) => login(u, DEMO_PASSWORD)} error={error} />
        ) : (
          <>
            {phone}
            <JuryGuide key={`guide-${session.username}`} username={session.username} onSwitch={() => void logout()} />
          </>
        )}
      </div>
    );
  }

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
            {phone || ((switching || session) && !error
              ? <OpeningPhone name={switching ?? session?.username ?? ""} />
              : <Login onLogin={login} error={error} />)}
          </PhoneScaler>
        )}
      </main>
    </div>
  );
}
