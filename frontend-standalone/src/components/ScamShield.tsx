import { arr, str, type SectionProps } from "./types";

export default function ScamShield({ props, ctx }: SectionProps) {
  const tips = arr<string>(props.tips).slice(0, 3);
  const hotline = str(props.hotline);
  return (
    <div className="card-box" style={{ borderColor: "var(--primary)" }}>
      <h3>🛡️ Stay safe</h3>
      <ul style={{ margin: 0, paddingLeft: 16, fontSize: ".86em", lineHeight: 1.45 }}>
        {tips.map((t, i) => <li key={i}>{t}</li>)}
      </ul>
      {hotline && (
        <button
          type="button"
          onClick={() => ctx.onCta("call_card_stop")}
          style={{
            marginTop: 10, width: "100%", padding: "9px 10px", borderRadius: 10, border: "var(--border-w) solid var(--primary)",
            background: "transparent", color: "var(--primary)", fontWeight: 700, fontSize: ".86em",
          }}
        >
          📞 {hotline}
        </button>
      )}
    </div>
  );
}
