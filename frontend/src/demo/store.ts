// Self-contained fixtures and browser-local state. No runtime API requests.
import customersJson from '../demo-data/customers.json';
import { ApiError } from '../api';
import { JURY, renameForJury } from '../jury/mode';
import type { Component, DeclaredSignalRow, HomeResponse, LoginResponse, Section, StylePrefs, TileGridPrefs, TimelineResponse } from '../api';
import type { ConsentGrant, EventRow, Goal, GoalsResponse, SourceView, SourcesResponse } from '../ecosystem/types';
import type { NudgeAck, NudgesResponse } from '../nudges/types';

export const TODAY = '2026-10-20';
export const STORAGE_KEY = 'kbc-demo-v1';
export const DEFAULT_STYLE: StylePrefs = {
  density: null, contrast: null, tone: null, appearance: null, accent: null, reduce_motion: false, privacy: false,
};
export type CustomerName = 'lotte' | 'sara' | 'jan' | 'marc';
export const CUSTOMER_NAMES: CustomerName[] = ['lotte', 'sara', 'jan', 'marc'];
export interface Snapshot { date: string; home: HomeResponse; goals: GoalsResponse; nudges: NudgesResponse }
export interface CustomerFixture {
  timeline: TimelineResponse; snapshots: Snapshot[]; templates: Record<string, Goal>;
  results: Record<string, string>; sources: SourcesResponse;
  source_values: Record<string, Record<string, string | number>>; tiles: Record<Component, Section>;
}
export const fixtures = (JURY ? renameForJury(customersJson) : customersJson) as unknown as Record<CustomerName, CustomerFixture>;
export interface LocalCustomer {
  tileGrid?: TileGridPrefs;
  style: StylePrefs | null; consent: boolean | null;
  pins: Partial<Record<Component, { position: number | null }>>; hidden: Component[];
  feedback: Record<string, { type: string; decision: string; until: string | null }>;
  declared: DeclaredSignalRow[]; dismissedSuggestions: Component[];
  goals: Goal[]; grants: ConsentGrant[]; sources: SourceView[] | null;
  pending: Record<string, { due: number; ref: string }>;
  nudgeAcks: Record<string, { action: NudgeAck; mutedUntil: string | null }>;
  events: EventRow[]; asOf: string;
}
interface SavedState { version: 1; session: LoginResponse | null; customers: Record<CustomerName, LocalCustomer>; nextId: number }
const blank = (): LocalCustomer => ({
  style: null, consent: null, pins: {}, hidden: [], feedback: {}, declared: [], dismissedSuggestions: [],
  goals: [], grants: [], sources: null, pending: {}, nudgeAcks: {}, events: [], asOf: TODAY,
});
const fresh = (): SavedState => ({ version: 1, session: null, customers: { lotte: blank(), sara: blank(), jan: blank(), marc: blank() }, nextId: 1 });
function load(): SavedState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const value = JSON.parse(raw) as SavedState;
      if (value.version === 1 && CUSTOMER_NAMES.every((name) => value.customers?.[name]?.pending)) return value;
    }
  } catch { /* Disabled storage or invalid save: use a fresh in-memory demo. */ }
  return fresh();
}
export const saved = load();
const listeners = new Set<() => void>();
/** Runs after every save, so a view of the demo state (the jury guide) can follow along. */
export function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => { listeners.delete(fn); };
}
export function persist(): void {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(saved)); } catch { /* Still usable without storage. */ }
  listeners.forEach((fn) => fn());
}
export function copy<T>(value: T): T { return structuredClone(value); }
export async function reply<T>(value: T): Promise<T> { return copy(value); }
export function currentName(): CustomerName {
  if (!saved.session) throw new ApiError(401, 'Choose a demo customer to continue');
  if (saved.session.role !== 'customer') throw new ApiError(403, 'Open a customer preview first');
  return saved.session.username as CustomerName;
}
export function current(): LocalCustomer { return saved.customers[currentName()]; }
export function customerFixture(): CustomerFixture { return fixtures[currentName()]; }
export function snapshot(asOf?: string): Snapshot {
  const f = customerFixture();
  const date = asOf ?? TODAY;
  const clamped = date < f.timeline.min_date ? f.timeline.min_date : date > TODAY ? TODAY : date;
  current().asOf = clamped;
  return [...f.snapshots].reverse().find((s) => s.date <= clamped) ?? f.snapshots[0];
}
export function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}
export function event(state: LocalCustomer, provider: string, kind: string, summary: string): void {
  state.events.unshift({ at: new Date().toISOString(), partner_id: provider, kind, summary, verified: false });
  state.events.splice(60);
}
