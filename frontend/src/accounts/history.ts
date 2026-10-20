// Bookings and balance curve for one account.
// The backend may send real `transactions` on an account. Until then we derive demo bookings that are consistent
// with what the home screen already shows (invoices, pension, child benefit) and that always end on the real balance.
import type { HomeResponse, Persona } from "../api";
import { arr, num, str } from "../components/types";
import { addDays, shortDate } from "../format";
import { hash, type Account, type Txn } from "./accounts";

export interface Point { date: string; balance_eur: number }

export interface History {
  /** newest first */
  txns: Txn[];
  /** end-of-day balance, oldest first, last point = today's balance */
  balances: Point[];
  in_30d: number;
  out_30d: number;
}

export interface DayGroup { date: string; label: string; items: Txn[] }

const WINDOW_DAYS = 75;
export const CHART_DAYS = 60;
const FLOOR_EUR = 60;

export const TXN_META: Record<string, { icon: string; label: string }> = {
  salary: { icon: "💼", label: "Salary" },
  invoice_income: { icon: "🧾", label: "Invoice" },
  pension: { icon: "🏛️", label: "Pension" },
  student_income: { icon: "🎓", label: "Student job" },
  allowance_from_parents: { icon: "🎁", label: "Allowance" },
  child_benefit: { icon: "👶", label: "Child benefit" },
  rent: { icon: "🏠", label: "Rent" },
  mortgage: { icon: "🏠", label: "Home loan" },
  utilities: { icon: "💡", label: "Utilities" },
  telecom: { icon: "📱", label: "Telecom" },
  subscription: { icon: "🎬", label: "Subscription" },
  insurance: { icon: "🛡️", label: "Insurance" },
  groceries: { icon: "🛒", label: "Groceries" },
  leisure: { icon: "🍽️", label: "Leisure" },
  transport: { icon: "🚆", label: "Transport" },
  childcare: { icon: "🧸", label: "Childcare" },
  healthcare: { icon: "💊", label: "Healthcare" },
  vat_payment: { icon: "🏦", label: "VAT" },
  social_contribution: { icon: "🏦", label: "Social contribution" },
  business: { icon: "🧰", label: "Business costs" },
  savings_transfer: { icon: "🐷", label: "Savings" },
  interest: { icon: "✨", label: "Interest" },
};

export function txnMeta(category: string): { icon: string; label: string } {
  return TXN_META[category] ?? { icon: "💶", label: category.replace(/_/g, " ") };
}

// --- helpers ---------------------------------------------------------------------------------------------

function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const toIso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

const cents = (v: number) => Math.round(v * 100) / 100;

/** The given day of each of the last months that falls inside the window, optionally only in some months (0 = Jan). */
function monthlyOn(asOf: string, day: number, months?: number[]): string[] {
  const end = new Date(asOf + "T00:00:00");
  const from = addDays(asOf, -WINDOW_DAYS);
  const out: string[] = [];
  for (let i = 0; i < 4; i++) {
    const first = new Date(end.getFullYear(), end.getMonth() - i, 1);
    if (months && !months.includes(first.getMonth())) continue;
    const last = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
    first.setDate(Math.min(day, last));
    const s = toIso(first);
    if (s <= asOf && s > from) out.push(s);
  }
  return out;
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
const round10 = (v: number) => Math.round(v / 10) * 10;

interface Fixed { who: string; cat: string; amount: number; day: number; jitter?: number; months?: number[] }
interface Often { who: string[]; cat: string; every: number; lo: number; hi: number }

const GROCERS = ["Colruyt", "Delhaize", "Albert Heijn", "Lidl", "Aldi"];

// --- templates ---------------------------------------------------------------------------------------------

function everyday(): Often[] {
  return [
    { who: GROCERS, cat: "groceries", every: 3, lo: 14, hi: 92 },
    { who: ["NMBS", "De Lijn", "Shell"], cat: "transport", every: 6, lo: 5, hi: 24 },
    { who: ["Brasserie Jules", "Kinepolis", "Pizzeria Napoli", "Café Central"], cat: "leisure", every: 7, lo: 14, hi: 68 },
  ];
}

function personalTemplates(personas: Persona[], heroProps: Record<string, unknown>) {
  const has = (p: Persona) => personas.includes(p);
  const fixed: Fixed[] = [];
  const often: Often[] = everyday();

  if (has("student")) {
    fixed.push(
      { who: "Student job", cat: "student_income", amount: 460, day: 12, jitter: 0.12 },
      { who: "Parents", cat: "allowance_from_parents", amount: 300, day: 1 },
      { who: "Kot rent", cat: "rent", amount: -430, day: 1 },
      { who: "Spotify", cat: "subscription", amount: -11.99, day: 20 },
    );
  }
  if (has("young_professional")) {
    fixed.push(
      { who: "Salary", cat: "salary", amount: 2480, day: 26 },
      { who: "Rent", cat: "rent", amount: -790, day: 1 },
      { who: "Engie", cat: "utilities", amount: -88, day: 8, jitter: 0.1 },
      { who: "Proximus", cat: "telecom", amount: -52.99, day: 15 },
      { who: "Netflix", cat: "subscription", amount: -17.99, day: 5 },
      { who: "AG Insurance", cat: "insurance", amount: -47.5, day: 21 },
    );
  }
  if (has("young_family")) {
    const benefit = num(heroProps.child_benefit_eur) > 0 ? num(heroProps.child_benefit_eur) : 178;
    fixed.push(
      { who: "Salary", cat: "salary", amount: 2350, day: 26 },
      { who: "Groeipakket", cat: "child_benefit", amount: benefit, day: 3 },
      { who: "Kinderopvang De Wolkjes", cat: "childcare", amount: -340, day: 10 },
      { who: "Home loan", cat: "mortgage", amount: -1040, day: 2 },
      { who: "Fluvius", cat: "utilities", amount: -121, day: 8, jitter: 0.1 },
      { who: "Proximus", cat: "telecom", amount: -64.99, day: 15 },
      { who: "Netflix", cat: "subscription", amount: -17.99, day: 5 },
      { who: "AG Insurance", cat: "insurance", amount: -58, day: 21 },
    );
  }
  if (has("freelancer")) {
    fixed.push(
      { who: "Home loan", cat: "mortgage", amount: -980, day: 2 },
      { who: "Engie", cat: "utilities", amount: -96, day: 8, jitter: 0.1 },
      { who: "Proximus", cat: "telecom", amount: -59.99, day: 15 },
    );
  }
  if (has("retiree")) {
    const pension = num(heroProps.pension_eur) > 0 ? num(heroProps.pension_eur) : 1850;
    fixed.push(
      { who: "Federale Pensioendienst", cat: "pension", amount: pension, day: 3 },
      { who: "Engie", cat: "utilities", amount: -134, day: 8, jitter: 0.1 },
      { who: "Proximus", cat: "telecom", amount: -39.99, day: 15 },
      { who: "AG Insurance", cat: "insurance", amount: -61, day: 21 },
    );
    often.push({ who: ["Apotheek Peeters", "Apotheek De Linde"], cat: "healthcare", every: 14, lo: 6, hi: 38 });
  }
  if (fixed.length === 0) {
    fixed.push({ who: "Salary", cat: "salary", amount: 2300, day: 26 }, { who: "Rent", cat: "rent", amount: -760, day: 1 });
  }
  return { fixed, often };
}

function businessTemplates(reserve: number) {
  const fixed: Fixed[] = [
    { who: "Adobe Creative Cloud", cat: "subscription", amount: -59.99, day: 9 },
    { who: "Boekhouding Claes", cat: "business", amount: -145, day: 28 },
    { who: "Proximus Business", cat: "telecom", amount: -79, day: 15 },
    { who: "Sociaal verzekeringsfonds", cat: "social_contribution", amount: -1062, day: 2, months: [0, 3, 6, 9] },
    { who: "FOD Financiën · VAT", cat: "vat_payment", amount: -(reserve > 0 ? reserve : 1840), day: 20, months: [0, 3, 6, 9] },
  ];
  const often: Often[] = [
    { who: ["Office supplies", "Coworking Gent", "Print & Copy"], cat: "business", every: 11, lo: 12, hi: 120 },
    { who: ["NMBS", "Shell", "Parking Gent"], cat: "transport", every: 9, lo: 9, hi: 75 },
  ];
  return { fixed, often };
}

// --- builder ---------------------------------------------------------------------------------------------

function invoiceIncome(home: HomeResponse, asOf: string, r: () => number): Txn[] {
  const section = home.layout.sections.find((s) => s.component === "InvoiceTracker");
  const clients = arr<{ name?: unknown; eur?: unknown; last_date?: unknown }>(section?.props.clients);
  const from = addDays(asOf, -WINDOW_DAYS);
  const out: Txn[] = [];
  // Real clients and dates first: each client's last invoice on the day the invoice tracker says.
  for (const c of clients) {
    const date = str(c.last_date);
    if (date > from && date <= asOf) {
      out.push({ id: "", date, counterparty: str(c.name, "Client"), category: "invoice_income", amount_eur: round10(800 + r() * 1800) });
    }
  }
  // Earlier invoices to fill the history.
  const names = clients.map((c) => str(c.name)).filter(Boolean);
  const pool = names.length > 0 ? names : ["Studio Noord", "Brasserie De Kat", "Atelier Vos"];
  for (let off = 6 + Math.floor(r() * 6); off < WINDOW_DAYS; off += 14 + Math.floor(r() * 12)) {
    out.push({
      id: "",
      date: addDays(asOf, -off),
      counterparty: pool[Math.floor(r() * pool.length)],
      category: "invoice_income",
      amount_eur: round10(800 + r() * 1800),
    });
  }
  return out;
}

function derive(account: Account, home: HomeResponse, heroProps: Record<string, unknown>): Txn[] {
  const asOf = home.as_of;
  const balance = account.balance_eur;
  const r = rng(hash(`${home.customer.first_name}|${account.id}|${asOf.slice(0, 7)}`));
  const personas = [...home.persona_mix].sort((a, b) => b.weight - a.weight).slice(0, 2).map((p) => p.persona);
  const out: Txn[] = [];
  const push = (date: string, who: string, cat: string, amount: number) =>
    out.push({ id: "", date, counterparty: who, category: cat, amount_eur: cents(amount) });

  const addFixed = (list: Fixed[]) => {
    for (const f of list) {
      for (const date of monthlyOn(asOf, f.day, f.months)) {
        const wobble = f.jitter ? 1 + (r() - 0.5) * 2 * f.jitter : 1;
        push(date, f.who, f.cat, f.amount * wobble);
      }
    }
  };
  const addOften = (list: Often[]) => {
    for (const o of list) {
      for (let off = Math.floor(r() * o.every); off < WINDOW_DAYS; off += Math.max(1, Math.round(o.every * (0.6 + r() * 0.8)))) {
        push(addDays(asOf, -off), o.who[Math.floor(r() * o.who.length)], o.cat, -(o.lo + r() * (o.hi - o.lo)));
      }
    }
  };

  switch (account.kind) {
    case "savings": {
      const dep = clamp(round10(balance * 0.05), 20, 350);
      for (const d of monthlyOn(asOf, 27)) push(d, "Transfer from current account", "savings_transfer", dep);
      for (const d of monthlyOn(asOf, 1)) push(d, "Interest", "interest", balance * 0.0011);
      return out;
    }
    case "child": {
      const dep = clamp(round10(balance * 0.03), 20, 120);
      for (const d of monthlyOn(asOf, 5)) push(d, "Monthly deposit", "savings_transfer", dep);
      for (const d of monthlyOn(asOf, 1)) push(d, "Interest", "interest", balance * 0.0011);
      return out;
    }
    case "reserve": {
      const dep = clamp(round10(balance * 0.22), 100, 600);
      for (const d of monthlyOn(asOf, 26)) push(d, "Transfer to tax reserve", "savings_transfer", dep);
      return out;
    }
    case "business": {
      out.push(...invoiceIncome(home, asOf, r));
      const t = businessTemplates(num(heroProps.reserve_eur));
      addFixed(t.fixed);
      addOften(t.often);
      break;
    }
    default: {
      const personal = personas.includes("freelancer") && account.kind === "current"
        ? invoiceIncome(home, asOf, r)
        : [];
      out.push(...personal);
      const t = personalTemplates(personas, heroProps);
      addFixed(t.fixed);
      addOften(t.often);
    }
  }
  return out;
}

function withBalances(account: Account, asOf: string, list: Txn[]): { txns: Txn[]; balances: Point[] } {
  const balance = account.balance_eur;
  const sorted = [...list].sort((a, b) => (a.date === b.date ? a.counterparty.localeCompare(b.counterparty) : a.date < b.date ? 1 : -1));
  const curve = (txns: Txn[]): Point[] => {
    const points: Point[] = [];
    for (let i = CHART_DAYS; i >= 0; i--) {
      const date = addDays(asOf, -i);
      let after = 0;
      for (const t of txns) if (t.date > date) after += t.amount_eur;
      points.push({ date, balance_eur: cents(balance - after) });
    }
    return points;
  };

  let txns = sorted;
  const spending = account.kind !== "savings" && account.kind !== "child" && account.kind !== "reserve";

  // More money in than the balance can explain: people move the surplus away every month, so do the same
  // here instead of showing a history in which the account was overdrawn.
  if (spending && account.transactions === undefined) {
    const base = txns;
    const net = base.reduce((t, x) => t + x.amount_eur, 0);
    const dates = [...monthlyOn(asOf, 14), ...monthlyOn(asOf, 28)];
    if (net > balance * 0.5 && dates.length > 0) {
      const who = account.kind === "business" ? "Transfer to personal account" : "Transfer to savings account";
      let each = Math.ceil((net - balance * 0.25) / dates.length / 10) * 10;
      for (let i = 0; i < 6; i++) {
        txns = [...base, ...dates.map((date) => ({ id: "", date, counterparty: who, category: "savings_transfer", amount_eur: -each }))];
        txns.sort((a, b) => (a.date === b.date ? a.counterparty.localeCompare(b.counterparty) : a.date < b.date ? 1 : -1));
        const low = Math.min(...curve(txns).map((p) => p.balance_eur));
        if (low >= FLOOR_EUR) break;
        each += Math.ceil((FLOOR_EUR - low) / dates.length / 10) * 10;
      }
    }
  }

  let balances = curve(txns);
  // Last resort: never show the balance below zero.
  const min = Math.min(...balances.map((p) => p.balance_eur));
  if (min < FLOOR_EUR && spending && account.transactions === undefined) {
    const x = Math.ceil((FLOOR_EUR - min) / 10) * 10;
    txns = [{ id: "", date: asOf, counterparty: "Transfer to savings account", category: "savings_transfer", amount_eur: -x }, ...txns];
    balances = curve(txns);
  }
  return { txns: txns.map((t, i) => ({ ...t, id: `${account.id}-${i}` })), balances };
}

export function buildHistory(account: Account, home: HomeResponse, heroProps: Record<string, unknown>): History {
  const asOf = home.as_of;
  const raw = account.transactions && account.transactions.length > 0 ? account.transactions : derive(account, home, heroProps);
  const { txns, balances } = withBalances(account, asOf, raw.filter((t) => t.date <= asOf));
  const since = addDays(asOf, -30);
  let inSum = 0;
  let outSum = 0;
  for (const t of txns) {
    if (t.date <= since) continue;
    if (t.amount_eur > 0) inSum += t.amount_eur;
    else outSum += -t.amount_eur;
  }
  return { txns, balances, in_30d: cents(inSum), out_30d: cents(outSum) };
}

// --- grouping for display ---------------------------------------------------------------------------------------

const WEEKDAY = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export function dayLabel(date: string, asOf: string): string {
  if (date === asOf) return "Today";
  if (date === addDays(asOf, -1)) return "Yesterday";
  return `${WEEKDAY[new Date(date + "T00:00:00").getDay()]} ${shortDate(date)}`;
}

export function groupByDay(txns: Txn[], asOf: string): DayGroup[] {
  const groups: DayGroup[] = [];
  for (const t of txns) {
    const last = groups[groups.length - 1];
    if (last && last.date === t.date) last.items.push(t);
    else groups.push({ date: t.date, label: dayLabel(t.date, asOf), items: [t] });
  }
  return groups;
}
