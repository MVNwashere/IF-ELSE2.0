import { arr, str, type SectionProps } from "./types";

export default function KateTile({ props, ctx }: SectionProps) {
  const prompt = str(props.prompt, "Hi, I'm Kate. Ask me anything about your money.");
  const cardKey = typeof props.card_key === "string" ? props.card_key : null;
  const chips = arr<string>(props.quick_replies).filter((q) => typeof q === "string").slice(0, 2);
  return (
    <div className="card-box kate-tile">
      <button type="button" className="kate-tile-main" onClick={() => ctx.openKate(cardKey)}>
        <span className="kate-avatar" aria-hidden="true">K</span>
        <span className="kate-tile-text">
          <b>Kate</b>
          <span>{prompt}</span>
        </span>
      </button>
      {chips.length > 0 && (
        <div className="kate-chips">
          {chips.map((q) => (
            <button key={q} type="button" className="kate-chip" onClick={() => ctx.openKate(cardKey, q)}>{q}</button>
          ))}
        </div>
      )}
    </div>
  );
}
