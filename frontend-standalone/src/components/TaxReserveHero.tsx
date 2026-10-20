import { longDate } from "../format";
import { useEur } from "../privacy";
import { num, str, type SectionProps } from "./types";

export default function TaxReserveHero({ props }: SectionProps) {
  const eur = useEur();
  const quarter = str(props.quarter_label, "This quarter");
  const income = num(props.quarter_income_eur);
  const reserve = num(props.reserve_eur);
  const pctv = num(props.reserve_pct);
  const due = str(props.vat_due_date);
  const days = num(props.days_to_due);
  const soon = days <= 14;
  return (
    <div className={`hero ${days <= 3 ? "danger" : soon ? "tight" : ""}`}>
      <h3>Tax reserve · {quarter}</h3>
      <div className="amount">{eur(reserve)}</div>
      <div className="line">to set aside for VAT — about {Math.round(pctv)}% of {eur(income)} invoiced</div>
      <div className="bar"><i style={{ width: `${Math.min(100, pctv * 3)}%` }} /></div>
      <div className="kv">
        <div>VAT return due<b>{longDate(due)}</b></div>
        <div>Days left<b>{days}</b></div>
      </div>
      {soon && <span className="pill">⏰ Return due in {days} days</span>}
    </div>
  );
}
