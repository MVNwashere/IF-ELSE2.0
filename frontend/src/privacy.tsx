// "Hide amounts": a context read by every component that formats money. eur() stays pure;
// components call useEur() instead so masking works everywhere with one line per file.
//
// One source of truth: Phone provides `masked` (privacy setting on and not temporarily revealed) through
// PrivacyContext. Components never keep their own copy. Free text from the backend (card copy, Kate, nudges,
// gallery, goals) goes through maskText()/<MaskedText>; charts, bars and rings use the neutral helpers below so
// their shape can't leak proportions either.
import { createContext, useContext } from "react";
import { eur } from "./format";

export const MASK = "€ ••••";
export const MASK_PCT = "••%";

export const PrivacyContext = createContext(false);

/** true while amounts are masked (privacy on and not temporarily revealed). */
export function useMasked(): boolean {
  return useContext(PrivacyContext);
}

/** Drop-in replacement for eur() that respects the privacy mask. */
export function useEur(): typeof eur {
  const masked = useContext(PrivacyContext);
  return masked ? () => MASK : eur;
}

// A number as format.ts (and the backend copy) writes it: "1.840", "13,99", "1.234,56", "1,234.56", "1 234".
const NUM = String.raw`\d+(?:[.,  ]\d{3})*(?:[.,]\d+)?`;
const NUM_SPACED = String.raw`\d+(?:[.,   ]\d{3})*(?:[.,]\d+)?`;
const MAGNITUDE = String.raw`(?:\s?(?:k|K|m|M|mln|mio|bn|million|thousand|billion)\b)?`;
const SIGN = String.raw`(?:[−+\-]\s?)?`;
const CUR = String.raw`(?:€|EUR\b|eur\b|euros?\b|Euros?\b)`;

// €1.840 · € 1.234,56 · −€13,99 · €12k · EUR 500 · 1,234 EUR · 1.234 € · 500 euro · 2.5M EUR
const AMOUNT = new RegExp(
  String.raw`(?<![\w.,])${SIGN}(?:${CUR}\s?${NUM}${MAGNITUDE}|${NUM_SPACED}${MAGNITUDE}\s?${CUR})`,
  "g",
);

const MONEY_WORDS = String.raw`income|salary|wage|balance|budget|spend|spent|spending|saving|savings|saved|invoiced|invoices?|revenue|interest|rent|mortgage|pension|wealth|portfolio|returns?|yield|reserve|net worth|equity|loan|debt|bills?`;
const PERCENT = String.raw`${SIGN}\d+(?:[.,]\d+)?\s?%`;
// A percentage tied to money: followed (same sentence, shortly after) by a masked amount or a money word,
// or preceded shortly by a money word. "about 25% of € ••••", "your savings grew 4%", "12% of your income".
const PCT_BEFORE_MONEY = new RegExp(
  String.raw`(?<![\w.,])${PERCENT}(?=[^.!?\n]{0,40}?(?:€ ••••|\b(?:${MONEY_WORDS})\b))`,
  "gi",
);
const PCT_AFTER_MONEY = new RegExp(
  String.raw`(\b(?:${MONEY_WORDS})\b[^.!?\n]{0,30}?)(?<![\w.,])${PERCENT}`,
  "gi",
);

/** Mask euro amounts (and money-related percentages) inside free text. Backend copy has amounts inlined. */
export function maskText(text: string, masked: boolean): string;
export function maskText(text: string | null | undefined, masked: boolean): string | null | undefined;
export function maskText(text: string | null | undefined, masked: boolean): string | null | undefined {
  if (!masked || !text) return text;
  return text
    .replace(AMOUNT, MASK)
    .replace(PCT_BEFORE_MONEY, MASK_PCT)
    .replace(PCT_AFTER_MONEY, (_, lead: string) => `${lead}${MASK_PCT}`);
}

/** maskText bound to the current privacy state. */
export function useMaskText(): (text: string) => string {
  const masked = useContext(PrivacyContext);
  return (text: string) => maskText(text, masked);
}

/** Free text that may contain amounts. Renders a plain text node (never HTML). */
export function MaskedText({ text }: { text: string | null | undefined }) {
  const masked = useContext(PrivacyContext);
  return <>{maskText(text ?? "", masked)}</>;
}

/** A 0..1 progress fraction for bars/rings: a neutral half-full placeholder while masked. */
export function maskFrac(frac: number, masked: boolean): number {
  return masked ? 0.5 : frac;
}

/** Values for a sparkline/chart: a flat line while masked, so the trend can't be read. */
export function maskSeries(values: number[], masked: boolean): number[] {
  return masked ? values.map(() => 0) : values;
}
