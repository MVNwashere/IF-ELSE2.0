import { shortDate } from "../format";
import { useEur } from "../privacy";
import { arr, num, type SectionProps } from "./types";

interface Client { name: string; eur: number; last_date: string }

export default function InvoiceTracker({ props }: SectionProps) {
  const eur = useEur();
  const unpaid = num(props.unpaid);
  const unpaidEur = num(props.unpaid_eur);
  const paidQ = num(props.paid_quarter_eur);
  const clients = arr<Client>(props.clients).slice(0, 4);
  return (
    <div className="card-box">
      <h3>Invoices</h3>
      <div className="big" style={{ color: unpaid > 0 ? "var(--amber)" : undefined }}>{eur(unpaidEur)}</div>
      <div className="sub">{unpaid} unpaid · {eur(paidQ)} received this quarter</div>
      <div style={{ marginTop: 8 }}>
        {clients.map((c) => (
          <div className="rowline" key={c.name}>
            <span className="cp">{c.name}</span>
            <span className="when">{shortDate(c.last_date)}</span>
            <span className="amt">{eur(c.eur)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
