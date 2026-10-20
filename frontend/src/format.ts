// Belgian-style money and date formatting. "€1.840" for whole euros, "€13,99" when cents matter.

export function eur(value: number, opts: { cents?: boolean; sign?: boolean } = {}): string {
  const cents = opts.cents ?? (!Number.isInteger(Math.round(value * 100) / 100) && Math.abs(value) < 1000);
  const abs = Math.abs(value);
  const fixed = cents ? abs.toFixed(2) : Math.round(abs).toString();
  const [intPart, decPart] = fixed.split(".");
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const body = decPart ? `${grouped},${decPart}` : grouped;
  const sign = value < 0 ? "−" : opts.sign && value > 0 ? "+" : "";
  return `${sign}€${body}`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

export function longDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

export function daysBetween(fromIso: string, toIso: string): number {
  const a = new Date(fromIso + "T00:00:00").getTime();
  const b = new Date(toIso + "T00:00:00").getTime();
  return Math.round((b - a) / 86_400_000);
}

export function addDays(iso: string, days: number): string {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + days);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${dd}`;
}

export function pct(weight: number): string {
  return `${Math.round(weight * 100)}%`;
}

export const PERSONA_LABEL: Record<string, string> = {
  student: "student",
  young_professional: "young professional",
  young_family: "young family",
  freelancer: "freelancer",
  retiree: "retiree",
};

export const FEED_PERSONA_LABEL: Record<string, string> = {
  TEEN: "youth", STU: "student", YPRO: "young professional", PAR: "parent",
  HOME: "household", SELF: "self-employed", INV: "investor",
  PRE: "pre-retirement", SEN: "retiree",
};

export const CATEGORY_LABEL: Record<string, string> = {
  salary: "Salary", invoice_income: "Invoices", pension: "Pension", student_income: "Student job",
  allowance_from_parents: "Allowance", child_benefit: "Child benefit", benefit: "Benefit",
  rent: "Rent", mortgage: "Mortgage", utilities: "Utilities", telecom: "Telecom", subscription: "Subscriptions",
  insurance_car: "Car insurance", insurance_home: "Home insurance", insurance_family: "Family insurance",
  groceries: "Groceries", leisure: "Leisure", transport: "Transport", childcare: "Childcare", baby: "Baby",
  school: "School", tuition: "Tuition", social_contribution: "Social contributions", vat_payment: "VAT",
  tax: "Tax", savings_transfer: "Savings", furniture: "Furniture", notary: "Notary", healthcare: "Healthcare",
  other: "Other",
};

export function categoryLabel(c: string): string {
  return CATEGORY_LABEL[c] ?? c.replace(/_/g, " ");
}

/** "SubscriptionsTile" → "Subscriptions tile"; prefers the backend's gallery label when known. */
export function componentLabel(component: string, gallery?: { component: string; label: string }[]): string {
  const g = gallery?.find((x) => x.component === component);
  if (g) return g.label;
  const words = component.replace(/([a-z])([A-Z])/g, "$1 $2").toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}
