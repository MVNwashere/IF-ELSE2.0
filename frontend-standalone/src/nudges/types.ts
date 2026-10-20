// UI types for local Kate nudges.
import type { KateAction } from "../api";

export type NudgeTier = "urgent" | "deadline" | "waiting" | "moment";
export type NudgeChannel = "push" | "digest" | "inbox";
export type NudgeStatus = "new" | "opened" | "dismissed" | "muted";
export type NudgeAck = "opened" | "dismissed" | "mute";

export interface Nudge {
  nudge_key: string;
  topic: string;
  tier: NudgeTier;
  title: string;
  why: string;
  evidence: string[];
  action: KateAction;
  open_view: "passport" | null;
  delivered_at: string;          // local time, ISO without zone
  channel: NudgeChannel;
  digest_id: string | null;
  held_reason: string | null;
  mutable: boolean;
  status: NudgeStatus;
  source: string;
}

export interface NudgeBudget { limit: number; used: number; window_days: number; quiet_hours: string; persona: string }

export interface NudgesResponse {
  as_of: string;
  since: string;
  nudges: Nudge[];
  budget: NudgeBudget;
  candidates: number;
  held: number;
}

export interface AckResponse { nudge_key: string; status: NudgeStatus; muted_until: string | null }

export interface TierStats { tier: NudgeTier; candidates: number; pushed: number; held: number }
export interface CustomerNudgeStats {
  label: string; persona: string; pushes: number; urgent: number; held: number; max_non_urgent_7d: number; budget: number;
}
export interface NudgeStats {
  since: string;
  as_of: string;
  customers: number;
  weeks: number;
  pushes_per_customer_week: number;
  non_urgent_per_customer_week: number;
  max_non_urgent_any_7d: number;
  budget_default: number;
  budget_retiree: number;
  candidates: number;
  pushed_items: number;
  held_items: number;
  naive_pushes: number;
  pushes: number;
  noise_avoided_pct: number;
  open_rate: number | null;
  dismiss_rate: number | null;
  mute_rate: number | null;
  acks: number;
  by_tier: TierStats[];
  per_customer: CustomerNudgeStats[];
  rules: string[];
}

/** What the phone shows in the banner: one nudge, or a bundled morning digest. */
export type Banner = { kind: "single"; nudge: Nudge } | { kind: "digest"; id: string; nudges: Nudge[] };

export const TIER_LABEL: Record<NudgeTier, string> = {
  urgent: "Urgent", deadline: "Deadline", waiting: "Waiting on you", moment: "Moment",
};

/** ControlPanel → phone: replay the nudges of a window (demo). detail: { days?: number } */
export const NUDGE_REPLAY_EVENT = "nudges:replay";
export const NUDGE_RESET_EVENT = "nudges:reset";
