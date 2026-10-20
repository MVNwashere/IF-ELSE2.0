import { useEffect, useMemo, useState } from "react";
import type { HomeResponse, TimelineResponse } from "../api";
import { addDays, daysBetween, longDate, PERSONA_LABEL, pct } from "../format";

interface Props {
  username: string | null;
  home: HomeResponse | null;
  timeline: TimelineResponse | null;
  asOf: string | null;
  explain: boolean;
  busy: boolean;
  error: string | null;
  mock: boolean;
  onSwitchCustomer: (username: string) => void;
  onAsOf: (asOf: string | null) => void;
  onExplain: (v: boolean) => void;
  onConsent: (v: boolean) => void;
  onResetFeedback: () => void;
  onLogout: () => void;
}

const DEMO = [
  { username: "lotte", hint: "time travel 2018 → 2026" },
  { username: "sara", hint: "freelancer + young mother" },
  { username: "jan", hint: "retiree, 71" },
];

export default function ControlPanel(p: Props) {
  const tl = p.timeline;
  const totalDays = tl ? Math.max(1, daysBetween(tl.min_date, tl.max_date)) : 1;
  const currentDate = p.asOf ?? tl?.max_date ?? null;
  const currentIdx = tl && currentDate ? Math.max(0, Math.min(totalDays, daysBetween(tl.min_date, currentDate))) : totalDays;
  const [slider, setSlider] = useState(currentIdx);

  // keep the slider in sync when the customer/timeline changes
  useEffect(() => { setSlider(currentIdx); }, [currentIdx, tl?.min_date, tl?.max_date]);

  // debounce slider → as_of
  useEffect(() => {
    if (!tl) return;
    const t = window.setTimeout(() => {
      const date = slider >= totalDays ? null : addDays(tl.min_date, slider);
      if (date !== p.asOf) p.onAsOf(date);
    }, 150);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slider]);

  const previewDate = tl ? addDays(tl.min_date, Math.min(slider, totalDays)) : null;
  const ticks = useMemo(() => (tl ? tl.milestones.map((m) => ({ ...m, left: (daysBetween(tl.min_date, m.date) / totalDays) * 100 })) : []), [tl, totalDays]);
  const theme = p.home?.layout.theme;

  // Snap to the nearest milestone when released within ~2% of the axis.
  const snap = () => {
    if (!tl) return;
    const tol = totalDays * 0.02;
    let best: number | null = null;
    for (const m of tl.milestones) {
      const idx = daysBetween(tl.min_date, m.date);
      if (Math.abs(idx - slider) <= tol && (best === null || Math.abs(idx - slider) < Math.abs(best - slider))) best = idx;
    }
    if (best !== null && best !== slider) setSlider(Math.max(0, Math.min(totalDays, best)));
  };

  return (
    <aside className="panel">
      <h1>
        KBC Adaptive Home
        <small>Demo controls · synthetic data{p.mock ? " · MOCK MODE" : ""}</small>
      </h1>

      <section>
        <h2>Customer</h2>
        <div className="row">
          {DEMO.map((d) => (
            <button
              key={d.username}
              className={`pbtn ${p.username === d.username ? "active" : ""}`}
              disabled={p.busy}
              title={d.hint}
              onClick={() => p.onSwitchCustomer(d.username)}
            >
              {d.username[0].toUpperCase() + d.username.slice(1)}
            </button>
          ))}
          {p.username && <button className="pbtn small" onClick={p.onLogout} disabled={p.busy}>Log out</button>}
        </div>
        {p.username && <div className="hint" style={{ marginTop: 8 }}>{DEMO.find((d) => d.username === p.username)?.hint ?? `logged in as ${p.username}`}</div>}
      </section>

      {tl && (
        <section>
          <h2>Time travel</h2>
          <div className="slider-wrap">
            <div className="slider-date">
              {longDate(previewDate)}
              {slider >= totalDays ? <small>today</small> : <small>as of</small>}
            </div>
            <div className="slider">
              <input
                type="range"
                min={0}
                max={totalDays}
                value={slider}
                onChange={(e) => setSlider(Number(e.target.value))}
                onMouseUp={snap}
                onTouchEnd={snap}
                onKeyUp={snap}
              />
              <div className="ticks">
                {ticks.map((t) => (
                  <div
                    key={`${t.date}-${t.label}`}
                    className={`tick ${slider >= daysBetween(tl.min_date, t.date) ? "passed" : ""}`}
                    style={{ left: `${t.left}%` }}
                    title={`${t.label} · ${longDate(t.date)}`}
                  >
                    <i />
                  </div>
                ))}
              </div>
            </div>
            <div className="row">
              {ticks.map((t) => (
                <button key={t.date} className="pbtn small" onClick={() => setSlider(Math.min(totalDays, daysBetween(tl.min_date, t.date) + 20))}>
                  {t.label}
                </button>
              ))}
              <button className="pbtn small" onClick={() => setSlider(totalDays)}>Today</button>
            </div>
          </div>
        </section>
      )}

      {p.home && (
        <section>
          <h2>Persona mix</h2>
          {p.home.persona_mix.map((pw) => (
            <div className="persona-block" key={pw.persona}>
              <header><span>{PERSONA_LABEL[pw.persona] ?? pw.persona}</span><span>{pct(pw.weight)}</span></header>
              <div className="bar"><i style={{ width: `${pw.weight * 100}%` }} /></div>
              {pw.evidence.length > 0 && <ul className="evidence-list">{pw.evidence.slice(0, 3).map((e, i) => <li key={i}>{e}</li>)}</ul>}
            </div>
          ))}
          {theme && (
            <div className="persona-chips" style={{ marginTop: 10 }}>
              <span className="chip theme">density <b>{theme.density}</b></span>
              <span className="chip theme">tone <b>{theme.tone}</b></span>
              <span className="chip theme">contrast <b>{theme.contrast}</b></span>
            </div>
          )}
        </section>
      )}

      <section>
        <h2>Controls</h2>
        <div className="toggle">
          <span>Explain mode: “why am I seeing this?”</span>
          <button type="button" className={`sw ${p.explain ? "on" : ""}`} aria-pressed={p.explain} onClick={() => p.onExplain(!p.explain)} />
        </div>
        {p.home && (
          <div className="toggle">
            <span>Commercial personalisation (consent)</span>
            <button
              type="button"
              className={`sw ${p.home.customer.consent_personalization ? "on" : ""}`}
              aria-pressed={p.home.customer.consent_personalization}
              disabled={p.busy}
              onClick={() => p.onConsent(!p.home!.customer.consent_personalization)}
            />
          </div>
        )}
        <div className="row" style={{ marginTop: 6 }}>
          <button className="pbtn small" disabled={p.busy || !p.home} onClick={p.onResetFeedback}>Reset feedback</button>
        </div>
        {p.error && <div className="err" style={{ marginTop: 8 }}>{p.error}</div>}
      </section>

      <section>
        <h2>How it works</h2>
        <div className="hint">
          Transactions → signals → <b>persona mix</b> → cards + ranker → <b>layout spec</b> → this screen.
          Nothing here was designed by hand: the system composed it, and every section can explain itself.
        </div>
      </section>
    </aside>
  );
}
