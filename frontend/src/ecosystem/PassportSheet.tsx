// Consent passport, both directions: every partner that has (or had) access to your data, and every outside
// source KBC reads with your OK. What, why, until when, and proof of deletion when access ends.
import { useCallback, useEffect, useState } from "react";
import { longDate } from "../format";
import Sheet from "../ui/Sheet";
import { eco } from "./client";
import type { ConsentGrant, ConsentsResponse, SourceView } from "./types";

interface Props {
  onClose: () => void;
  onChanged: () => void;
  onError: (msg: string) => void;
  asOf?: string;
  playbookIds?: string[];    // the customer's goals: a source is connected for one of them (purpose binding)
}

function groupByPartner(grants: ConsentGrant[]): [string, ConsentGrant[]][] {
  const m = new Map<string, ConsentGrant[]>();
  for (const g of grants) m.set(g.partner_name, [...(m.get(g.partner_name) ?? []), g]);
  return [...m.entries()].sort((a, b) => Number(b[1].some((g) => g.status === "active")) - Number(a[1].some((g) => g.status === "active")));
}

const SENS: Record<SourceView["sensitivity"], string> = { low: "low sensitivity", medium: "personal", high: "sensitive" };

function valueText(v: string | number): string {
  return typeof v === "number" ? new Intl.NumberFormat("nl-BE").format(v) : v;
}

function SourceRow({ s, goals, busy, onConnect, onDisconnect }: {
  s: SourceView; goals: string[]; busy: boolean; onConnect: (pid: string) => void; onDisconnect: () => void;
}) {
  const purposeGoal = s.goals.find((g) => goals.includes(g)) ?? null;
  const values = Object.entries(s.values);
  return (
    <div className={`eco-grant eco-source ${s.status}`}>
      <div className="eco-grant-top">
        <span className={`eco-pill ${s.status === "connected" || s.status === "public" ? "done" : s.status === "expired" ? "declined" : "proposed"}`}>
          {s.status === "public" ? "public data" : s.status}
        </span>
        <b>{s.name}</b>
        <span className={`eco-chip ${s.sensitivity === "high" ? "sensitive" : ""}`}>{SENS[s.sensitivity]}</span>
      </div>
      <div className="muted-note">{s.provider}</div>
      <div className="eco-chips">{s.reads.map((r) => <span key={r} className="eco-chip">{r}</span>)}</div>
      <p className="muted-note">{s.why}</p>
      {values.length > 0 && (
        <div className="eco-source-values">
          {values.map(([k, v]) => <span key={k}><small>{k.replace(/_/g, " ")}</small> <b>{valueText(v)}</b></span>)}
          <small className="muted-note">Simulated values</small>
        </div>
      )}
      <div className="eco-grant-meta">
        {s.status === "connected" && <span>Purpose: {s.purpose}</span>}
        {s.status === "connected" && s.connected_on && s.expires_on && <span>Since {longDate(s.connected_on)} · until {longDate(s.expires_on)}</span>}
        {s.status === "public" && <span>No permission needed. Shown so you know KBC uses it.</span>}
        {s.status === "available" && s.needs_consent && <span>Access for {s.consent_days} days, only for the goal you pick.</span>}
      </div>
      {s.status === "connected" && (
        <button type="button" className="btn-ghost small danger" disabled={busy} onClick={onDisconnect}>Disconnect</button>
      )}
      {(s.status === "available" || s.status === "expired") && s.needs_consent && (
        purposeGoal
          ? <button type="button" className="btn-ghost small" disabled={busy} onClick={() => onConnect(purposeGoal)}>Connect for this goal</button>
          : <span className="muted-note">Used for: {s.goals.join(", ").replace(/_/g, " ")}. Start one of those goals first.</span>
      )}
    </div>
  );
}

export default function PassportSheet({ onClose, onChanged, onError, asOf, playbookIds = [] }: Props) {
  const [data, setData] = useState<ConsentsResponse | null>(null);
  const [sources, setSources] = useState<SourceView[] | null>(null);
  const [busy, setBusy] = useState<number | string | null>(null);

  const err = useCallback((e: unknown) => onError(e instanceof Error ? e.message : String(e)), [onError]);
  const load = useCallback(async () => {
    try { setData(await eco.consents()); } catch (e) { err(e); }
    try { setSources((await eco.sources(asOf)).sources); } catch { setSources(null); }
  }, [err, asOf]);
  useEffect(() => { void load(); }, [load]);

  const revoke = async (id: number) => {
    setBusy(id);
    try {
      setData(await eco.revokeConsent(id));
      onChanged();
      window.setTimeout(() => void load(), 3500);   // the partner confirms deletion with a signed webhook
    } catch (e) { err(e); } finally { setBusy(null); }
  };
  const connect = async (sourceId: string, playbookId: string) => {
    setBusy(sourceId);
    try { setSources((await eco.connectSource(sourceId, playbookId, asOf)).sources); } catch (e) { err(e); } finally { setBusy(null); }
  };
  const disconnect = async (sourceId: string) => {
    setBusy(sourceId);
    try { setSources((await eco.disconnectSource(sourceId, asOf)).sources); } catch (e) { err(e); } finally { setBusy(null); }
  };

  return (
    <Sheet full title="🔐 Consent passport" onClose={onClose}>
      {!data ? <p className="muted-note">Loading…</p> : (
        <>
          <div className="eco-pass-sum">
            <div><b>{data.partners_with_access}</b><span>partners with access</span></div>
            <div><b>{data.fields_shared}</b><span>data fields shared</span></div>
            {sources && <div><b>{sources.filter((s) => s.status === "connected").length}</b><span>sources KBC reads</span></div>}
          </div>
          <h3 className="eco-pass-h">Data partners see</h3>
          <p className="ps-intro">Partners only ever see what you approved, for one purpose, until the date shown. Revoke and their access stops immediately; they must confirm they deleted your data.</p>
          {data.grants.length === 0 && <p className="muted-note">No partner has access to your data.</p>}
          {groupByPartner(data.grants).map(([partner, grants]) => (
            <div key={partner} className="eco-pass-partner">
              <h3>{partner}</h3>
              {grants.map((g) => (
                <div key={g.grant_id} className={`eco-grant ${g.status}`}>
                  <div className="eco-grant-top">
                    <span className={`eco-pill ${g.status === "active" ? "done" : "declined"}`}>{g.status}</span>
                    <span className="muted-note">{g.goal_title} · {g.step_title}</span>
                  </div>
                  <div className="eco-chips">
                    {g.fields.map((f) => <span key={f.field} className={`eco-chip ${f.sensitive ? "sensitive" : ""}`}>{f.label}</span>)}
                  </div>
                  <div className="eco-grant-meta">
                    <span>Purpose: {g.purpose}</span>
                    <span>
                      {g.status === "revoked" && g.revoked_on ? `Revoked ${longDate(g.revoked_on)}` : `Granted ${longDate(g.granted_on)} · until ${longDate(g.expires_on)}`}
                    </span>
                    {g.kbc_earns && <span>💶 {g.kbc_earns}</span>}
                  </div>
                  {g.deletion_confirmed_by && (
                    <div className="eco-deleted">🗑 Deletion confirmed by {g.deletion_confirmed_by} (signed webhook)</div>
                  )}
                  {g.status === "revoked" && !g.deletion_confirmed_by && (
                    <div className="muted-note">Waiting for {g.partner_name} to confirm deletion…</div>
                  )}
                  {g.status === "active" && (
                    <button type="button" className="btn-ghost small danger" disabled={busy !== null} onClick={() => void revoke(g.grant_id)}>
                      {busy === g.grant_id ? "Revoking…" : "Revoke access"}
                    </button>
                  )}
                </div>
              ))}
            </div>
          ))}
          {sources && (
            <div className="eco-pass-partner">
              <h3 className="eco-pass-h">Data KBC reads (with your OK)</h3>
              <p className="ps-intro">Outside sources that make your goals more exact. Each one only for the goal you pick, until the date shown.</p>
              {sources.map((s) => (
                <SourceRow key={s.source_id} s={s} goals={playbookIds} busy={busy !== null}
                  onConnect={(pid) => void connect(s.source_id, pid)} onDisconnect={() => void disconnect(s.source_id)} />
              ))}
            </div>
          )}
        </>
      )}
    </Sheet>
  );
}
