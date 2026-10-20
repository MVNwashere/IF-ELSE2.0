// How a card looks at a glance: an icon that says what it is about, and a tone that says how much it matters.
import type { Card } from "../api";
import { Icon } from "../components/icons";

const BY_TYPE: Record<string, string> = {
  core_coming_up: "calendar", core_unusual: "alert", core_spending: "cart", core_insurance: "insurance",
  core_money: "savings", core_goals: "savings", core_health: "trend", core_debt: "budget", core_cards: "card",
  core_investments: "trend",
  vat_reserve: "invoice", late_client: "invoice", insurance_renewal: "insurance", protection_gap: "insurance",
  price_increase: "tag", new_payee: "alert", duplicate_charge: "alert", runway: "alert",
  idle_cash: "trend", cashflow_squeeze: "budget", pension_savings: "pension", life_event: "sparkle",
  scam_awareness: "insurance",
};
const BY_KIND: Record<string, string> = {
  editorial: "book", insight: "trend", product: "tag", tool: "budget", action: "calendar",
};

export function cardIcon(card: Pick<Card, "card_type" | "details" | "family">): string {
  const kind = typeof card.details?.kind === "string" ? card.details.kind : "";
  return BY_TYPE[card.card_type] ?? BY_KIND[kind] ?? (card.family === "protection" ? "insurance" : "budget");
}

/** urgent → red, soon → amber, an opportunity → green, a tip or explainer → quiet; otherwise the plain card. */
export function cardTone(card: Pick<Card, "stage" | "family" | "details" | "commercial">): string {
  if (card.stage === "urgent") return "tone-urgent";
  if (card.stage === "soon") return "tone-soon";
  if (card.details?.kind === "editorial") return "tone-quiet";
  if (card.family === "opportunity" && !card.commercial) return "tone-good";
  return "";
}

export function CardGlyph({ card }: { card: Pick<Card, "card_type" | "details" | "family"> }) {
  return <Icon name={cardIcon(card)} />;
}
