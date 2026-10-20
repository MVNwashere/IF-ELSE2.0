import { shortDate } from "../format";
import { useEur } from "../privacy";
import { arr, num, type SectionProps } from "./types";

interface Bill { counterparty: string; amount_eur: number; date: string; category: string }

export default function UpcomingBills({ props }: SectionProps) {
  const eur = useEur();
  const bills = arr<Bill>(props.bills).slice(0, 5);
  const total = num(props.total_eur);
  return (
    <div className="card-box">
      <h3>Next 14 days</h3>
      <div className="big">{eur(total)}</div>
      <div className="sub">{bills.length} {bills.length === 1 ? "bill" : "bills"} coming up</div>
      <div style={{ marginTop: 8 }}>
        {bills.map((b, i) => (
          <div className="rowline" key={`${b.counterparty}-${b.date}-${i}`}>
            <span className="cp">{b.counterparty}</span>
            <span className="when">{shortDate(b.date)}</span>
            <span className="amt">{eur(b.amount_eur)}</span>
          </div>
        ))}
        {bills.length === 0 && <div className="sub">Nothing due. Nice.</div>}
      </div>
    </div>
  );
}
