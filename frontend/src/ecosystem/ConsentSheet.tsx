// Approve a step: exactly what the provider will and will NOT see, for how long, why they can be trusted, which
// vetted partners you can pick from (ranked by results, not by fee) and what KBC earns if you go ahead.
import { useState } from "react";
import { addDays, longDate } from "../format";
import Sheet from "../ui/Sheet";
import { KindBadge, ProductChips } from "./bits";
import type { PartnerOption, Step } from "./types";

interface Props {
  step: Step;
  asOf: string;
  busy: boolean;
  onApprove: (partnerId?: string) => void;
  onDecline: () => void;
  onClose: () => void;
}

function pctText(x: number | null): string {
  return x == null ? "—" : `${Math.round(x * 100)}%`;
}

function Alternatives({ options, chosen, onPick }: { options: PartnerOption[]; chosen: string; onPick: (id: string) => void }) {
  return (
    <div className="eco-box eco-alts">
      <h3>Pick your partner</h3>
      <p className="muted-note">All vetted by KBC. Ranked by how often customers reach the result and by their rating, never by what KBC earns.</p>
      <ul role="radiogroup" aria-label="Partner">
        {options.map((o) => (
          <li key={o.provider.id}>
            <button type="button" role="radio" aria-checked={chosen === o.provider.id}
              className={`eco-alt ${chosen === o.provider.id ? "on" : ""}`} onClick={() => onPick(o.provider.id)}>
              <span className="eco-alt-top">
                <b>{o.provider.name}</b>
                {o.recommended && <span className="eco-pill done">Best results</span>}
              </span>
              <span className="muted-note">{o.provider.blurb}</span>
              <span className="eco-alt-stats">
                <span>Outcome reached: <b>{pctText(o.outcome_rate)}</b></span>
                <span>Rating: <b>{o.rating == null ? "—" : `${o.rating.toFixed(1)}/5`}</b></span>
              </span>
              <span className="eco-fee small">💶 {o.fee.kbc_earns}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function ConsentSheet({ step, asOf, busy, onApprove, onDecline, onClose }: Props) {
  const options = step.alternatives ?? [];
  const [chosen, setChosen] = useState<string>(options.find((o) => o.chosen)?.provider.id ?? step.provider.id);
  const picked = options.find((o) => o.provider.id === chosen);
  const p = picked?.provider ?? step.provider;
  const fee = picked?.fee ?? step.fee ?? null;
  const isKbc = p.kind === "kbc";
  const isAdvisor = p.kind === "advisor";
  return (
    <Sheet full title={isAdvisor ? "Book a meeting" : "Review & approve"} onClose={onClose}>
      <div className="eco-consent">
        <div className="eco-consent-who">
          <div>
            <b>{p.name}</b>
            <KindBadge provider={p} />
          </div>
          <p>{step.title}. {step.description}</p>
          <ProductChips products={step.products} />
        </div>

        {options.length > 1 && <Alternatives options={options} chosen={chosen} onPick={setChosen} />}

        {isAdvisor ? (
          <div className="eco-box ok">
            <h3>Your advisor gets the file KBC already built</h3>
            <p>Your goal, the steps already done and the numbers behind them. You never start from zero, and nothing leaves KBC. We book the first free slot; you can move it.</p>
          </div>
        ) : isKbc || step.data_shared.length === 0 ? (
          <div className="eco-box ok">
            <h3>No data leaves KBC</h3>
            <p>This step is done by KBC itself. Nothing is shared with a partner.</p>
          </div>
        ) : (
          <>
            <div className="eco-box share">
              <h3>{p.name} will see:</h3>
              <ul>
                {step.data_shared.map((d) => (
                  <li key={d.field}>
                    <span>{d.label}</span>
                    {d.sensitive && <span className="eco-sensitive">sensitive</span>}
                  </li>
                ))}
              </ul>
            </div>
            {step.data_not_shared.length > 0 && (
              <div className="eco-box noshare">
                <h3>Will NOT see:</h3>
                <ul>{step.data_not_shared.map((d) => <li key={d}><span>{d}</span></li>)}</ul>
              </div>
            )}
            <div className="eco-expiry">
              ⏱ Access ends after {step.consent_days} days ({longDate(addDays(asOf, step.consent_days))}). You can revoke it any time in your consent passport, and {p.name} must confirm it deleted your data.
            </div>
          </>
        )}

        {fee && p.kind === "partner" && (
          <div className="eco-box eco-fee-box">
            <h3>💶 What KBC earns</h3>
            <p>{fee.kbc_earns} {fee.you_pay_extra}</p>
          </div>
        )}

        <div className="eco-box vetting">
          <h3>{isKbc || isAdvisor ? "KBC service" : "Checked by KBC before joining"}</h3>
          <ul>{p.vetting.map((v) => <li key={v}><span className="tick" aria-hidden="true">✓</span><span>{v}</span></li>)}</ul>
          {p.integration && <div className="eco-integration">Connected via {p.integration}</div>}
        </div>

        {step.why_this_provider && <p className="eco-whyp">Why {step.provider.name}: {step.why_this_provider}</p>}

        <div className="eco-consent-actions">
          <button type="button" className="btn-primary" disabled={busy}
            onClick={() => onApprove(options.length > 1 ? chosen : undefined)}>
            {isAdvisor ? "Book the meeting" : isKbc ? "Go ahead" : `Approve & share with ${p.name}`}
          </button>
          <button type="button" className="btn-ghost" disabled={busy} onClick={onDecline}>Decline</button>
        </div>
      </div>
    </Sheet>
  );
}
