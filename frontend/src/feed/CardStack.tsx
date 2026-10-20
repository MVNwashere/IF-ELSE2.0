import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import type { Card as CardT, Decision } from "../api";
import { maskText, useEur, useMasked } from "../privacy";
import Sheet from "../ui/Sheet";
import Card from "./Card";
import CaughtUp from "./CaughtUp";

interface Props {
  cards: CardT[];
  caughtUp: boolean;
  hiddenCount: number;
  asOf: string;
  onFeedback: (card: CardT, decision: Decision) => void;
  onCta: (action: string) => void;
  onAskKate: (cardKey: string) => void;
}

type DetailCard = Pick<CardT, "card_key" | "card_type" | "title" | "body" | "evidence" | "details">;

export default function CardStack({ cards, caughtUp, hiddenCount, asOf, onFeedback, onCta, onAskKate }: Props) {
  const [active, setActive] = useState<{ title: string; body: string; card?: DetailCard } | null>(null);
  const [target, setTarget] = useState(0);
  const [monthly, setMonthly] = useState(0);
  const eur = useEur();
  const masked = useMasked();
  const phone = typeof document === "undefined" ? null : document.querySelector<HTMLElement>(".phone");
  const metrics = active?.card?.details?.metrics;
  const related = active?.card?.details?.related_cards;
  const planner = active?.card?.details?.planner as { kind: string; target: number; current: number; monthly: number } | undefined;
  useEffect(() => {
    if (planner?.kind === "savings") {
      setTarget(planner.target);
      setMonthly(planner.monthly);
    }
  }, [active?.card?.card_key]);
  useEffect(() => { setActive(null); }, [asOf]);
  const monthsToTarget = planner?.kind === "savings" && monthly > 0
    ? Math.ceil(Math.max(0, target - planner.current) / monthly) : null;
  return (
    <div className="feed">
      <div className="feed-head">
        <h2>For you</h2>
        <span>{cards.length} {cards.length === 1 ? "item" : "items"}</span>
      </div>
      <AnimatePresence initial={false} mode="popLayout">
        {cards.map((c) => (
          <motion.div
            key={c.card_key}
            layout
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, x: -80, scale: 0.96, transition: { duration: 0.22 } }}
            transition={{ type: "spring", stiffness: 380, damping: 32 }}
          >
            <Card card={c} asOf={asOf} onFeedback={onFeedback} onCta={onCta} onAskKate={onAskKate}
              onOpen={() => setActive({ title: c.title, body: c.body, card: c })} />
          </motion.div>
        ))}
      </AnimatePresence>
      {(caughtUp || cards.length === 0) && (
        <motion.div layout key="caught-up">
          <CaughtUp hiddenCount={hiddenCount} empty={cards.length === 0} />
        </motion.div>
      )}
      {active && phone && createPortal(
        <Sheet title={maskText(active.title, masked)} onClose={() => setActive(null)} full>
          <div className="feed-detail">
            <p>{maskText(active.body, masked)}</p>
            {Array.isArray(metrics) && metrics.length > 0 && (
              <div className="feed-detail-metrics">
                {(metrics as { label: string; value: number }[]).map((row, i) => (
                  <div key={`${row.label}-${i}`}><span>{row.label}</span><b>{active.card?.details.metric_unit === "%" ? `${row.value}%` : active.card?.details.metric_unit === "months" ? `${row.value} months` : eur(row.value)}</b></div>
                ))}
              </div>
            )}
            {planner?.kind === "savings" && (masked ? <p>Reveal amounts to use this planner.</p> : <div className="feed-planner">
              <h3>Try a savings plan</h3>
              <p>Starting from {eur(planner.current)} available toward this target.</p>
              <label>Target (€)<input type="number" min="0" step="10" value={target}
                onChange={(event) => setTarget(Math.max(0, event.currentTarget.valueAsNumber || 0))} /></label>
              <label>Set aside each month (€)<input type="number" min="0" step="10" value={monthly}
                onChange={(event) => setMonthly(Math.max(0, event.currentTarget.valueAsNumber || 0))} /></label>
              <strong>{monthsToTarget === null ? "Enter a monthly amount" :
                monthsToTarget === 0 ? "Target already covered" : `About ${monthsToTarget} months to reach this target`}</strong>
              <small>Estimate only. No transfer is scheduled.</small>
            </div>)}
            {typeof active.card?.details.methodology === "string" && <p>{active.card.details.methodology}</p>}
            {active.card?.evidence.length ? <>
              <h3>Why you're seeing this</h3>
              <ul>{active.card.evidence.map((line, i) => <li key={i}>{maskText(line, masked)}</li>)}</ul>
            </> : null}
            {Array.isArray(related) && related.length > 0 && <>
              <h3>Related cards</h3>
              <div className="feed-related">
                {(related as DetailCard[]).map((item) => (
                  <button key={item.card_type} type="button" onClick={() => {
                    const card = cards.find((c) => c.card_type === item.card_type);
                    setActive(card ? { title: card.title, body: card.body, card } :
                      { title: item.title, body: item.body, card: item });
                  }}>{item.title} <span aria-hidden="true">→</span></button>
                ))}
              </div>
            </>}
          </div>
        </Sheet>, phone)}
    </div>
  );
}
