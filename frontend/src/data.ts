// Thin layer over the API that switches to the mock fixture when the URL has ?mock=1.
import { api } from "./api";
import type {
  CardType, Component, DeclaredSignal, Decision, HomeResponse, KateAction, KateReply, KateTurn, LayoutPrefState,
  LoginResponse, Section, Size, StylePrefs, TimelineResponse,
} from "./api";
import mockHome from "../mock/home_sara.json";

export const MOCK = typeof window !== "undefined" && new URLSearchParams(window.location.search).get("mock") === "1";

const fixture = mockHome as unknown as HomeResponse;
let mockState: HomeResponse = structuredClone(fixture);
let mockHiddenExtra = 0;
const mockHidden = new Set<Component>();

const mockTimeline: TimelineResponse = {
  min_date: "2018-09-01",
  max_date: "2026-09-30",
  milestones: [
    { date: "2018-09-15", label: "Student" },
    { date: "2021-07-01", label: "First salary" },
    { date: "2022-04-01", label: "Mortgage" },
    { date: "2024-02-10", label: "Baby" },
    { date: "2026-01-05", label: "Went freelance" },
  ],
};

// Sizes + sample props for tiles the fixture doesn't show, so the gallery can add any of them.
const MOCK_EXTRA: Partial<Record<Component, { size: Size; props: Record<string, unknown> }>> = {
  SubscriptionsTile: {
    size: "half",
    props: {
      monthly_total_eur: 71.94, count: 6,
      items: [
        { counterparty: "Netflix", amount_eur: 15.99, period_days: 30, previous_amount_eur: 13.99 },
        { counterparty: "Spotify", amount_eur: 11.99, period_days: 30, previous_amount_eur: null },
        { counterparty: "Adobe", amount_eur: 24.19, period_days: 30, previous_amount_eur: null },
      ],
    },
  },
  BalanceHero: {
    size: "hero",
    props: { balance_eur: 4210, monthly_income_eur: 5120, monthly_spend_eur: 4380, trend_30d_eur: 340, sparkline: [3870, 3920, 3900, 4010, 3980, 4100, 4050, 4150, 4210] },
  },
  RunwayHero: { size: "hero", props: { balance_eur: 4210, runway_days: 26, next_income_date: "2026-10-12", next_income_eur: 2400, daily_budget_eur: 350.83 } },
  FamilyBudgetHero: {
    size: "hero",
    props: {
      month_label: "September", month_income_eur: 5120, month_spent_eur: 3610, month_budget_eur: 4000, child_benefit_eur: 184.5, childcare_eur: 420,
      top_categories: [{ category: "groceries", eur: 780 }, { category: "childcare", eur: 420 }, { category: "mortgage", eur: 1150 }, { category: "leisure", eur: 210 }],
    },
  },
  PensionHero: { size: "hero", props: { balance_eur: 4210, pension_eur: 0, pension_received_date: null, next_pension_date: null, upcoming_bills_eur: 612, upcoming_bills_count: 3 } },
  SpendingByCategory: {
    size: "half",
    props: { month_label: "September", total_eur: 3610, categories: [{ category: "mortgage", eur: 1150 }, { category: "groceries", eur: 780 }, { category: "childcare", eur: 420 }, { category: "leisure", eur: 210 }] },
  },
  SplitBills: { size: "half", props: { recent: [{ counterparty: "Pizzeria Da Mario", amount_eur: 64.5, date: "2026-09-27" }], hint: "Shared a dinner? Ask for your share back." } },
  AdvisorContact: { size: "half", props: { advisor_name: "Els Peeters", reason: "Questions about VAT or your business account?", slots: ["Tue 14:00", "Thu 10:30"] } },
  ScamShield: { size: "half", props: { tips: ["KBC never asks for your PIN.", "Don't scan QR codes from unknown texts.", "In doubt? Hang up and call us."], hotline: "Card Stop 078 170 170" } },
};

function styleToTheme(h: HomeResponse): void {
  const base = fixture.layout.theme;
  const s = h.style;
  h.layout.theme = {
    density: s.density ?? base.density,
    tone: s.tone ?? base.tone,
    contrast: s.contrast ?? base.contrast,
    appearance: s.appearance ?? "light",
    accent: s.accent,
    reduce_motion: s.reduce_motion,
    privacy: s.privacy,
    overrides: (Object.keys(s) as (keyof StylePrefs)[]).filter((k) => s[k] !== null && s[k] !== false),
  };
}

function withAsOf(asOf?: string): HomeResponse {
  const copy = structuredClone(mockState);
  if (asOf) copy.as_of = asOf;
  copy.feed.hidden_count = fixture.feed.hidden_count + mockHiddenExtra;
  const shown = new Set(copy.layout.sections.map((s) => s.component));
  copy.gallery = copy.gallery.map((g) => ({ ...g, state: shown.has(g.component) ? "shown" : mockHidden.has(g.component) ? "hidden" : "available" }));
  styleToTheme(copy);
  return copy;
}

function findProps(component: Component): { size: Size; props: Record<string, unknown> } | null {
  const fromFixture = fixture.layout.sections.find((s) => s.component === component);
  if (fromFixture) return { size: fromFixture.size, props: fromFixture.props };
  return MOCK_EXTRA[component] ?? null;
}

function mockPinAt(component: Component, position: number | null): void {
  const sections = mockState.layout.sections;
  const existing = sections.find((s) => s.component === component);
  const src = existing ?? (() => { const f = findProps(component); return f ? { component, ...f, pinned: false } : null; })();
  if (!src) return;
  mockHidden.delete(component);
  const tile: Section = { ...src, pinned: true };
  const isHero = mockState.gallery.find((g) => g.component === component)?.is_hero ?? tile.size === "hero";
  const rest = sections.filter((s) => s.component !== component);
  if (isHero) {
    tile.size = "hero";
    mockState.layout.sections = [tile, ...rest.filter((s) => s.size !== "hero")];
  } else {
    const feed = rest.findIndex((s) => s.component === "ForYouFeed");
    const head = rest.slice(0, feed + 1);
    const tail = rest.slice(feed + 1);
    const at = position === null ? tail.length : Math.max(0, Math.min(position, tail.length));
    tail.splice(at, 0, tile);
    mockState.layout.sections = [...head, ...tail];
  }
  mockState.layout.explanations[component] = "Pinned by you.";
  mockState.suggestions = mockState.suggestions.filter((s) => s.component !== component);
}

const QUICK = ["Make the text bigger", "Switch to dark mode", "What can you do?"];

function action(kind: KateAction["kind"], label: string, extra: Partial<KateAction> = {}): KateAction {
  return { kind, label, component: null, card_key: null, card_type: null, style: null, signal: null, ...extra };
}

function mockKate(message: string, cardKey: string | null, history: KateTurn[]): KateReply {
  const card = cardKey ? mockState.feed.cards.find((c) => c.card_key === cardKey) : undefined;
  const m = message.toLowerCase();
  const style = mockState.style;
  if (!message && card) {
    return {
      reply: `About "${card.title}": ${card.body} Want me to snooze it for a week, or show it to you?`,
      actions: [action("snooze_card", "Snooze 7 days", { card_key: card.card_key, card_type: card.card_type }), action("open_card", "Show me the card", { card_key: card.card_key })],
      quick_replies: ["Why am I seeing this?", "What can you do?"],
      source: "rules",
    };
  }
  if (!message) {
    return {
      reply: `Hi ${mockState.customer.first_name}, I'm Kate. Your VAT return is due in 20 days. Want your subscriptions on your home too? Netflix just went up.`,
      actions: [action("add_tile", "Add Subscriptions", { component: "SubscriptionsTile" })],
      quick_replies: QUICK,
      source: "rules",
    };
  }
  if (m.includes("dark")) {
    return { reply: "Sure, dark mode is easier on the eyes in the evening.", actions: [action("set_style", "Switch to dark", { style: { ...style, appearance: "dark" } })], quick_replies: ["Make the text bigger"], source: "rules" };
  }
  if (m.includes("big") || m.includes("larger") || m.includes("text")) {
    return { reply: "I can make the text and tiles larger for you.", actions: [action("set_style", "Use large text", { style: { ...style, density: "large" } })], quick_replies: ["Switch to dark mode"], source: "rules" };
  }
  if (m.includes("baby") || m.includes("pregnan")) {
    return { reply: "Congratulations! Shall I adapt your home for a growing family?", actions: [action("declare", "Yes, I'm expecting", { signal: "expecting_baby" })], quick_replies: [], source: "rules" };
  }
  if (m.includes("hide") || m.includes("savings")) {
    return { reply: "I can hide your savings goal from the home screen. You can always bring it back.", actions: [action("hide_tile", "Hide Savings goal", { component: "SavingsGoal" })], quick_replies: [], source: "rules" };
  }
  if (m.includes("reset") || m.includes("auto")) {
    return { reply: "I can put all your style settings back to Auto.", actions: [action("reset_style", "Reset to Auto")], quick_replies: [], source: "rules" };
  }
  if (card) {
    return { reply: `On "${card.title}": ${card.evidence[0] ?? card.rank_explanation}. You decide what happens next.`, actions: [action("dismiss_card", "Dismiss it", { card_key: card.card_key, card_type: card.card_type })], quick_replies: QUICK, source: "rules" };
  }
  return {
    reply: `I can pin or hide tiles, snooze cards, change how the app looks, or explain a card. (${history.length} earlier messages in this chat.)`,
    actions: [action("pin_tile", "Pin Invoices", { component: "InvoiceTracker" })],
    quick_replies: QUICK,
    source: "rules",
  };
}

export const data = {
  login(username: string, password: string): Promise<LoginResponse> {
    if (MOCK) return Promise.resolve({ role: "customer", username });
    return api.login(username, password);
  },
  session(): Promise<LoginResponse> {
    if (MOCK) return Promise.resolve({ role: "customer", username: "sara" });
    return api.session();
  },
  logout(): Promise<{ ok: boolean }> {
    if (MOCK) return Promise.resolve({ ok: true });
    return api.logout();
  },
  home(asOf?: string): Promise<HomeResponse> {
    if (MOCK) return Promise.resolve(withAsOf(asOf));
    return api.home(asOf);
  },
  timeline(): Promise<TimelineResponse> {
    if (MOCK) return Promise.resolve(mockTimeline);
    return api.timeline();
  },
  feedback(card_key: string, card_type: CardType, decision: Decision, asOf?: string): Promise<HomeResponse> {
    if (MOCK) {
      if (decision === "reset") {
        mockState = structuredClone(fixture);
        mockHidden.clear();
        mockHiddenExtra = 0;
      } else {
        const before = mockState.feed.cards.length;
        mockState.feed.cards = mockState.feed.cards.filter((c) => c.card_key !== card_key);
        mockHiddenExtra += before - mockState.feed.cards.length;
      }
      return Promise.resolve(withAsOf(asOf));
    }
    return api.feedback(card_key, card_type, decision, asOf);
  },
  layoutPref(component: Component, state: LayoutPrefState, asOf?: string): Promise<HomeResponse> {
    if (MOCK) {
      if (state === "hidden") {
        mockState.layout.sections = mockState.layout.sections.filter((s) => s.component !== component);
        mockState.layout.explanations[component] = "Hidden by you.";
        mockHidden.add(component);
      } else if (state === "pinned") {
        mockPinAt(component, null);
      } else {
        mockState.layout.sections = mockState.layout.sections.map((s) => (s.component === component ? { ...s, pinned: false } : s));
        mockState.layout.explanations[component] = fixture.layout.explanations[component] ?? "Adapts to you again.";
      }
      return Promise.resolve(withAsOf(asOf));
    }
    return api.layoutPref(component, state, asOf);
  },
  consent(consent: boolean, asOf?: string): Promise<HomeResponse> {
    if (MOCK) {
      mockState.customer.consent_personalization = consent;
      if (!consent) mockState.feed.cards = mockState.feed.cards.filter((c) => !c.commercial);
      else mockState.feed.cards = structuredClone(fixture.feed.cards);
      return Promise.resolve(withAsOf(asOf));
    }
    return api.consent(consent, asOf);
  },
  pinAt(component: Component, position: number | null, asOf?: string): Promise<HomeResponse> {
    if (MOCK) { mockPinAt(component, position); return Promise.resolve(withAsOf(asOf)); }
    return api.pinAt(component, position, asOf);
  },
  layoutReset(asOf?: string): Promise<HomeResponse> {
    if (MOCK) {
      mockState.layout.sections = structuredClone(fixture.layout.sections);
      mockState.layout.explanations = structuredClone(fixture.layout.explanations);
      mockHidden.clear();
      return Promise.resolve(withAsOf(asOf));
    }
    return api.layoutReset(asOf);
  },
  style(style: StylePrefs, asOf?: string): Promise<HomeResponse> {
    if (MOCK) { mockState.style = { ...style }; return Promise.resolve(withAsOf(asOf)); }
    return api.style(style, asOf);
  },
  suggestion(component: Component, decision: "accept" | "dismiss", asOf?: string): Promise<HomeResponse> {
    if (MOCK) {
      if (decision === "accept") mockPinAt(component, null);
      mockState.suggestions = mockState.suggestions.filter((s) => s.component !== component);
      return Promise.resolve(withAsOf(asOf));
    }
    return api.suggestion(component, decision, asOf);
  },
  declare(signal: DeclaredSignal, state: "set" | "clear", asOf?: string): Promise<HomeResponse> {
    if (MOCK) {
      mockState.declared = mockState.declared.filter((d) => d.signal !== signal);
      if (state === "set") mockState.declared.push({ signal, created_at: mockState.as_of });
      return Promise.resolve(withAsOf(asOf));
    }
    return api.declare(signal, state, asOf);
  },
  kate(message: string, card_key: string | null, history: KateTurn[], asOf?: string): Promise<KateReply> {
    if (MOCK) return new Promise((res) => window.setTimeout(() => res(mockKate(message, card_key, history)), 450));
    return api.kate(message, card_key, history, asOf);
  },
};
