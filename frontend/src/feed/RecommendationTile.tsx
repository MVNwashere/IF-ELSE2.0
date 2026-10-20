import type { Card } from "../api";
import { shortDate } from "../format";
import { maskFrac, maskText, useEur, useMasked } from "../privacy";
import { CardGlyph, cardTone } from "./cardVisuals";

type Metric = { label: string; value: number };
type Upcoming = { date: string; name: string; category: string; amount: number };

function metricsFor(card: Card): Metric[] {
  return Array.isArray(card.details.metrics)
    ? card.details.metrics.filter((row): row is Metric =>
      !!row && typeof row.label === "string" && typeof row.value === "number" && Number.isFinite(row.value))
    : [];
}

function upcomingFor(card: Card): Upcoming[] {
  return Array.isArray(card.details.items)
    ? card.details.items.filter((i): i is Upcoming => !!i && typeof i.name === "string" && typeof i.amount === "number")
    : [];
}

const isExplainer = (card: Card) => card.details.kind === "editorial" && metricsFor(card).length === 0;

export function wideTile(card: Card): boolean {
  if (card.card_type === "core_coming_up" || card.card_type === "core_spending") return true;
  if (isExplainer(card) || card.card_type === "core_insurance") return false;
  return card.stage === "urgent" || metricsFor(card).length > 2 || card.body.length > 110 || !!card.details.planner;
}

/** eur_impact is a yearly amount for these: a price change, a cheaper renewal, interest or tax back */
const YEARLY = new Set(["insurance_renewal", "price_increase", "idle_cash", "pension_savings"]);

const SPEND_COLOURS = ["var(--primary)", "#12a99b", "#f59e0b", "#8b5cf6", "#ef4444", "#64748b"];

function status(card: Card): [string, string] | null {
  if (card.stage === "urgent") return ["Needs attention", "urgent"];
  if (card.stage === "soon") return ["Soon", "soon"];
  if (card.commercial) return ["Offer", ""];
  if (card.details.kind === "editorial") return ["Tip", ""];
  return null;
}

export default function RecommendationTile({ card, onOpen }: { card: Card; onOpen: () => void }) {
  const eur = useEur();
  const masked = useMasked();
  const metrics = metricsFor(card);
  const unit = card.details.metric_unit;
  const value = (amount: number) => unit === "%" ? `${amount}%` : unit === "months" ? `${amount} month${amount === 1 ? "" : "s"}` : eur(amount);
  const planner = card.details.planner as { kind?: string; current?: number; target?: number; monthly?: number } | undefined;
  const total = typeof card.details.total === "number" ? card.details.total : null;
  const pill = status(card);
  const tone = cardTone(card);
  const explainer = isExplainer(card);

  let body: React.ReactNode;
  if (card.card_type === "core_coming_up") {
    const items = upcomingFor(card);
    body = <>
      <strong className="tile-main-value">{eur(total ?? 0)}<small> next {Number(card.details.horizon_days ?? 30)} days</small></strong>
      <span className="tile-list">
        {items.slice(0, 3).map((i, n) => (
          <span className="tile-row" key={`${i.date}-${i.name}-${n}`}>
            <span className="tile-row-date">{shortDate(i.date)}</span>
            <span className="tile-row-name">{maskText(i.name, masked)}</span>
            <strong>{eur(i.amount)}</strong>
          </span>
        ))}
        {items.length > 3 && <small>+ {items.length - 3} more</small>}
      </span>
    </>;
  } else if (card.card_type === "core_spending") {
    const sum = Math.max(1, metrics.reduce((n, m) => n + m.value, 0));
    body = <>
      <strong className="tile-main-value">{eur(total ?? sum)}<small> so far this month</small></strong>
      <span className="tile-stack" aria-hidden="true">
        {metrics.map((m, i) => <span key={m.label} style={{ flex: maskFrac(m.value / sum, masked) || 1, background: SPEND_COLOURS[i % SPEND_COLOURS.length] }} />)}
      </span>
      <span className="tile-legend">
        {metrics.slice(0, 4).map((m, i) => (
          <span key={m.label}><i style={{ background: SPEND_COLOURS[i % SPEND_COLOURS.length] }} />{m.label}<strong>{eur(m.value)}</strong></span>
        ))}
      </span>
    </>;
  } else if (card.card_type === "core_unusual" && metrics.length === 2) {
    const lowDate = typeof card.details.low_date === "string" ? card.details.low_date : null;
    body = <>
      <span className="tile-description">{maskText(card.body, masked)}</span>
      <span className="tile-dip">
        <span><small>Today</small><strong>{eur(metrics[0].value)}</strong></span>
        <span className="tile-dip-arrow" aria-hidden="true">→</span>
        <span className="low"><small>Lowest{lowDate ? ` · ${shortDate(lowDate)}` : ""}</small><strong>{eur(metrics[1].value)}</strong></span>
      </span>
    </>;
  } else {
    body = <>
      {card.card_type === "core_insurance" && total !== null
        ? <strong className="tile-main-value">{eur(total)}<small> a year</small></strong> : null}
      <span className="tile-description">{maskText(card.body, masked)}</span>
      {metrics.length > 0 && card.card_type !== "core_insurance" && <span className="tile-metrics">
        {metrics.slice(0, 3).map((row, i) => <span className="tile-metric" key={`${row.label}-${i}`}><span>{maskText(row.label, masked)}</span><strong>{value(row.value)}</strong></span>)}
      </span>}
      {card.card_type === "core_insurance" && <span className="tile-metrics">
        {metrics.slice(0, 3).map((row, i) => <span className="tile-metric" key={`${row.label}-${i}`}><span>{maskText(row.label, masked)}</span><strong>{eur(row.value)}</strong></span>)}
      </span>}
      {planner?.kind === "savings" && typeof planner.target === "number" && typeof planner.current === "number" && <>
        <span className="tile-metrics">
          <span className="tile-metric"><span>{card.card_type === "core_goals" ? "Saved / target" : "Now / goal"}</span><strong>{eur(planner.current)} / {eur(planner.target)}</strong></span>
        </span>
        {!masked && <span className="tile-progress" aria-hidden="true"><span style={{ width: `${Math.max(0, Math.min(100, planner.target > 0 ? planner.current / planner.target * 100 : 0))}%` }} /></span>}
      </>}
      {(card.eur_impact > 0 || card.due_date) && <span className="tile-facts">
        {card.eur_impact > 0 && <span>{eur(card.eur_impact)} {YEARLY.has(card.card_type) ? "a year" : card.family === "opportunity" ? "to gain" : "at stake"}</span>}
        {card.due_date && <span>Due {shortDate(card.due_date)}</span>}
      </span>}
    </>;
  }

  return (
    <button type="button" className={`recommendation-tile ${card.stage} ${tone}${explainer ? " explainer" : ""}`} onClick={onOpen}>
      <span className="recommendation-topline">
        <span className="recommendation-tile-icon" aria-hidden="true"><CardGlyph card={card} /></span>
        {pill && <span className={`tile-status ${pill[1]}`}>{pill[0]}</span>}
      </span>
      <b className="recommendation-title">{card.card_type === "core_goals" ? "Savings planner" : maskText(card.title, masked)}</b>
      {body}
      <span className="recommendation-link">{card.cta && card.details.playbook_id ? "KBC can take care of it ›" : "Details & why ›"}</span>
    </button>
  );
}
