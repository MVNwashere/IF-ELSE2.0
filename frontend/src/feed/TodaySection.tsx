// "Today": what needs the customer now, right under the KBC ball. The persona's own main tile (VAT reserve, pension,
// family budget), up to two urgent moments with their one action, and the goal KBC noticed. Everything else stays in
// the For you wall below.
import { motion } from "framer-motion";
import type { Card, Section } from "../api";
import { resolve } from "../components/registry";
import type { SectionCtx } from "../components/types";
import type { GoalCandidate } from "../ecosystem/types";
import { useWinLine } from "../ecosystem/bits";
import { maskText, useEur, useMasked } from "../privacy";
import { CardGlyph } from "./cardVisuals";

/** Main tiles that only repeat the balance in the ball stay off Today. */
const BALLS_JOB = new Set(["BalanceHero"]);
export const TODAY_MAX_URGENT = 2;

interface Props {
  hero: Section | undefined;
  urgent: Card[];
  noticed: GoalCandidate | null;
  ctx: SectionCtx;
  onDetails: (card: Card) => void;
  onAskKate: (cardKey: string) => void;
  onCta: (action: string, card?: Card) => void;
  onPreviewGoal: (candidate: GoalCandidate) => void;
}

function Attention({ card, onDetails, onAskKate, onCta }: {
  card: Card; onDetails: () => void; onAskKate: () => void; onCta: (action: string, card?: Card) => void;
}) {
  const masked = useMasked();
  const eur = useEur();
  const alt = card.details.alt_cta as { label: string; action: string } | undefined;
  return (
    <article className={`today-alert ${card.family}`} aria-label={maskText(card.title, masked)}>
      <div className="today-alert-top">
        <span className="today-alert-icon" aria-hidden="true"><CardGlyph card={card} /></span>
        <span className="today-alert-kicker">Needs you{card.due_date ? "" : " now"}</span>
        {card.eur_impact > 0 && <span className="today-alert-amount">{eur(card.eur_impact)}</span>}
      </div>
      <h3>{maskText(card.title, masked)}</h3>
      <p>{maskText(card.body, masked)}</p>
      <div className="today-alert-actions">
        {alt && <button type="button" className="btn-danger small" onClick={() => onCta(alt.action, card)}>{alt.label}</button>}
        {card.cta && <button type="button" className={alt ? "btn-ghost small" : "btn-primary small"} onClick={() => onCta(card.cta!.action, card)}>{card.cta.label}</button>}
        <button type="button" className="today-ask" onClick={onAskKate}><span className="kate-dot" aria-hidden="true">K</span>Ask Kate</button>
        <button type="button" className="link" onClick={onDetails}>Why this?</button>
      </div>
    </article>
  );
}

export default function TodaySection({ hero, urgent, noticed, ctx, onDetails, onAskKate, onCta, onPreviewGoal }: Props) {
  const masked = useMasked();
  const winLine = useWinLine();
  const Hero = hero && !BALLS_JOB.has(hero.component) ? resolve(hero.component) : null;
  const shown = urgent.slice(0, TODAY_MAX_URGENT);
  if (!Hero && !shown.length && !noticed) return null;
  const potential = noticed ? winLine(noticed.potential) : "";
  return (
    <section className="today" aria-label="Today">
      <h2 className="today-h">Today</h2>
      {Hero && hero && <motion.div className="today-hero" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
        <Hero props={hero.props} ctx={ctx} />
      </motion.div>}
      {shown.map((card, i) => (
        <motion.div key={card.card_key} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.06 * (i + 1) }}
          data-card-key={card.card_key}>
          <Attention card={card} onDetails={() => onDetails(card)} onAskKate={() => onAskKate(card.card_key)} onCta={onCta} />
        </motion.div>
      ))}
      {noticed && (
        <motion.button type="button" className="today-noticed" onClick={() => onPreviewGoal(noticed)}
          initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.06 * (shown.length + 1) }}>
          <span className="today-noticed-icon" aria-hidden="true">{noticed.icon}</span>
          <span className="today-noticed-body">
            <span className="today-noticed-kicker">KBC noticed</span>
            <b>{maskText(noticed.title, masked)}</b>
            <span>{maskText(noticed.why_now, masked)}</span>
            <span className="today-noticed-foot">{potential && <small>{potential}</small>}<em>See the plan ›</em></span>
          </span>
        </motion.button>
      )}
    </section>
  );
}
