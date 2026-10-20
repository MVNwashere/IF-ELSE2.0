import { shortDate } from "../format";
import { useEur } from "../privacy";
import { num, str, type SectionProps } from "./types";

export default function RunwayHero({ props }: SectionProps) {
  const eur = useEur();
  const balance = num(props.balance_eur);
  const runway = typeof props.runway_days === "number" ? props.runway_days : null;
  const nextDate = str(props.next_income_date as string | null, "") || null;
  const nextEur = typeof props.next_income_eur === "number" ? props.next_income_eur : null;
  const daily = num(props.daily_budget_eur);
  const tight = runway !== null && runway <= 7;
  const warn = runway !== null && runway <= 21;
  return (
    <div className={`hero ${tight ? "danger" : warn ? "tight" : ""}`}>
      <h3>Until your next income</h3>
      <div className="amount">{eur(balance)} left</div>
      <div className="line">
        {nextDate
          ? <>{nextEur !== null ? <b>{eur(nextEur)}</b> : "Next income"} expected on {shortDate(nextDate)}</>
          : "No regular income detected yet"}
      </div>
      <div className="kv">
        <div>Per day until then<b>{eur(daily)}</b></div>
        {runway !== null && <div>Runway at current pace<b>{runway} days</b></div>}
      </div>
      {tight && <span className="pill">⚠ Tight week — spend carefully</span>}
    </div>
  );
}
