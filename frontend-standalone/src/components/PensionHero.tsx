import { longDate, shortDate } from "../format";
import { useEur } from "../privacy";
import { num, str, type SectionProps } from "./types";

export default function PensionHero({ props }: SectionProps) {
  const eur = useEur();
  const balance = num(props.balance_eur);
  const pension = num(props.pension_eur);
  const received = str(props.pension_received_date as string | null, "") || null;
  const next = str(props.next_pension_date as string | null, "") || null;
  const billsEur = num(props.upcoming_bills_eur);
  const billsCount = num(props.upcoming_bills_count);
  return (
    <div className="hero calm">
      <h3>Your account</h3>
      <div className="amount">{eur(balance)}</div>
      {received
        ? <div className="line">✓ Pension of {eur(pension)} received on {longDate(received)}</div>
        : <div className="line">Pension of {eur(pension)} per month</div>}
      <div className="kv">
        {next && <div>Next pension<b>{shortDate(next)}</b></div>}
        <div>Bills next 14 days<b>{billsCount} · {eur(billsEur)}</b></div>
        <div>After bills<b>{eur(balance - billsEur)}</b></div>
      </div>
      <span className="pill">Everything is in order</span>
    </div>
  );
}
