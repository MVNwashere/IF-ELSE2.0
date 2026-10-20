import { useEur } from "../privacy";
import { num, str, type SectionProps } from "./types";

export default function SavingsGoal({ props }: SectionProps) {
  const eur = useEur();
  const label = str(props.goal_label, "Savings");
  const saved = num(props.saved_eur);
  const target = num(props.target_eur);
  const monthly = num(props.monthly_eur);
  const ratio = target > 0 ? Math.min(1, saved / target) : 0;
  const r = 26, c = 2 * Math.PI * r;
  return (
    <div className="card-box">
      <h3>{label}</h3>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <svg width="64" height="64" viewBox="0 0 64 64" aria-hidden="true">
          <circle cx="32" cy="32" r={r} fill="none" stroke="var(--border)" strokeWidth="7" />
          <circle
            cx="32" cy="32" r={r} fill="none" stroke="var(--primary)" strokeWidth="7" strokeLinecap="round"
            strokeDasharray={c} strokeDashoffset={c * (1 - ratio)} transform="rotate(-90 32 32)"
            style={{ transition: "stroke-dashoffset .6s ease" }}
          />
          <text x="32" y="36" textAnchor="middle" fontSize="13" fontWeight="800" fill="var(--text)">{Math.round(ratio * 100)}%</text>
        </svg>
        <div>
          <div className="big" style={{ fontSize: "1.2em" }}>{eur(saved)}</div>
          <div className="sub">of {eur(target)}</div>
          <div className="sub">{eur(monthly)} / month</div>
        </div>
      </div>
    </div>
  );
}
