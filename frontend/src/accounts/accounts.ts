// The accounts behind the hero tile.
// The backend may send them as `accounts` inside the hero section's props (see docs/COMPONENT-PROPS.md).
// Until it does, we derive a few clearly labelled demo accounts from data the home screen already has.
import type { HomeResponse, Persona, Section } from "../api";
import { arr, num, str } from "../components/types";

export type AccountKind = "current" | "savings" | "reserve" | "child" | "business" | "joint";

/** One booking on an account. Positive = money in, negative = money out. */
export interface Txn {
  id: string;
  date: string;
  counterparty: string;
  category: string;
  amount_eur: number;
}

export interface Account {
  id: string;
  kind: AccountKind;
  name: string;
  last4: string;
  balance_eur: number;
  /** Real bookings from the backend, newest first or in any order. When missing, history.ts derives demo bookings. */
  transactions?: Txn[];
}

export interface AccountsView {
  /** accounts[0] is the one the customer uses most: the account the hero tile summarises. */
  accounts: Account[];
  total_eur: number;
  /** true when the accounts were derived for the demo instead of sent by the backend. */
  illustrative: boolean;
}

const KINDS: AccountKind[] = ["current", "savings", "reserve", "child", "business", "joint"];
const MAX_ACCOUNTS = 4;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function txnsFromProps(raw: unknown[], accountId: string): Txn[] {
  const out: Txn[] = [];
  raw.forEach((item, i) => {
    if (!item || typeof item !== "object") return;
    const o = item as Record<string, unknown>;
    const date = str(o.date);
    if (!ISO_DATE.test(date) || typeof o.amount_eur !== "number" || !Number.isFinite(o.amount_eur)) return;
    out.push({
      id: `${accountId}-t${i}`,
      date,
      counterparty: str(o.counterparty, "Unknown"),
      category: str(o.category, "other"),
      amount_eur: o.amount_eur,
    });
  });
  return out;
}

function fromProps(raw: unknown[]): Account[] {
  const out: Account[] = [];
  raw.forEach((item, i) => {
    if (!item || typeof item !== "object") return;
    const o = item as Record<string, unknown>;
    const name = str(o.name);
    if (!name || typeof o.balance_eur !== "number" || !Number.isFinite(o.balance_eur)) return;
    const last4 = str(o.last4);
    const id = str(o.id, `account_${i}`);
    const transactions = txnsFromProps(arr<unknown>(o.transactions), id);
    out.push({
      id,
      kind: KINDS.includes(o.kind as AccountKind) ? (o.kind as AccountKind) : "current",
      name,
      last4: /^\d{4}$/.test(last4) ? last4 : "0000",
      balance_eur: o.balance_eur,
      ...(transactions.length > 0 ? { transactions } : {}),
    });
  });
  return out.slice(0, MAX_ACCOUNTS);
}

// Deterministic pseudo-random numbers, so the demo accounts don't jump around on every render.
export function hash(s: string): number {
  let x = 2166136261;
  for (let i = 0; i < s.length; i++) {
    x ^= s.charCodeAt(i);
    x = Math.imul(x, 16777619);
  }
  return x >>> 0;
}

function between(seed: string, lo: number, hi: number, step = 10): number {
  return lo + (hash(seed) % (Math.floor((hi - lo) / step) + 1)) * step;
}

interface Template { id: string; kind: AccountKind; name: string; lo: number; hi: number }

const EXTRA: Record<Persona, Template[]> = {
  student: [
    { id: "savings", kind: "savings", name: "Savings account", lo: 150, hi: 1800 },
  ],
  young_professional: [
    { id: "savings", kind: "savings", name: "Savings account", lo: 1500, hi: 12000 },
    { id: "holiday", kind: "savings", name: "Holiday fund", lo: 200, hi: 2500 },
  ],
  young_family: [
    { id: "child_savings", kind: "child", name: "Child savings", lo: 300, hi: 4000 },
    { id: "savings", kind: "savings", name: "Savings account", lo: 1500, hi: 9000 },
  ],
  freelancer: [
    { id: "tax_reserve", kind: "reserve", name: "Tax reserve", lo: 600, hi: 3200 },
    { id: "savings", kind: "savings", name: "Savings account", lo: 1500, hi: 9000 },
  ],
  retiree: [
    { id: "savings", kind: "savings", name: "Savings account", lo: 6000, hi: 28000 },
    { id: "term", kind: "savings", name: "Term account", lo: 5000, hi: 20000 },
  ],
};

const PRIMARY: Record<string, { kind: AccountKind; name: string }> = {
  FamilyBudgetHero: { kind: "joint", name: "Family account" },
  TaxReserveHero: { kind: "business", name: "Business account" },
};

function primaryBalance(hero: Section, seed: string): number {
  const p = hero.props;
  if (typeof p.balance_eur === "number" && Number.isFinite(p.balance_eur)) return p.balance_eur;
  // A freelancer's business account holds a share of what was invoiced this quarter.
  const invoiced = Math.round((num(p.quarter_income_eur) * 0.25) / 10) * 10;
  return Math.max(between(`${seed}|primary`, 900, 4500), invoiced);
}

/** The accounts behind the current hero tile, or null when the home screen has no hero. */
export function accountsFor(home: HomeResponse, hero: Section | undefined): AccountsView | null {
  if (!hero) return null;

  const given = fromProps(arr<unknown>(hero.props.accounts));
  if (given.length > 0) {
    return { accounts: given, total_eur: given.reduce((t, a) => t + a.balance_eur, 0), illustrative: false };
  }

  const seed = `${home.customer.first_name}|${home.as_of.slice(0, 7)}`;
  const top = [...home.persona_mix].sort((a, b) => b.weight - a.weight).slice(0, 2).map((p) => p.persona);
  const personas: Persona[] = top.length > 0 ? top : ["young_professional"];

  const main = PRIMARY[hero.component] ?? { kind: "current" as const, name: "Current account" };
  const accounts: Account[] = [{
    id: "main",
    kind: main.kind,
    name: main.name,
    last4: String(1000 + (hash(`${seed}|main`) % 9000)),
    balance_eur: primaryBalance(hero, seed),
  }];

  for (const persona of personas) {
    for (const t of EXTRA[persona]) {
      if (accounts.length >= MAX_ACCOUNTS || accounts.some((a) => a.id === t.id)) continue;
      // The tax-reserve account must agree with the number on the tax-reserve tile.
      const reserve = hero.component === "TaxReserveHero" && t.id === "tax_reserve" ? num(hero.props.reserve_eur, -1) : -1;
      accounts.push({
        id: t.id,
        kind: t.kind,
        name: t.name,
        last4: String(1000 + (hash(`${seed}|${t.id}`) % 9000)),
        balance_eur: reserve >= 0 ? reserve : between(`${seed}|${t.id}`, t.lo, t.hi),
      });
    }
  }

  return { accounts, total_eur: accounts.reduce((t, a) => t + a.balance_eur, 0), illustrative: true };
}
