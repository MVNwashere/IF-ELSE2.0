import { longDate, shortDate } from "../format";
import { useEur } from "../privacy";
import { num, str, type SectionProps } from "./types";

interface VatPayment { date: string; name: string; amount: number }

function dueText(days: number): string {
  if (days < 0) return `${-days} day${days === -1 ? "" : "s"} overdue`;
  if (days === 0) return "Due today";
  return days === 1 ? "Due tomorrow" : `Due in ${days} days`;
}

export default function TaxReserveHero({ props, ctx }: SectionProps) {
  const eur = useEur();
  const quarter = str(props.quarter_label, "This quarter");
  const income = num(props.quarter_income_eur);
  const reserve = num(props.reserve_eur);
  const pctv = num(props.reserve_pct);
  const due = str(props.vat_due_date);
  const days = num(props.days_to_due);
  const vat = (props.vat_payment ?? null) as VatPayment | null;
  const action = (props.action ?? null) as { label: string; action: string } | null;
  const soon = days <= 14;
  return (
    <div className={`hero ${days <= 3 ? "danger" : soon ? "tight" : ""}`}>
      <h3>VAT return · {quarter}</h3>
      <div className="amount">{eur(reserve)}</div>
      <div className="line">to set aside for VAT: {Math.round(pctv)}% of the {eur(income)} you invoiced</div>
      <div className="kv">
        <div>Return due<b>{longDate(due)}</b></div>
        {vat && <div>Payment to {vat.name}<b>{shortDate(vat.date)}</b></div>}
      </div>
      <div className="hero-foot">
        {soon && <span className="pill">⏰ {dueText(days)}</span>}
        {action && <button type="button" className="hero-action" onClick={() => ctx.onCta(action.action)}>{action.label}</button>}
      </div>
    </div>
  );
}
