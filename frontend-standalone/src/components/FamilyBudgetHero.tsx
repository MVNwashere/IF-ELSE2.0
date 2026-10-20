import { categoryLabel } from "../format";
import { useEur } from "../privacy";
import { arr, num, str, type SectionProps } from "./types";

interface Cat { category: string; eur: number }

export default function FamilyBudgetHero({ props }: SectionProps) {
  const eur = useEur();
  const month = str(props.month_label, "This month");
  const income = num(props.month_income_eur);
  const spent = num(props.month_spent_eur);
  const budget = num(props.month_budget_eur);
  const childBenefit = num(props.child_benefit_eur);
  const childcare = num(props.childcare_eur);
  const cats = arr<Cat>(props.top_categories).slice(0, 4);
  const ratio = budget > 0 ? Math.min(1, spent / budget) : 0;
  const over = budget > 0 && spent > budget;
  return (
    <div className={`hero ${over ? "tight" : ""}`}>
      <h3>Family budget · {month}</h3>
      <div className="amount">
        {over
          ? <>{eur(spent - budget)} <span style={{ fontSize: ".45em", fontWeight: 600 }}>over budget</span></>
          : <>{eur(budget - spent)} <span style={{ fontSize: ".45em", fontWeight: 600 }}>to go</span></>}
      </div>
      <div className="line">{eur(spent)} spent of {eur(budget)} · {eur(income)} in so far</div>
      <div className="bar"><i style={{ width: `${ratio * 100}%` }} /></div>
      <div className="kv">
        <div>Child benefit<b>{eur(childBenefit)}</b></div>
        <div>Childcare<b>{eur(childcare)}</b></div>
        <div>Net for the kids<b>{eur(childBenefit - childcare, { sign: true })}</b></div>
      </div>
      {cats.length > 0 && (
        <div className="tags">
          {cats.map((c) => <span key={c.category}>{categoryLabel(c.category)} {eur(c.eur)}</span>)}
        </div>
      )}
    </div>
  );
}
