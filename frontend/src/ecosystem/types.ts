// Mirrors backend/app/ecosystem/models.py: keep both in sync. Dates are ISO strings.

export type StepStatus = "proposed" | "approved" | "in_progress" | "done" | "declined" | "blocked";
export type GoalStatus = "active" | "completed" | "cancelled";
export type GrantStatus = "active" | "revoked" | "expired";
export type ProviderKind = "kbc" | "partner";
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
}

export interface ConsentsResponse { grants: ConsentGrant[]; partners_with_access: number; fields_shared: number }

export interface FunnelRow { playbook_id: string; title: string; icon: string; detected: number; started: number; steps_done: number; completed: number; projected_2_3m: number }
export interface PartnerRow { partner_id: string; name: string; ecosystems: string[]; value_share: ValueShare; leads: number; completed: number; fees_eur: number; avg_response_s: number | null }
export interface EventRow { at: string; partner_id: string; kind: string; summary: string; verified: boolean }

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
}
