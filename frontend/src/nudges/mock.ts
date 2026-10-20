// A few nudges for ?mock=1 (same shapes as the backend). Acks are kept in memory.
import type { KateAction } from "../api";
import type { AckResponse, Nudge, NudgeAck, NudgeStats, NudgesResponse } from "./types";

const action = (a: Partial<KateAction> & Pick<KateAction, "kind" | "label">): KateAction => ({
  component: null, card_key: null, card_type: null, style: null, signal: null, playbook_id: null, goal_id: null, ...a,
});

const BASE: Omit<Nudge, "status">[] = [
  {
    nudge_key: "vat_return:2026-10", topic: "vat_return", tier: "deadline",
    title: "Q3 2026 VAT return, 20 Oct 2026: about €1.890 short",
    why: "€9.000 invoiced in Q3 2026. About €1.890 due 20 Oct 2026.",
    evidence: ["€9.000 invoiced in Q3 2026", "€1.200 on your account after this month's bills"],
    action: action({ kind: "open_card", label: "Set it aside", card_key: "vat_reserve:2026q3", card_type: "vat_reserve" }),
    open_view: null, delivered_at: "2026-10-06T08:00:00", channel: "push", digest_id: null, held_reason: null,
    mutable: true, source: "signals:vat_return",
  },
  {
    nudge_key: "insurance_renewal:2026-11", topic: "insurance_renewal", tier: "deadline",
    title: "Car insurance renews 1 Nov 2026: about €165 a year to save",
    why: "Yearly payment of €612 to AG Insurance on 1 Nov 2025. Compare before it renews; after that you're tied in for a year.",
    evidence: ["Yearly payment of €612 to AG Insurance on 1 Nov 2025", "No car insurance with KBC"],
    action: action({ kind: "open_card", label: "Compare cover", card_key: "insurance_renewal:ag-insurance-car", card_type: "insurance_renewal" }),
    open_view: null, delivered_at: "2026-10-11T08:00:00", channel: "push", digest_id: null, held_reason: null,
    mutable: true, source: "card:insurance_renewal",
  },
  {
    nudge_key: "intent_get_paid:once", topic: "intent_get_paid", tier: "moment",
    title: "💶 Get paid on time?",
    why: "Brouwerij Het Anker usually pays every ~30 days; the last payment was 118 days ago. KBC and its partners can collect it for you.",
    evidence: ["5 payments from Brouwerij Het Anker so far"],
    action: action({ kind: "start_goal", label: "Show me the plan", playbook_id: "get_paid" }),
    open_view: null, delivered_at: "2026-10-12T08:00:00", channel: "inbox", digest_id: null,
    held_reason: "Attention budget: 2 nudges a week, already used", mutable: true, source: "intent",
  },
];

const acks = new Map<string, NudgeAck>();

function withStatus(n: Omit<Nudge, "status">): Nudge {
  const a = acks.get(n.nudge_key);
  return { ...n, status: a === "opened" ? "opened" : a === "dismissed" ? "dismissed" : a === "mute" ? "muted" : "new" };
}

export const mockNudges = {
  list: async (asOf?: string, since?: string): Promise<NudgesResponse> => {
    const hi = asOf ?? "2026-10-20";
    const lo = since ?? "2026-09-20";
    const nudges = BASE.filter((n) => n.delivered_at.slice(0, 10) > lo && n.delivered_at.slice(0, 10) <= hi).map(withStatus);
    return {
      as_of: hi, since: lo, nudges, candidates: nudges.length, held: nudges.filter((n) => n.channel === "inbox").length,
      budget: { limit: 2, used: 1, window_days: 7, quiet_hours: "21:00–08:00", persona: "default" },
    };
  },
  ack: async (key: string, a: NudgeAck): Promise<AckResponse> => {
    acks.set(key, a);
    return { nudge_key: key, status: a === "mute" ? "muted" : a, muted_until: null };
  },
  reset: async () => { acks.clear(); return { ok: true }; },
  stats: async (): Promise<NudgeStats> => ({
    since: "2026-09-22", as_of: "2026-10-20", customers: 16, weeks: 4, pushes_per_customer_week: 0.33,
    non_urgent_per_customer_week: 0.25, max_non_urgent_any_7d: 2, budget_default: 2, budget_retiree: 1,
    candidates: 21, pushed_items: 21, held_items: 0, naive_pushes: 75, pushes: 21, noise_avoided_pct: 72,
    open_rate: null, dismiss_rate: null, mute_rate: null, acks: 0,
    by_tier: [
      { tier: "urgent", candidates: 5, pushed: 5, held: 0 }, { tier: "deadline", candidates: 15, pushed: 15, held: 0 },
      { tier: "waiting", candidates: 0, pushed: 0, held: 0 }, { tier: "moment", candidates: 1, pushed: 1, held: 0 },
    ],
    per_customer: [
      { label: "Lotte", persona: "default", pushes: 1, urgent: 0, held: 0, max_non_urgent_7d: 1, budget: 2 },
      { label: "Sara", persona: "default", pushes: 3, urgent: 0, held: 0, max_non_urgent_7d: 1, budget: 2 },
      { label: "Jan", persona: "retiree", pushes: 2, urgent: 2, held: 0, max_non_urgent_7d: 0, budget: 1 },
      { label: "Marc", persona: "default", pushes: 1, urgent: 0, held: 0, max_non_urgent_7d: 1, budget: 2 },
    ],
    rules: ["Max 2 non-urgent nudges per rolling 7 days (1 for retirees)"],
  }),
};
