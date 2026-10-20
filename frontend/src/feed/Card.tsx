import { motion, useMotionValue, useTransform } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import type { Card as CardT, Decision } from "../api";
import { longDate } from "../format";
import { maskText, useEur, useMasked } from "../privacy";
import { FAMILY_ICON } from "../components/icons";

interface Props {
  card: CardT;
  asOf: string;
  onFeedback: (card: CardT, decision: Decision) => void;
  onCta: (action: string) => void;
  onAskKate: (cardKey: string) => void;
  onOpen: () => void;
}

interface ComparisonRow { item: string; current: string; kbc: string }

const STAGE_LABEL: Record<string, string> = { early: "upcoming", soon: "soon", urgent: "urgent", info: "" };

export default function Card({ card, asOf, onFeedback, onCta, onAskKate, onOpen }: Props) {
  const eur = useEur();
  const masked = useMasked();
  const [menu, setMenu] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const x = useMotionValue(0);
  const hintOpacity = useTransform(x, [-120, -30, 0], [1, 0.3, 0]);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menu) return;
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setMenu(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menu]);

  const daysLeft = card.due_date ? Math.round((new Date(card.due_date + "T00:00:00").getTime() - new Date(asOf + "T00:00:00").getTime()) / 86_400_000) : null;
  const comparison = Array.isArray(card.details?.comparison) ? (card.details.comparison as ComparisonRow[]) : [];
  const impactYearly = card.card_type === "insurance_renewal" || card.card_type === "price_increase";

  const act = (d: Decision) => { setMenu(false); onFeedback(card, d); };

  return (
    <div style={{ position: "relative" }} ref={ref} data-card-key={card.card_key}>
      <motion.div className="swipe-hint" style={{ opacity: hintOpacity }}>Dismiss ✕</motion.div>
      <motion.div
        className={`fcard stage-${card.stage} ${card.card_type === "core_money" ? "core-money" : ""}`}
        style={{ x }}
        drag="x"
        dragConstraints={{ left: 0, right: 0 }}
        dragElastic={{ left: 0.6, right: 0.05 }}
        onDragEnd={(_, info) => { if (info.offset.x < -120) onFeedback(card, "dismiss"); }}
        whileDrag={{ cursor: "grabbing" }}
      >
        <div className="top">
          <span className="fam" title={card.family}>{FAMILY_ICON[card.family] ?? "•"} {card.family}</span>
          {STAGE_LABEL[card.stage] && <span className={`stage ${card.stage}`}>{STAGE_LABEL[card.stage]}</span>}
          <span className="spacer" />
          <button type="button" aria-label="Why am I seeing this?" title="Why am I seeing this?" onClick={() => setDrawer((v) => !v)}>ⓘ</button>
          <button type="button" aria-label="More" onClick={() => setMenu((v) => !v)}>⋯</button>
        </div>
        <h3>{maskText(card.title, masked)}</h3>
        <p>{maskText(card.body, masked)}</p>
        {Array.isArray(card.details?.metrics) && card.details.metrics.length > 1 && card.card_type === "core_money" && (
          <div className="core-breakdown" aria-label="Money by account type">
            {(card.details.metrics as {label: string; value: number}[]).filter((row) => row.value > 0).map((row) =>
              <span key={row.label} title={`${row.label}: ${eur(row.value)}`} style={{ flex: row.value }} />)}
          </div>
        )}
        {Array.isArray(card.details?.metrics) && card.card_type.startsWith("core_") && card.card_type !== "core_money" && (
          <div className="core-preview">
            {(card.details.metrics as {label: string; value: number}[]).slice(0, 3).map((row, i) =>
              <div key={`${row.label}-${i}`}><span>{row.label}</span><b>{card.details.metric_unit === "%" ? `${row.value}%` : eur(row.value)}</b></div>)}
          </div>
        )}
        <div className="bottom">
          {card.eur_impact > 0 && <span className="impact">{eur(card.eur_impact)}{impactYearly ? "/yr" : ""}</span>}
          {card.due_date && (
            <span className="due">
              {daysLeft !== null && daysLeft >= 0 ? `in ${daysLeft} ${daysLeft === 1 ? "day" : "days"}` : longDate(card.due_date)}
            </span>
          )}
          {card.commercial && <span className="commercial">offer</span>}
          <button type="button" className="card-open" onClick={onOpen}>View details</button>
          <button type="button" className="ask-kate" title="Ask Kate about this" onClick={() => onAskKate(card.card_key)}>
            <span className="kate-dot" aria-hidden="true">K</span>Ask Kate
          </button>
          {card.cta && (
            <button type="button" className="cta" onClick={() => onCta(card.cta!.action)}>{card.cta.label}</button>
          )}
        </div>

        {menu && (
          <div className="menu">
            <button type="button" onClick={() => act("accept")}>✓ Done / accept</button>
            <button type="button" onClick={() => act("snooze")}>⏰ Snooze 7 days</button>
            <button type="button" onClick={() => act("less")}>Show me less of this</button>
            <button type="button" className="danger" onClick={() => act("dismiss")}>Not relevant to me</button>
          </div>
        )}

        {drawer && (
          <div className="drawer">
            <h4>Why am I seeing this?</h4>
            <ul>{card.evidence.map((e, i) => <li key={i}>{e}</li>)}</ul>
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <span className="rank">{card.rank_explanation}</span>
              <span>confidence {Math.round(card.confidence * 100)}%</span>
            </div>
            {comparison.length > 0 && (
              <>
                <h4 style={{ marginTop: 10 }}>Compared to what you pay now</h4>
                <table>
                  <thead><tr><th></th><th>Now</th><th>KBC</th></tr></thead>
                  <tbody>
                    {comparison.map((r, i) => (
                      <tr key={i}><td>{r.item}</td><td>{r.current}</td><td>{r.kbc}</td></tr>
                    ))}
                  </tbody>
                </table>
                <div style={{ marginTop: 6, fontSize: ".85em" }}>KBC figures are illustrative. Your current policy's terms are not known to us.</div>
              </>
            )}
          </div>
        )}
      </motion.div>
    </div>
  );
}
