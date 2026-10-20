import { arr, str, type SectionProps } from "./types";

export default function AdvisorContact({ props, ctx }: SectionProps) {
  const name = str(props.advisor_name, "Your advisor");
  const reason = str(props.reason);
  const slots = arr<string>(props.slots).slice(0, 3);
  const initials = name.split(" ").map((s) => s[0]).join("").slice(0, 2).toUpperCase();
  return (
    <div className="card-box">
      <h3>Talk to a human</h3>
      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        <div style={{ width: 40, height: 40, borderRadius: "50%", background: "var(--primary)", color: "#fff", display: "grid", placeItems: "center", fontWeight: 800, flexShrink: 0 }}>
          {initials}
        </div>
        <div>
          <div style={{ fontWeight: 700, fontSize: ".95em" }}>{name}</div>
          {reason && <div className="sub">{reason}</div>}
        </div>
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 10 }}>
        {slots.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => ctx.onCta("book_advisor")}
            style={{ padding: "6px 10px", borderRadius: 8, border: "var(--border-w) solid var(--border)", background: "var(--card)", color: "var(--text)", fontSize: ".8em", fontWeight: 600 }}
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
