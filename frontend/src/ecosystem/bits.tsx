// Small shared pieces of the ecosystem UI. Text nodes only.
import { useEur } from "../privacy";
import type { ProductRef, ProviderPublic, StepStatus, WinTotals } from "./types";

export function ProgressRing({ done, total, size = 44 }: { done: number; total: number; size?: number }) {
  const r = (size - 6) / 2;
  const c = 2 * Math.PI * r;
  const frac = total > 0 ? Math.min(1, done / total) : 0;
  return (
    <svg className="eco-ring" width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${done} of ${total} steps done`}>
      <circle cx={size / 2} cy={size / 2} r={r} className="track" />
      <circle
        cx={size / 2} cy={size / 2} r={r} className="fill"
        strokeDasharray={c} strokeDashoffset={c * (1 - frac)}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle">{done}/{total}</text>
    </svg>
  );
}

export function KindBadge({ provider }: { provider: Pick<ProviderPublic, "kind"> }) {
  return provider.kind === "kbc"
    ? <span className="eco-kind kbc">KBC</span>
    : <span className="eco-kind partner">✓ Vetted partner</span>;
}

export function ProductChips({ products }: { products: ProductRef[] }) {
  if (!products.length) return null;
  return (
    <div className="eco-chips">
      {products.map((p) => (
        <span key={`${p.id}-${p.partner ?? ""}`} className="eco-chip">{p.partner || p.name.startsWith("KBC") ? p.name : `KBC ${p.name}`}</span>
      ))}
    </div>
  );
}

const STATUS_LABEL: Record<StepStatus, string> = {
  proposed: "To review", approved: "Approved", in_progress: "In progress", done: "Done", declined: "Declined", blocked: "Blocked",
};

export function StatusPill({ status, held }: { status: StepStatus; held?: boolean }) {
  if (held) return <span className="eco-pill done">Already with KBC ✓</span>;
  return (
    <span className={`eco-pill ${status}`}>
      {status === "in_progress" && <i className="eco-spin" aria-hidden="true" />}
      {status === "done" ? "✓ Done" : STATUS_LABEL[status]}
    </span>
  );
}

export function hours(h: number): string {
  const r = Math.round(h);
  return `${r} ${r === 1 ? "hour" : "hours"}`;
}

/** "€6.000 saved · 22 hours" */
export function useWinLine() {
  const eur = useEur();
  return (w: Pick<WinTotals, "customer_eur" | "hours_saved">) => {
    const parts: string[] = [];
    if (w.customer_eur > 0) parts.push(`${eur(w.customer_eur)} saved`);
    if (w.hours_saved > 0) parts.push(hours(w.hours_saved));
    return parts.join(" · ");
  };
}
