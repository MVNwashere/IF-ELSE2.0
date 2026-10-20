import { shortDate } from "../format";
import { useEur } from "../privacy";
import { arr, num, type SectionProps } from "./types";

interface Open { name: string; eur: number; last_date: string; days: number }
interface Paid { name: string; eur: number; date: string }

/** What may still be open (the same estimate as the late-client card and the "Get paid on time" goal) and the
 * payments that came in. */
export default function InvoiceTracker({ props }: SectionProps) {
  const eur = useEur();
  const openEur = num(props.unpaid_eur);
  const paidQ = num(props.paid_quarter_eur);
  const open = arr<Open>(props.open);
  const recent = arr<Paid>(props.recent).slice(0, 3);
  return (
    <div className="card-box">
      <h3>Invoices</h3>
      {open.length > 0 ? <>
        <div className="big" style={{ color: "var(--amber)" }}>{eur(openEur)}</div>
        <div className="sub">may still be open</div>
        {open.map((o) => (
          <div className="rowstack warn" key={o.name}>
            <span className="cp">{o.name}</span>
            <span className="when">last paid {o.days} days ago</span>
          </div>
        ))}
      </> : <>
        <div className="big">{eur(paidQ)}</div>
        <div className="sub">received this quarter · nothing late</div>
      </>}
      {recent.length > 0 && <div className="box-label">Latest payments</div>}
      {recent.map((p, i) => (
        <div className="rowstack" key={`${p.name}-${p.date}-${i}`}>
          <span className="cp">{p.name}</span>
          <span className="when">{shortDate(p.date)} · <b>{eur(p.eur)}</b></span>
        </div>
      ))}
    </div>
  );
}
