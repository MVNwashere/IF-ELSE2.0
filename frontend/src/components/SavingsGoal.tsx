import { maskFrac, useEur, useMasked } from "../privacy";
import { num, str, type SectionProps } from "./types";

/** What was put aside in the last 12 months, against the next milestone still ahead. */
export default function SavingsGoal({ props }: SectionProps) {
  const eur = useEur();
  const masked = useMasked();
  const label = str(props.goal_label, "Savings");
  const saved = num(props.saved_eur);
  const target = num(props.target_eur);
  const monthly = num(props.monthly_eur);
  const ratio = maskFrac(target > 0 ? Math.min(1, saved / target) : 0, masked);
  const r = 26, c = 2 * Math.PI * r;
  return (
    <div className="card-box">
      <h3>{label}</h3>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <svg width="64" height="64" viewBox="0 0 64 64" aria-hidden="true" style={{ flexShrink: 0 }}>
          <circle cx="32" cy="32" r={r} fill="none" stroke="var(--border)" strokeWidth="7" />
          <circle
            cx="32" cy="32" r={r} fill="none" stroke="var(--primary)" strokeWidth="7" strokeLinecap="round"
            strokeDasharray={c} strokeDashoffset={c * (1 - ratio)} transform="rotate(-90 32 32)"
            style={{ transition: "stroke-dashoffset .6s ease" }}
          />
          <text x="32" y="36" textAnchor="middle" fontSize="13" fontWeight="800" fill="var(--text)">{masked ? "••" : `${Math.round(ratio * 100)}%`}</text>
        </svg>
        <div style={{ minWidth: 0 }}>
          <div className="big" style={{ fontSize: "1.2em" }}>{eur(saved)}</div>
          <div className="sub">put aside this year</div>
        </div>
      </div>
      <div className="sub" style={{ marginTop: 8 }}>Next milestone <b>{eur(target)}</b>{monthly > 0 ? <> · about {eur(monthly)} a month</> : null}</div>
    </div>
  );
}
