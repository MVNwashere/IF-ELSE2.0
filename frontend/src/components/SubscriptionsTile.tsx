import { useEur } from "../privacy";
import { arr, num, type SectionProps } from "./types";

interface Sub { counterparty: string; amount_eur: number; period_days: number; previous_amount_eur: number | null }

export default function SubscriptionsTile({ props }: SectionProps) {
  const eur = useEur();
  const total = num(props.monthly_total_eur);
  const count = num(props.count);
  const items = arr<Sub>(props.items).slice(0, 3);
  return (
    <div className="card-box">
      <h3>Subscriptions</h3>
      <div className="big">{eur(total)}<span className="per">/month</span></div>
      <div className="sub">{count} active</div>
      <div style={{ marginTop: 8 }}>
        {items.map((s, i) => {
          const up = typeof s.previous_amount_eur === "number" && s.previous_amount_eur < s.amount_eur;
          return (
            <div className="rowline" key={`${s.counterparty}-${i}`}>
              <span className="cp">{s.counterparty}</span>
              <span className="amt">
                {up && <span className="up" title={`was ${eur(s.previous_amount_eur ?? 0)}`}>↑ </span>}
                {eur(s.amount_eur)}
              </span>
            </div>
          );
        })}
        {items.length === 0 && <div className="sub">No subscriptions found.</div>}
      </div>
    </div>
  );
}
