// Mirrors backend/app/ecosystem/models.py: keep both in sync. Dates are ISO strings.

export type StepStatus = "proposed" | "approved" | "in_progress" | "done" | "declined" | "blocked";
export type GoalStatus = "active" | "completed" | "cancelled";
export type GrantStatus = "active" | "revoked" | "expired";
export type ProviderKind = "kbc" | "partner" | "advisor";
export type ValueShareModel = "lead_fee" | "revenue_share" | "fee_per_completed_step" | "subscription";
export type StepDecision = "approve" | "decline" | "reset";

export interface DataField { field: string; label: string; sensitive: boolean }
export interface ValueShare { model: ValueShareModel; amount_eur: number; pct: number; note: string }
export interface ProviderPublic { id: string; name: string; kind: ProviderKind; blurb: string; vetting: string[]; integration: string }
export interface Win { customer: string; kbc: string; partner: string }
export interface Estimates { customer_eur: number; hours_saved: number; kbc_revenue_eur: number; partner_fee_eur: number }
export interface ProductRef { id: string; name: string; ecosystem: string; partner: string | null }

export interface Step {
  step_id: string;
  order: number;
  title: string;
  description: string;
  provider: ProviderPublic;
  why_this_provider: string;
  products: ProductRef[];
  status: StepStatus;
  data_shared: DataField[];
  data_not_shared: string[];
  consent_days: number;
  win: Win;
  estimates: Estimates;
  result: string;
  ref: string;
  grant_id: number | null;
  updated_at: string | null;
  already_held: boolean;
  done_on?: string | null;
  fee?: FeeDisclosure | null;
  alternatives?: PartnerOption[];
  source_hint?: SourceHint | null;
  booking?: string;
}

export interface FeeDisclosure { model: ValueShareModel | null; amount_eur: number; pct: number; kbc_earns: string; you_pay_extra: string }
export interface PartnerOption {
  provider: ProviderPublic;
  rating: number | null;
  outcome_rate: number | null;
  rank: number;
  recommended: boolean;
  chosen: boolean;
  fee: FeeDisclosure;
  data_shared: DataField[];
}
export interface SourceHint { source_id: string; name: string; prompt: string; connected: boolean }
export type OutcomeStatus = "verified" | "pending" | "not_met";
export interface MeasuredOutcome {
  metric: string;
  label: string;
  status: OutcomeStatus;
  measured_eur: number | null;
  estimate_eur: number | null;
  unit: string;
  summary: string;
  evidence: string[];
  check_on: string | null;
  step_id: string | null;
}

export interface Progress { done: number; total: number }
export interface WinTotals {
  customer_eur: number;
  hours_saved: number;
  kbc_revenue_eur: number;
  partner_fees_eur: number;
  kbc_products: string[];
  partner_leads: number;
}

export interface Goal {
  goal_id: number;
  playbook_id: string;
  title: string;
  icon: string;
  tagline: string;
  ecosystems: string[];
  status: GoalStatus;
  created_on: string;
  target_date: string | null;
  origin: "detected" | "stated";
  evidence: string[];
  progress: Progress;
  steps: Step[];
  outcome: WinTotals;
  potential: WinTotals;
  next_goal: string | null;
  next_goal_title?: string | null;
  measured?: MeasuredOutcome[];
}

export interface GoalCandidate {
  playbook_id: string;
  title: string;
  icon: string;
  tagline: string;
  ecosystems: string[];
  confidence: number;
  evidence: string[];
  why_now: string;
  steps_preview: string[];
  partners_preview: string[];
  potential: WinTotals;
}

export interface PlaybookSummary { playbook_id: string; title: string; icon: string; tagline: string; ecosystems: string[]; steps: number }

export interface GoalsResponse {
  as_of: string;
  candidates: GoalCandidate[];
  goals: Goal[];
  holdings: ProductRef[];
  playbooks: PlaybookSummary[];
}

export interface ConsentGrant {
  grant_id: number;
  partner_id: string;
  partner_name: string;
  goal_id: number;
  goal_title: string;
  step_id: string;
  step_title: string;
  fields: DataField[];
  purpose: string;
  granted_on: string;
  expires_on: string;
  status: GrantStatus;
  revoked_on: string | null;
  deletion_confirmed_at?: string | null;
  deletion_confirmed_by?: string | null;
  kbc_earns?: string;
}

export type SourceStatus = "available" | "connected" | "expired" | "public";
export interface SourceView {
  source_id: string;
  name: string;
  provider: string;
  kind: "psd2" | "government" | "partner" | "public" | "utility";
  reads: string[];
  goals: string[];
  sensitivity: "low" | "medium" | "high";
  needs_consent: boolean;
  consent_days: number;
  why: string;
  status: SourceStatus;
  connected_on: string | null;
  expires_on: string | null;
  purpose: string;
  playbook_id: string | null;
  values: Record<string, string | number>;
  simulated: boolean;
}
export interface SourcesResponse { sources: SourceView[]; connected: number; note: string }

export interface ConsentsResponse { grants: ConsentGrant[]; partners_with_access: number; fields_shared: number; sources?: SourceView[] }

export interface FunnelRow { playbook_id: string; title: string; icon: string; detected: number; started: number; steps_done: number; completed: number; projected_2_3m: number }
export interface PartnerRow { partner_id: string; name: string; ecosystems: string[]; value_share: ValueShare; leads: number; completed: number; fees_eur: number; avg_response_s: number | null }
export interface EventRow { at: string; partner_id: string; kind: string; summary: string; verified: boolean }

export interface LearningRow {
  playbook_id: string; title: string; icon: string; detected: number; hit_rate: number; avg_confidence: number;
  shown: number; started: number; completed: number; start_rate: number | null; completion_rate: number | null;
}
export interface RuleRow { playbook_id: string; rule: string; hits: number; hit_rate: number }
export interface OutcomeSummary { verified: number; pending: number; not_met: number; verified_eur: number; estimated_eur_for_verified: number }

export interface EcosystemOverview {
  catalogue_items: number;
  ecosystems: number;
  building_blocks_used: number;
  partners: number;
  funnel: FunnelRow[];
  partner_rows: PartnerRow[];
  events: EventRow[];
  realised: WinTotals;
  projection: Record<string, number>;
  assumptions: string[];
  scoring_ms: number;
  learning?: LearningRow[];
  rules?: RuleRow[];
  outcomes?: OutcomeSummary;
}
