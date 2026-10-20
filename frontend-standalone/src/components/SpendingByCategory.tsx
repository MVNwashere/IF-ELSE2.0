import { categoryLabel } from "../format";
import { useEur } from "../privacy";
import { arr, num, str, type SectionProps } from "./types";

interface Cat { category: string; eur: number }

export default function SpendingByCategory({ props }: SectionProps) {
  const eur = useEur();
  const month = str(props.month_label, "This month");
  const total = num(props.total_eur);
  const cats = arr<Cat>(props.categories).slice(0, 6);
  const max = Math.max(1, ...cats.map((c) => c.eur));
  return (
    <div className="card-box">
      <h3>Spending · {month}</h3>
      <div className="big">{eur(total)}</div>
      <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}>
        {cats.map((c) => (
          <div key={c.category}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: ".78em" }}>
              <span>{categoryLabel(c.category)}</span>
              <span style={{ fontWeight: 700 }}>{eur(c.eur)}</span>
            </div>
            <div style={{ height: 6, borderRadius: 3, background: "var(--border)", overflow: "hidden", marginTop: 2 }}>
              <div style={{ width: `${(c.eur / max) * 100}%`, height: "100%", background: "var(--primary)", transition: "width .5s ease" }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
