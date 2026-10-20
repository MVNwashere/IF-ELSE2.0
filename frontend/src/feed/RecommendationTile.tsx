import type { Card } from "../api";
import { Icon } from "../components/icons";
import { shortDate } from "../format";
import { maskText, useEur, useMasked } from "../privacy";

type Metric = { label: string; value: number };
function metricsFor(card: Card): Metric[] {
  return Array.isArray(card.details.metrics)
    ? card.details.metrics.filter((row): row is Metric =>
      !!row && typeof row.label === "string" && typeof row.value === "number" && Number.isFinite(row.value))
    : [];
}

export function wideTile(card: Card): boolean {
  if (card.card_type === "core_money" || card.card_type === "core_coming_up") return false;
  return card.stage === "urgent" || metricsFor(card).length > 2 || card.body.length > 100 || !!card.details.planner;
}

export default function RecommendationTile({ card, onOpen }: { card: Card; onOpen: () => void }) {
  const eur = useEur();
  const masked = useMasked();
  const metrics = metricsFor(card);
  const money = card.card_type === "core_money" && metrics.length > 0;
  const upcoming = card.card_type === "core_coming_up" && metrics.length > 0;
  const unit = card.details.metric_unit;
  const value = (amount: number) => unit === "%" ? `${amount}%` : unit === "months" ? `${amount} months` : eur(amount);
  const planner = card.details.planner as { kind?: string; current?: number; target?: number; monthly?: number } | undefined;
  const preview = upcoming ? metrics.slice(1, 3) : money && metrics.length === 1 ? [] : metrics.slice(0, 3);
  const icon = money ? "savings" : upcoming ? "pension" : card.family === "protection" ? "shield" : card.family === "opportunity" ? "savings" : "budget";
  return (
    <button type="button" className={`recommendation-tile ${card.stage}`} onClick={onOpen}>
      <span className="recommendation-topline">
        <span className="recommendation-tile-icon" aria-hidden="true"><Icon name={icon} /></span>
        {card.stage === "urgent" ? <span className="tile-status urgent">Needs attention</span>
          : card.commercial ? <span className="tile-status">Offer</span> : null}
      </span>
      <b className="recommendation-title">{card.card_type === "core_goals" ? "Savings planner" : maskText(card.title, masked)}</b>
      {money ? <>
        <strong className="tile-main-value">{eur(metrics.reduce((sum, row) => sum + row.value, 0))}</strong>
        <span className="tile-description">Across known accounts</span>
      </> : upcoming ? <>
        <strong className="tile-main-value">{eur(metrics[0].value)}</strong>
        <span className="tile-description">Next payment · {metrics[0].label}</span>
      </> : <span className="tile-description">{maskText(card.body, masked)}</span>}
      {preview.length > 0 && <span className="tile-metrics">
        {preview.map((row, i) => <span className="tile-metric" key={`${row.label}-${i}`}><span>{maskText(row.label, masked)}</span><strong>{value(row.value)}</strong></span>)}
        {metrics.length > 3 && <small>+ {metrics.length - 3} more in details</small>}
      </span>}
      {planner?.kind === "savings" && typeof planner.target === "number" && typeof planner.current === "number" && <>
        <span className="tile-metrics">
          <span className="tile-metric"><span>Saved / target</span><strong>{eur(planner.current)} / {eur(planner.target)}</strong></span>
          {typeof planner.monthly === "number" && <span className="tile-metric"><span>Monthly plan</span><strong>{eur(planner.monthly)}</strong></span>}
        </span>
        {!masked && <span className="tile-progress" aria-hidden="true"><span style={{ width: `${Math.max(0, Math.min(100, planner.target > 0 ? planner.current / planner.target * 100 : 0))}%` }} /></span>}
      </>}
      {(card.eur_impact > 0 || (card.due_date && !upcoming)) && <span className="tile-facts">
        {card.eur_impact > 0 && <span>{eur(card.eur_impact)} {card.card_type === "insurance_renewal" || card.card_type === "price_increase" ? "/ year" : "potential impact"}</span>}
        {card.due_date && !upcoming && <span>Due {shortDate(card.due_date)}</span>}
      </span>}
      <span className="recommendation-link">View details <span aria-hidden="true">↗</span></span>
    </button>
  );
}
