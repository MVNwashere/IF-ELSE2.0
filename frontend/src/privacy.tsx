// "Hide amounts": a context read by every component that formats money. eur() stays pure;
// components call useEur() instead so masking works everywhere with one line per file.
import { createContext, useContext } from "react";
import { eur } from "./format";

export const MASK = "€ ••••";

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

/** Mask euro amounts inside free text (card titles/bodies come from the backend with amounts inlined). */
export function maskText(text: string, masked: boolean): string {
  return masked ? text.replace(/[−+-]?€\s?\d[\d.,]*/g, MASK) : text;
}
