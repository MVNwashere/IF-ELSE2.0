// "What KBC knows about you" (from the Profile hub, or Kate): everything KBC knows and uses about the customer. What you told us (editable, with where
// it came from), what we worked out (with evidence, and "that's not me"), what your data may be used for, and where
// it comes from or goes to (the consent passport). Every change goes through the regular validated endpoints.
import { useCallback, useEffect, useState } from "react";
import type { FactValue, ProfileField, ProfileResponse, Purpose } from "../api";
import { data, profileData } from "../data";
import { shortDate } from "../format";
import { MaskedText } from "../privacy";
import Sheet from "./Sheet";

interface Props {
  asOf: string;
  onClose: () => void;
  onPassport: () => void;
  onChanged: () => void;            // the home screen depends on the profile: reload it
  notify: (msg: string) => void;
}

const CATEGORY: Record<ProfileField["category"], string> = {
  household: "Household", work: "Work", home: "Home", money: "Money", contact: "Contact and offers",
};

function sourceText(f: ProfileField): string {
  const when = f.updated_on ? ` on ${shortDate(f.updated_on)}` : "";
  return f.source === "kate" ? `You told Kate${when}` : `You entered this${when}`;
}

function FieldEditor({ f, busy, onSave, onDelete }: {
  f: ProfileField; busy: boolean; onSave: (v: FactValue) => void; onDelete: () => void;
}) {
  const [num, setNum] = useState<number>(typeof f.value === "number" ? f.value : 0);
  const chosen = Array.isArray(f.value) ? f.value : [];
  return (
    <div className="pf-editor">
      {f.kind === "enum" && (
        <div className="seg" role="radiogroup" aria-label={f.label}>
          {f.options.map((o) => (
            <button key={o.value} type="button" role="radio" aria-checked={f.value === o.value}
              className={f.value === o.value ? "on" : ""} disabled={busy} onClick={() => onSave(o.value)}>{o.label}</button>
          ))}
        </div>
      )}
      {f.kind === "set" && (
        <div className="seg" role="group" aria-label={f.label}>
          {f.options.map((o) => {
            const on = chosen.includes(o.value);
            return (
              <button key={o.value} type="button" aria-pressed={on} className={on ? "on" : ""} disabled={busy}
                onClick={() => onSave(on ? chosen.filter((v) => v !== o.value) : [...chosen, o.value])}>{o.label}</button>
            );
          })}
        </div>
      )}
      {f.kind === "bool" && (
        <div className="seg" role="radiogroup" aria-label={f.label}>
          {[true, false].map((v) => (
            <button key={String(v)} type="button" role="radio" aria-checked={f.value === v}
              className={f.value === v ? "on" : ""} disabled={busy} onClick={() => onSave(v)}>{v ? "Yes" : "No"}</button>
          ))}
        </div>
      )}
      {f.kind === "int" && (
        <div className="pf-stepper">
          <button type="button" className="btn-ghost small" aria-label="Fewer" disabled={busy || num <= (f.min ?? 0)} onClick={() => setNum((n) => n - 1)}>−</button>
          <b aria-live="polite">{num}</b>
          <button type="button" className="btn-ghost small" aria-label="More" disabled={busy || num >= (f.max ?? 99)} onClick={() => setNum((n) => n + 1)}>+</button>
          <button type="button" className="btn-primary small" disabled={busy || num === f.value} onClick={() => onSave(num)}>Save</button>
        </div>
      )}
      <div className="pf-hint">{f.hint} Used for: {f.used_for.join(", ")}.</div>
      {f.value !== null && <button type="button" className="link danger" disabled={busy} onClick={onDelete}>Delete this</button>}
    </div>
  );
}

export default function AboutYouSheet({ asOf, onClose, onPassport, onChanged, notify }: Props) {
  const [p, setP] = useState<ProfileResponse | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    profileData.get(asOf).then((r) => { if (live) setP(r); }).catch(() => { if (live) setFailed(true); });
    return () => { live = false; };
  }, [asOf]);

  const run = useCallback(async (fn: () => Promise<ProfileResponse>, msg: string) => {
    setBusy(true);
    try {
      setP(await fn());
      notify(msg);
      onChanged();
    } catch (e) {
      notify(e instanceof Error ? e.message : "That didn't work, please try again");
    } finally { setBusy(false); }
  }, [notify, onChanged]);

  const clearDeclared = async (signal: ProfileResponse["declared"][number]["signal"]) => {
    await run(async () => { await data.declare(signal, "clear", asOf); return profileData.get(asOf); }, "Removed");
  };

  if (failed) return <Sheet title="What KBC knows about you" onClose={onClose}><p className="ps-intro">Your profile can't be loaded right now.</p></Sheet>;
  if (!p) return <Sheet title="What KBC knows about you" onClose={onClose}><p className="ps-intro">Loading…</p></Sheet>;

  const fromKate = p.fields.some((f) => f.source === "kate");
  const byCategory = Object.entries(CATEGORY).map(([cat, label]) => [label, p.fields.filter((f) => f.category === cat)] as const);
  const perm = (purpose: Purpose) => p.permissions.find((x) => x.purpose === purpose)?.allowed ?? false;

  return (
    <Sheet title="What KBC knows about you" onClose={onClose} full className="profile-sheet">
      <p className="ps-intro">
        Everything KBC knows and uses about you, {p.first_name}. Correct anything, and decide what it may be used for.
      </p>

      <h3 className="pf-h">What you told us</h3>
      {byCategory.map(([label, fields]) => fields.length > 0 && (
        <div className="pf-group" key={label}>
          <div className="ps-label">{label}</div>
          {fields.map((f) => (
            <div className={`pf-row ${open === f.key ? "open" : ""}`} key={f.key}>
              <button type="button" className="pf-row-head" aria-expanded={open === f.key} onClick={() => setOpen(open === f.key ? null : f.key)}>
                <span className="pf-k">{f.label}</span>
                <span className={`pf-v ${f.value === null ? "unset" : ""}`}>{f.value_label ?? "Not set"}</span>
              </button>
              {f.source && <div className="pf-src">{sourceText(f)}</div>}
              {open === f.key && (
                <FieldEditor
                  key={`${f.key}:${JSON.stringify(f.value)}`}
                  f={f}
                  busy={busy}
                  onSave={(v) => void run(() => profileData.setFact(f.key, v, "you", asOf), "Saved to your profile")}
                  onDelete={() => void run(() => profileData.deleteFact(f.key, asOf), "Deleted")}
                />
              )}
            </div>
          ))}
        </div>
      ))}
      {p.declared.length > 0 && (
        <div className="pf-group">
          <div className="ps-label">Life changes you told Kate</div>
          {p.declared.map((d) => (
            <div className="pf-row" key={d.signal}>
              <div className="pf-row-head static"><span className="pf-k">{d.label}</span>
                <button type="button" className="link danger" disabled={busy} onClick={() => void clearDeclared(d.signal)}>Remove</button>
              </div>
              <div className="pf-src">Since {shortDate(d.created_on)}</div>
            </div>
          ))}
        </div>
      )}
      {fromKate && (
        <button type="button" className="btn-ghost block" disabled={busy} onClick={() => void run(() => profileData.forgetKate(asOf), "Kate forgot what you told her")}>
          Forget everything I told Kate
        </button>
      )}

      <h3 className="pf-h">What we worked out</h3>
      <p className="pf-hint">From your own transactions{p.personas.some((x) => x.from_you) ? " and what you told us" : ""}. It shapes your home screen.</p>
      {p.personas.map((x) => (
        <div className="pf-persona" key={x.persona}>
          <div className="pf-persona-top">
            <b>{x.label}</b><span>{x.weight_pct}%</span>
            <button type="button" className="link" disabled={busy}
              onClick={() => void run(() => profileData.correction("persona", x.persona, "set", asOf), "Thanks, your home adapts")}>That's not me</button>
          </div>
          <div className="pf-bar" aria-hidden="true"><i style={{ width: `${x.weight_pct}%` }} /></div>
          <ul className="pf-evidence">{x.evidence.slice(0, 3).map((e) => <li key={e}><MaskedText text={e} /></li>)}</ul>
        </div>
      ))}
      {perm("detect_life_events") ? p.goals.map((g) => (
        <div className="pf-persona" key={g.playbook_id}>
          <div className="pf-persona-top">
            <b>Suggested: {g.title}</b>
            <button type="button" className="link" disabled={busy}
              onClick={() => void run(() => profileData.correction("goal", g.playbook_id, "set", asOf), "Okay, we won't suggest it")}>Not for me</button>
          </div>
          <ul className="pf-evidence">{g.evidence.slice(0, 2).map((e) => <li key={e}><MaskedText text={e} /></li>)}</ul>
        </div>
      )) : <p className="pf-hint">You switched off spotting life changes, so KBC suggests no goals.</p>}
      {p.corrections.length > 0 && (
        <div className="pf-group">
          <div className="ps-label">You corrected</div>
          {p.corrections.map((c) => (
            <div className="pf-row" key={`${c.kind}:${c.target}`}>
              <div className="pf-row-head static"><span className="pf-k">{c.label}</span>
                <button type="button" className="link" disabled={busy}
                  onClick={() => void run(() => profileData.correction(c.kind, c.target, "clear", asOf), "Undone")}>Undo</button>
              </div>
            </div>
          ))}
        </div>
      )}

      <h3 className="pf-h">What your data may be used for</h3>
      <div className="ps-group">
        {p.permissions.map((x) => (
          <div className="ps-toggle" key={x.purpose}>
            <div><b>{x.label}</b><span>{x.allowed ? x.description : x.when_off}</span></div>
            <button type="button" role="switch" aria-checked={x.allowed} aria-label={x.label} className={`sw ${x.allowed ? "on" : ""}`} disabled={busy}
              onClick={() => void run(() => profileData.permission(x.purpose, !x.allowed, asOf), x.allowed ? "Switched off" : "Switched on")} />
          </div>
        ))}
      </div>

      <h3 className="pf-h">Who else sees it</h3>
      <p className="pf-hint">
        {p.data_access.partners_with_access === 0 ? "No partner can see your data right now." :
          `${p.data_access.partners_with_access} partner${p.data_access.partners_with_access === 1 ? "" : "s"} can see ${p.data_access.fields_shared} piece${p.data_access.fields_shared === 1 ? "" : "s"} of your data.`}
        {" "}{p.data_access.sources_connected === 0 ? "KBC reads no outside sources." :
          `KBC reads ${p.data_access.sources_connected} outside source${p.data_access.sources_connected === 1 ? "" : "s"} with your OK.`}
      </p>
      <button type="button" className="btn-ghost block" style={{ marginTop: 6 }} onClick={onPassport}>🔐 Consent passport: who sees my data</button>
    </Sheet>
  );
}
