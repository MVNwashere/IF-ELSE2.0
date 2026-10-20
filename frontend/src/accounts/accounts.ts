// The accounts behind the hero tile.
// The backend may send them as `accounts` inside the hero section's props (see docs/COMPONENT-PROPS.md).
// Until it does, we derive a few clearly labelled demo accounts from data the home screen already has.
import type { HomeResponse, Section } from "../api";
import { arr, str } from "../components/types";

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

/** The primary account's balance: the backend fills `balance_eur` on every hero tile from the same Customer State the
 * cards use, so the ball and the feed always agree. */
function primaryBalance(home: HomeResponse, hero: Section): number {
  if (typeof hero.props.balance_eur === "number") return hero.props.balance_eur;
  // older snapshots: the "Your money" card carries the same current-account figure
  const money = home.feed.cards.find((c) => c.card_type === "core_money")?.details.metrics;
  return Array.isArray(money) && typeof money[0]?.value === "number" ? money[0].value : 0;
}

/** The accounts behind the current hero tile, or null when the home screen has no hero. */
export function accountsFor(home: HomeResponse, hero: Section | undefined): AccountsView | null {
  if (!hero) return null;

  const given = fromProps(arr<unknown>(hero.props.accounts));
  if (given.length > 0) {
    return { accounts: given, total_eur: given.reduce((t, a) => t + a.balance_eur, 0), illustrative: false };
  }

  const seed = `${home.customer.first_name}|${home.as_of.slice(0, 7)}`;
  // Only accounts the bank actually sees: no made-up savings or reserve pots next to the real balance.
  const accounts: Account[] = [{
    id: "main",
    kind: "current",
    name: "Current account",
    last4: String(1000 + (hash(`${seed}|main`) % 9000)),
    balance_eur: primaryBalance(home, hero),
  }];

  return { accounts, total_eur: accounts.reduce((t, a) => t + a.balance_eur, 0), illustrative: true };
}
