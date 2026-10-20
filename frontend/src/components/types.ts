import type { Card, Decision, HomeResponse } from "../api";

export interface SectionCtx {
  home: HomeResponse;
  asOf: string;
  explain: boolean;
  onFeedback: (card: Card, decision: Decision) => void;
  onCta: (action: string) => void;
  /** Open the Kate sheet, optionally about one card and/or with a first user message. */
  openKate: (cardKey?: string | null, message?: string) => void;
}

export interface SectionProps {
  props: Record<string, unknown>;
  ctx: SectionCtx;
}

export type SectionComponent = (p: SectionProps) => React.JSX.Element;

/** Cast the untyped props record to the component's declared shape. */
export function as<T>(props: Record<string, unknown>): T {
  return props as unknown as T;
}

export function num(v: unknown, fallback = 0): number {
  return typeof v === "number" && Number.isFinite(v) ? v : fallback;
}

export function str(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}

export function arr<T>(v: unknown): T[] {
  return Array.isArray(v) ? (v as T[]) : [];
}
