// density / tone / contrast / appearance / accent → CSS variables applied on the phone root.
import type { CSSProperties } from "react";
import type { Accent, Theme, Tone } from "./api";

const DENSITY = {
  compact: { font: "15px", space: "10px", radius: "14px", heroPad: "16px" },
  comfortable: { font: "16px", space: "12px", radius: "16px", heroPad: "20px" },
  large: { font: "19px", space: "16px", radius: "18px", heroPad: "24px" },
} as const;

const TONE_ACCENT: Record<Tone, string> = {
  casual: "#7c3aed",
  neutral: "#0d6fb8",
  warm: "#d97706",
  business: "#0f766e",
  formal: "#1e3a8a",
};

/** Customer-chosen accent → [primary, primary-2] (hero gradient, buttons, avatar). */
export const ACCENTS: Record<Accent, [string, string]> = {
  blue: ["#0d6fb8", "#00a3e0"],
  teal: ["#0f766e", "#14b8a6"],
  purple: ["#6d28d9", "#a855f7"],
  amber: ["#b45309", "#f59e0b"],
  navy: ["#1e3a8a", "#3b5bdb"],
};

type Palette = Record<"--bg" | "--card" | "--text" | "--muted" | "--border" | "--border-w" | "--shadow" | "--chip" | "--hover", string>;

const PALETTES: Record<"light" | "dark", Record<"normal" | "high", Palette>> = {
  light: {
    normal: {
      "--bg": "#eef3f8", "--card": "#ffffff", "--text": "#0f172a", "--muted": "#64748b", "--border": "#e2e8f0", "--border-w": "1px",
      "--shadow": "0 1px 2px rgba(15,23,42,.05), 0 6px 18px rgba(15,23,42,.06)", "--chip": "#f1f5f9", "--hover": "#f1f5f9",
    },
    high: {
      "--bg": "#ffffff", "--card": "#ffffff", "--text": "#000000", "--muted": "#222222", "--border": "#000000", "--border-w": "2px",
      "--shadow": "none", "--chip": "#eeeeee", "--hover": "#e5e5e5",
    },
  },
  dark: {
    normal: {
      "--bg": "#0b1220", "--card": "#151f32", "--text": "#e6edf7", "--muted": "#94a3b8", "--border": "#26344d", "--border-w": "1px",
      "--shadow": "0 1px 2px rgba(0,0,0,.4), 0 6px 18px rgba(0,0,0,.35)", "--chip": "#1f2b42", "--hover": "#223049",
    },
    high: {
      "--bg": "#000000", "--card": "#0a0a0a", "--text": "#ffffff", "--muted": "#e5e5e5", "--border": "#ffffff", "--border-w": "2px",
      "--shadow": "none", "--chip": "#1a1a1a", "--hover": "#262626",
    },
  },
};

export function themeVars(theme: Theme): CSSProperties {
  const d = DENSITY[theme.density];
  const high = theme.contrast === "high";
  const dark = theme.appearance === "dark";
  const [p1, p2] = theme.accent
    ? ACCENTS[theme.accent]
    : high ? ["#003d73", "#00539c"] : ["#0d6fb8", "#00a3e0"];
  const vars: Record<string, string> = {
    "--font-size": d.font,
    "--space": d.space,
    "--radius": d.radius,
    "--hero-pad": d.heroPad,
    "--accent": theme.accent ? ACCENTS[theme.accent][0] : TONE_ACCENT[theme.tone],
    ...PALETTES[dark ? "dark" : "light"][high ? "high" : "normal"],
    "--primary": p1,
    "--primary-2": p2,
    colorScheme: dark ? "dark" : "light",
  };
  return vars as CSSProperties;
}

export function greeting(tone: Tone, firstName: string): string {
  switch (tone) {
    case "casual": return `Hey ${firstName} 👋`;
    case "neutral": return `Hello ${firstName}`;
    case "warm": return `Hi ${firstName}`;
    case "business": return `Good morning, ${firstName}`;
    case "formal": return `Good morning, ${firstName}.`;
  }
}
