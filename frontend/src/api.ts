// Typed client. Mirrors backend/app/schemas.py — keep both in sync.

import type { ConsentsResponse, EcosystemOverview, Goal, GoalsResponse, StepDecision } from "./ecosystem/types";

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
export type ProfileFactKey =
  | "partner" | "children" | "cares_for_relative" | "employment" | "housing" | "risk_appetite"
  | "contact_channel" | "avoid_topics";
export type FactValue = string | number | boolean | string[];
export type Purpose = "personalise_offers" | "detect_life_events" | "kate_memory" | "kate_ai" | "advisor_view";
export type CorrectionKind = "persona" | "goal";

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
  size?: Size;                    // when shown; older fixtures leave it out
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
  tile_grid?: TileGridPrefs | null;   // the For you wall as arranged by the customer; null: never arranged
}
/** The For you wall (feed/tileGrid.ts). Tile ids are "card:<card_key>" or "widget:<Component>". */
export interface TileGridPrefs {
  placements: Record<string, { slot: number; span: 1 | 2 }>;
  hidden: string[];
  slotCount: number;
}

// ---- Kate ----
export type KateActionKind =
  | "pin_tile" | "hide_tile" | "add_tile" | "snooze_card" | "dismiss_card"
  | "set_style" | "declare" | "open_card" | "reset_style"
  | "start_goal" | "open_goal"
  | "update_profile" | "forget_fact" | "forget_kate_facts" | "correct_inference" | "set_permission"
  | "open_profile" | "open_passport" | "revoke_consent";
/** A proposal only: the app shows a button; on tap it calls the regular endpoint. */
export interface KateAction {
  kind: KateActionKind;
  label: string;
  component: Component | null;
  card_key: string | null;
  card_type: CardType | null;
  style: StylePrefs | null;       // set_style: the full new StylePrefs to POST to /api/me/style
  signal: DeclaredSignal | null;
  playbook_id?: string | null;    // start_goal
  goal_id?: number | null;        // open_goal
  fact_key?: ProfileFactKey | null;       // update_profile / forget_fact
  fact_value?: FactValue | null;          // update_profile
  correction_kind?: CorrectionKind | null; // correct_inference
  target?: string | null;
  purpose?: Purpose | null;               // set_permission
  allowed?: boolean | null;
  grant_id?: number | null;               // revoke_consent
}
export interface KateTurn { role: "user" | "kate"; text: string }
export interface KateReply { reply: string; actions: KateAction[]; quick_replies: string[]; source: "rules" | "llm" }
// ---- Profile: what KBC knows and may use ----
export interface FieldOption { value: string; label: string }
export interface ProfileField {
  key: ProfileFactKey;
  label: string;
  category: "household" | "work" | "home" | "money" | "contact";
  kind: "enum" | "int" | "bool" | "set";
  hint: string;
  options: FieldOption[];
  min: number | null;
  max: number | null;
  used_for: string[];
  value: FactValue | null;
  value_label: string | null;
  source: "you" | "kate" | null;
  updated_on: string | null;
}
export interface InferredPersona { persona: Persona; label: string; weight_pct: number; evidence: string[]; from_you: boolean }
export interface InferredGoal { playbook_id: string; title: string; evidence: string[] }
export interface CorrectionView { kind: CorrectionKind; target: string; label: string; created_on: string }
export interface PermissionView { purpose: Purpose; label: string; description: string; when_off: string; allowed: boolean }
export interface ProfileResponse {
  as_of: string;
  first_name: string;
  fields: ProfileField[];
  declared: { signal: DeclaredSignal; label: string; created_on: string }[];
  personas: InferredPersona[];
  goals: InferredGoal[];
  corrections: CorrectionView[];
  permissions: PermissionView[];
  data_access: { partners_with_access: number; fields_shared: number; sources_connected: number };
}

export interface Milestone { date: string; label: string }
export interface TimelineResponse { min_date: string; max_date: string; milestones: Milestone[]; today?: string | null }
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

// Every request belongs to the session that sent it. Logging out or switching customer aborts whatever is still in
// flight, so a late response for the previous customer can never render for the next one.
let sessionAbort = new AbortController();

export function abortSessionRequests(): void {
  sessionAbort.abort();
  sessionAbort = new AbortController();
}

export function isAbort(e: unknown): boolean {
  return e instanceof DOMException && e.name === "AbortError";
}

export async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
    signal: sessionAbort.signal,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* ignore */ }
    throw new ApiError(res.status, String(detail));
  }
  return res.json() as Promise<T>;
}

function withAsOf(path: string, asOf?: string): string {
  return asOf ? `${path}?as_of=${asOf}` : path;
}

export const api = {
  login: (username: string, password: string) => call<LoginResponse>("POST", "/api/login", { username, password }),
  logout: () => call<{ ok: boolean }>("POST", "/api/logout"),
  session: () => call<LoginResponse>("GET", "/api/me/session"),
  home: (asOf?: string) => call<HomeResponse>("GET", asOf ? `/api/me/home?as_of=${asOf}` : "/api/me/home"),
  timeline: () => call<TimelineResponse>("GET", "/api/me/timeline"),
  feedback: (card_key: string, card_type: CardType, decision: Decision, asOf?: string) =>
    call<HomeResponse>("POST", asOf ? `/api/me/feedback?as_of=${asOf}` : "/api/me/feedback", { card_key, card_type, decision }),
  layoutPref: (component: Component, state: LayoutPrefState, asOf?: string) =>
    call<HomeResponse>("POST", asOf ? `/api/me/layout-prefs?as_of=${asOf}` : "/api/me/layout-prefs", { component, state }),
  consent: (consent_personalization: boolean, asOf?: string) =>
    call<HomeResponse>("POST", asOf ? `/api/me/consent?as_of=${asOf}` : "/api/me/consent", { consent_personalization }),
  pinAt: (component: Component, position: number | null, asOf?: string) =>
    call<HomeResponse>("POST", withAsOf("/api/me/layout-prefs", asOf), { component, state: "pinned", position }),
  layoutReset: (asOf?: string) => call<HomeResponse>("POST", withAsOf("/api/me/layout-reset", asOf)),
  style: (style: StylePrefs, asOf?: string) => call<HomeResponse>("POST", withAsOf("/api/me/style", asOf), style),
  suggestion: (component: Component, decision: "accept" | "dismiss", asOf?: string) =>
    call<HomeResponse>("POST", withAsOf("/api/me/suggestion", asOf), { component, decision }),
  declare: (signal: DeclaredSignal, state: "set" | "clear", asOf?: string) =>
    call<HomeResponse>("POST", withAsOf("/api/me/declare", asOf), { signal, state }),
  kate: (message: string, card_key: string | null, history: KateTurn[], asOf?: string) =>
    call<KateReply>("POST", withAsOf("/api/me/kate", asOf), { message, card_key, history }),
  advisorOverview: () => call<AdvisorOverview>("GET", "/api/advisor/overview"),
  // ---- profile ----
  profile: (asOf?: string) => call<ProfileResponse>("GET", withAsOf("/api/me/profile", asOf)),
  setFact: (key: ProfileFactKey, value: FactValue, via: "you" | "kate", asOf?: string) =>
    call<ProfileResponse>("PUT", withAsOf(`/api/me/profile/facts/${encodeURIComponent(key)}`, asOf), { value, via }),
  deleteFact: (key: ProfileFactKey, asOf?: string) =>
    call<ProfileResponse>("DELETE", withAsOf(`/api/me/profile/facts/${encodeURIComponent(key)}`, asOf)),
  forgetKate: (asOf?: string) => call<ProfileResponse>("POST", withAsOf("/api/me/profile/forget-kate", asOf)),
  correction: (kind: CorrectionKind, target: string, state: "set" | "clear", asOf?: string) =>
    call<ProfileResponse>("POST", withAsOf("/api/me/profile/corrections", asOf), { kind, target, state }),
  permission: (purpose: Purpose, allowed: boolean, asOf?: string) =>
    call<ProfileResponse>("PUT", withAsOf(`/api/me/profile/permissions/${encodeURIComponent(purpose)}`, asOf), { allowed }),
  advisorProfile: (username: string) => call<ProfileResponse>("GET", `/api/advisor/profile/${encodeURIComponent(username)}`),
  // ---- ecosystem engine (types in ecosystem/types.ts) ----
  goals: (asOf?: string) => call<GoalsResponse>("GET", withAsOf("/api/me/goals", asOf)),
  startGoal: (playbook_id: string, asOf?: string) => call<Goal>("POST", withAsOf("/api/me/goals", asOf), { playbook_id }),
  stepDecision: (goalId: number, stepId: string, decision: StepDecision, asOf?: string) =>
    call<Goal>("POST", withAsOf(`/api/me/goals/${encodeURIComponent(goalId)}/steps/${encodeURIComponent(stepId)}`, asOf), { decision }),
  cancelGoal: (goalId: number) => call<{ ok: boolean }>("POST", `/api/me/goals/${encodeURIComponent(goalId)}/cancel`),
  consents: () => call<ConsentsResponse>("GET", "/api/me/consents"),
  revokeConsent: (grantId: number) => call<ConsentsResponse>("POST", `/api/me/consents/${encodeURIComponent(grantId)}/revoke`),
  goalsReset: () => call<{ ok: boolean }>("POST", "/api/me/goals-reset"),
  ecosystemOverview: () => call<EcosystemOverview>("GET", "/api/ecosystem/overview"),
  previewGoal: (playbook_id: string, asOf?: string) =>
    call<Goal>("GET", withAsOf(`/api/me/goals/preview/${encodeURIComponent(playbook_id)}`, asOf)),
  saveTileGrid: (grid: TileGridPrefs) => call<{ ok: boolean }>("PUT", "/api/me/tile-grid", grid),
};
