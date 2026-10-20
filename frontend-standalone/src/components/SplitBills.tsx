import { shortDate } from "../format";
import { useEur } from "../privacy";
import { arr, str, type SectionProps } from "./types";

interface Recent { counterparty: string; amount_eur: number; date: string }

export default function SplitBills({ props, ctx }: SectionProps) {
  const eur = useEur();
  const recent = arr<Recent>(props.recent).slice(0, 3);
  const hint = str(props.hint);
  return (
    <div className="card-box">
      <h3>Split a bill</h3>
      {hint && <div className="sub" style={{ marginBottom: 6 }}>{hint}</div>}
      {recent.map((r, i) => (
        <div className="rowline" key={`${r.counterparty}-${r.date}-${i}`}>
          <span className="cp">{r.counterparty}</span>
          <span className="when">{shortDate(r.date)}</span>
          <button
            type="button"
            className="amt"
            style={{ background: "none", border: "none", color: "var(--primary)", padding: 0 }}
            onClick={() => ctx.onCta("split_request")}
          >
            {eur(r.amount_eur)} ↗
          </button>
        </div>
      ))}
      {recent.length === 0 && <div className="sub">No recent shareable spends.</div>}
    </div>
  );
}
