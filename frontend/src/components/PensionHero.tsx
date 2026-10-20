import { longDate, shortDate } from "../format";
import { useEur } from "../privacy";
import { num, str, type SectionProps } from "./types";

/** The balance is already in the KBC ball: this tile is about the pension and the bills it has to cover. */
export default function PensionHero({ props }: SectionProps) {
  const eur = useEur();
  const balance = num(props.balance_eur);
  const pension = num(props.pension_eur);
  const received = str(props.pension_received_date as string | null, "") || null;
  const next = str(props.next_pension_date as string | null, "") || null;
  const billsEur = num(props.upcoming_bills_eur);
  const billsCount = num(props.upcoming_bills_count);
  const horizon = num(props.bills_horizon_days, 14);
  const covered = balance - billsEur >= 0;
  return (
    <div className="hero calm">
      <h3>Your pension</h3>
      <div className="amount">{eur(pension)}<span className="per"> a month</span></div>
      {received
        ? <div className="line">✓ Received on {longDate(received)}</div>
        : <div className="line">Paid every month</div>}
      <div className="kv">
        {next && <div>Next pension<b>{shortDate(next)}</b></div>}
        <div>Bills next {horizon} days<b>{billsCount} · {eur(billsEur)}</b></div>
        <div>Left after bills<b>{eur(balance - billsEur)}</b></div>
      </div>
      <span className="pill">{covered ? "✓ Your bills are covered" : "Your bills need more than your balance"}</span>
    </div>
  );
}
