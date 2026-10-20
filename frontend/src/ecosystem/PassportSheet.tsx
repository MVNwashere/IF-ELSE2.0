// Consent passport: every partner that has (or had) access to your data, what, why and until when.
import { useCallback, useEffect, useState } from "react";
import { longDate } from "../format";
import Sheet from "../ui/Sheet";
import { eco } from "./client";
import type { ConsentGrant, ConsentsResponse } from "./types";

interface Props { onClose: () => void; onChanged: () => void; onError: (msg: string) => void }

function groupByPartner(grants: ConsentGrant[]): [string, ConsentGrant[]][] {
  const m = new Map<string, ConsentGrant[]>();
  for (const g of grants) m.set(g.partner_name, [...(m.get(g.partner_name) ?? []), g]);
  return [...m.entries()].sort((a, b) => Number(b[1].some((g) => g.status === "active")) - Number(a[1].some((g) => g.status === "active")));
}

export default function PassportSheet({ onClose, onChanged, onError }: Props) {
  const [data, setData] = useState<ConsentsResponse | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  const load = useCallback(async () => {
    try { setData(await eco.consents()); } catch (e) { onError(e instanceof Error ? e.message : String(e)); }
  }, [onError]);
  useEffect(() => { void load(); }, [load]);

  const revoke = async (id: number) => {
    setBusy(id);
    try { setData(await eco.revokeConsent(id)); onChanged(); } catch (e) { onError(e instanceof Error ? e.message : String(e)); } finally { setBusy(null); }
  };

  return (
    <Sheet full title="🔐 Consent passport" onClose={onClose}>
      {!data ? <p className="muted-note">Loading…</p> : (
        <>
          <div className="eco-pass-sum">
            <div><b>{data.partners_with_access}</b><span>partners with access</span></div>
            <div><b>{data.fields_shared}</b><span>data fields shared</span></div>
          </div>
          <p className="ps-intro">Partners only ever see what you approved, for one purpose, until the date shown. Revoke and their access stops immediately.</p>
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
                  </div>
                  {g.status === "active" && (
                    <button type="button" className="btn-ghost small danger" disabled={busy !== null} onClick={() => void revoke(g.grant_id)}>
                      {busy === g.grant_id ? "Revoking…" : "Revoke access"}
                    </button>
                  )}
                </div>
              ))}
            </div>
          ))}
        </>
      )}
    </Sheet>
  );
}
