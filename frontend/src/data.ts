// Every screen reads and writes through `data` and `profileData`: the backend API, or, with ?mock=1 (or
// `npm run dev:mock`), the self-contained demo engine in demo/ (bundled fixtures + browser storage, no backend).
import { api } from "./api";
import type {
  CardType, Component, CorrectionKind, DeclaredSignal, Decision, FactValue, KateTurn, LayoutPrefState,
  ProfileFactKey, Purpose, StylePrefs, TileGridPrefs,
} from "./api";
import { localData } from "./demo/data";
import { localProfile } from "./demo/profile";

export const MOCK = typeof window !== "undefined" &&
  (new URLSearchParams(window.location.search).get("mock") === "1" || import.meta.env.MODE === "mock");

const apiData: typeof localData = {
  login: (username: string, password: string) => api.login(username, password),
  session: () => api.session(),
  logout: () => api.logout(),
  home: (asOf?: string) => api.home(asOf),
  timeline: () => api.timeline(),
  feedback: (card_key: string, card_type: CardType, decision: Decision, asOf?: string) =>
    api.feedback(card_key, card_type, decision, asOf),
  layoutPref: (component: Component, state: LayoutPrefState, asOf?: string) => api.layoutPref(component, state, asOf),
  pinAt: (component: Component, position: number | null, asOf?: string) => api.pinAt(component, position, asOf),
  layoutReset: (asOf?: string) => api.layoutReset(asOf),
  saveTileGrid: (grid: TileGridPrefs) => api.saveTileGrid(grid),
  style: (style: StylePrefs, asOf?: string) => api.style(style, asOf),
  suggestion: (component: Component, decision: "accept" | "dismiss", asOf?: string) =>
    api.suggestion(component, decision, asOf),
  consent: (consent: boolean, asOf?: string) => api.consent(consent, asOf),
  declare: (signal: DeclaredSignal, state: "set" | "clear", asOf?: string) => api.declare(signal, state, asOf),
  kate: (message: string, card_key: string | null, history: KateTurn[], asOf?: string) =>
    api.kate(message, card_key, history, asOf),
};

const apiProfile: typeof localProfile = {
  get: (asOf?: string) => api.profile(asOf),
  setFact: (key: ProfileFactKey, value: FactValue, via: "you" | "kate", asOf?: string) => api.setFact(key, value, via, asOf),
  deleteFact: (key: ProfileFactKey, asOf?: string) => api.deleteFact(key, asOf),
  forgetKate: (asOf?: string) => api.forgetKate(asOf),
  correction: (kind: CorrectionKind, target: string, state: "set" | "clear", asOf?: string) =>
    api.correction(kind, target, state, asOf),
  permission: (purpose: Purpose, allowed: boolean, asOf?: string) => api.permission(purpose, allowed, asOf),
};

export const data = MOCK ? localData : apiData;
export const profileData = MOCK ? localProfile : apiProfile;
