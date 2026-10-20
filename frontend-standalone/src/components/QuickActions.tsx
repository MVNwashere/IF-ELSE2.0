import { Icon } from "./icons";
import { arr, type SectionProps } from "./types";

interface Action { label: string; action: string; icon: string }

export default function QuickActions({ props, ctx }: SectionProps) {
  const actions = arr<Action>(props.actions).slice(0, 4);
  return (
    <div className="qa" style={{ gridTemplateColumns: `repeat(${Math.max(1, actions.length)}, 1fr)` }}>
      {actions.map((a) => (
        <button key={a.action} type="button" onClick={() => ctx.onCta(a.action)}>
          <span className="ico"><Icon name={a.icon} /></span>
          <span>{a.label}</span>
        </button>
      ))}
    </div>
  );
}
