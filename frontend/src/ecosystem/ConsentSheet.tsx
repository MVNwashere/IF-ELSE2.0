// Approve a step: exactly what the provider will and will NOT see, for how long, and why they can be trusted.
import { addDays, longDate } from "../format";
import Sheet from "../ui/Sheet";
import { KindBadge, ProductChips } from "./bits";
import type { Step } from "./types";

interface Props {
  step: Step;
  asOf: string;
  busy: boolean;
  onApprove: () => void;
  onDecline: () => void;
  onClose: () => void;
}

export default function ConsentSheet({ step, asOf, busy, onApprove, onDecline, onClose }: Props) {
  const p = step.provider;
  const isKbc = p.kind === "kbc";
  return (
    <Sheet full title="Review & approve" onClose={onClose}>
      <div className="eco-consent">
        <div className="eco-consent-who">
          <div>
            <b>{p.name}</b>
            <KindBadge provider={p} />
          </div>
          <p>{step.title}. {step.description}</p>
          <ProductChips products={step.products} />
        </div>

        {isKbc || step.data_shared.length === 0 ? (
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
              ⏱ Access ends after {step.consent_days} days ({longDate(addDays(asOf, step.consent_days))}). You can revoke it any time in your consent passport.
            </div>
          </>
        )}

        <div className="eco-box vetting">
          <h3>{isKbc ? "KBC service" : "Checked by KBC before joining"}</h3>
          <ul>{p.vetting.map((v) => <li key={v}><span className="tick" aria-hidden="true">✓</span><span>{v}</span></li>)}</ul>
          {p.integration && <div className="eco-integration">Connected via {p.integration}</div>}
        </div>

        {step.why_this_provider && <p className="eco-whyp">Why {p.name}: {step.why_this_provider}</p>}

        <div className="eco-consent-actions">
          <button type="button" className="btn-primary" disabled={busy} onClick={onApprove}>{isKbc ? "Go ahead" : "Approve & share"}</button>
          <button type="button" className="btn-ghost" disabled={busy} onClick={onDecline}>Decline</button>
        </div>
      </div>
    </Sheet>
  );
}
