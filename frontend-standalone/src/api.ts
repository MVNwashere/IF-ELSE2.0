// Shared UI types for the standalone frontend.


export type Persona ="student" | "young_professional" | "young_family" | "freelancer" | "investor" | "retiree";
export type Family = "deadline" | "anomaly" | "forecast" | "opportunity" | "milestone" | "protection";
export type Stage = "early" | "soon" | "urgent" | "info";
export type CardType = string; // backend validates against the legacy, core and catalogue registries
export type Decision = "dismiss" | "snooze" | "less" | "accept" | "reset";
export type LayoutPrefState = "pinned" | "hidden" | "reset";
export type Component =
  | "BalanceHero" | "RunwayHero" | "FamilyBudgetHero" | "TaxReserveHero" | "PensionHero"
  | "ForYouFeed" | "QuickActions" | "UpcomingBills" | "SplitBills" | "InvoiceTracker"
  | "SavingsGoal" | "ScamShield" | "AdvisorContact" | "SpendingByCategory"
  | "KateTile" | "SubscriptionsTile";
export type Density = "compact" | "comfortable" | "large";
export type Tone = "casual" | "neutral" | "warm" | "business" | "formal";
export type Contrast = "normal" | "high";
export type Size = "hero" | "full" | "half";
export type Appearance = "light" | "dark";
export type Accent = "blue" | "teal" | "purple" | "amber" | "navy";
export type DeclaredSignal = "expecting_baby" | "going_freelance" | "retiring" | "studying";

export interface PersonaWeight { persona: Persona; weight: number; evidence: string[] }
export interface FeedPersona { code: "TEEN" | "STU" | "YPRO" | "PAR" | "HOME" | "SELF" | "INV" | "PRE" | "SEN"; weight: number; evidence: string[] }
export interface Cta { label: string; action: string }
export interface Card {
  card_key: string;
  card_type: CardType;
  family: Family;
  stage: Stage;
  title: string;
  body: string;
  eur_impact: number;
  due_date: string | null;
  confidence: number;
  commercial: boolean;
  evidence: string[];
  rank_explanation: string;
  score: number;
  cta: Cta | null;
  details: Record<string, unknown>;
}
export interface Theme {
  density: Density;
  tone: Tone;
  contrast: Contrast;
  appearance: Appearance;
  accent: Accent | null;          // null = the tone's accent
  reduce_motion: boolean;
  privacy: boolean;
  overrides: string[];            // theme keys the customer set themselves
}
/** The customer's own settings. null = "Auto" (the engine decides). */
export interface StylePrefs {
  density: Density | null;
  contrast: Contrast | null;
  tone: Tone | null;
  appearance: Appearance | null;
  accent: Accent | null;
  reduce_motion: boolean;
  privacy: boolean;
}
export interface Section { component: Component; size: Size; props: Record<string, unknown>; pinned: boolean }
export interface TileSuggestion { component: Component; title: string; reason: string; as_hero: boolean }
export interface GalleryItem {
  component: Component;
  label: string;
  description: string;
  reason: string;
  score: number;
  suggested: boolean;
  state: "shown" | "available" | "hidden";
  is_hero: boolean;
}
export interface DeclaredSignalRow { signal: DeclaredSignal; created_at: string }
export interface Layout { version: number; theme: Theme; sections: Section[]; explanations: Record<string, string> }
export interface Feed { cards: Card[]; caught_up: boolean; hidden_count: number }
export interface CustomerPublic { first_name: string; language: "nl" | "fr"; consent_personalization: boolean }
export interface HomeResponse {
  as_of: string;
  customer: CustomerPublic;
  persona_mix: PersonaWeight[];
  feed_personas: FeedPersona[];
  layout: Layout;
  feed: Feed;
  generated_at: string;
  llm_copy: boolean;
  style: StylePrefs;
  suggestions: TileSuggestion[];
  gallery: GalleryItem[];
  declared: DeclaredSignalRow[];
}

// ---- Kate ----
export type KateActionKind =
  | "pin_tile" | "hide_tile" | "add_tile" | "snooze_card" | "dismiss_card"
  | "set_style" | "declare" | "open_card" | "reset_style"
  | "start_goal" | "open_goal";
/** A proposal only: the app shows a button; on tap it calls the regular endpoint. */
export interface KateAction {
  kind: KateActionKind;
  label: string;
  component: Component | null;
  card_key: string | null;
  card_type: CardType | null;
  style: StylePrefs | null;       // set_style: the complete new local StylePrefs
  signal: DeclaredSignal | null;
  playbook_id?: string | null;    // start_goal
  goal_id?: number | null;        // open_goal
}
export interface KateTurn { role: "user" | "kate"; text: string }
export interface KateReply { reply: string; actions: KateAction[]; quick_replies: string[]; source: "rules" | "llm" }
export interface Milestone { date: string; label: string }
export interface TimelineResponse { min_date: string; max_date: string; milestones: Milestone[] }
export interface LoginResponse { role: "customer" | "advisor"; username: string }
export interface AdvisorOverview {
  customers_scored: number;
  scoring_ms: number;
  projected_2_3m_seconds: number;
  persona_distribution: Record<string, number>;
  card_volume: Record<string, number>;
  eur_impact_total: number;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

