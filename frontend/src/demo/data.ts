// The demo engine behind ?mock=1: the same interface as data.ts, on bundled fixtures and browser storage.
// No backend, no HTTP requests. Logins are local persona picks (lotte, sara, jan, marc, advisor; password demo).
import { ApiError } from '../api';
import type { Component, DeclaredSignal, Decision, HomeResponse, KateAction, KateReply, KateTurn, LayoutPrefState, Section, StylePrefs, TileGridPrefs } from '../api';
import { copy, current, customerFixture, DEFAULT_STYLE, persist, reply, saved, snapshot, TODAY, addDays, CUSTOMER_NAMES } from './store';

const hero = (s: Section) => s.size === 'hero';

function home(asOf?: string): HomeResponse {
  const h = copy(snapshot(asOf).home);
  const local = current();
  const palette = customerFixture().tiles;
  h.as_of = local.asOf;
  h.customer.consent_personalization = local.consent ?? h.customer.consent_personalization;
  h.style = copy(local.style ?? DEFAULT_STYLE);
  h.declared = copy(local.declared.filter((d) => d.created_at <= h.as_of));
  h.tile_grid = local.tileGrid ? copy(local.tileGrid) : null;
  const signalPersona = { expecting_baby: 'young_family', going_freelance: 'freelancer', retiring: 'retiree', studying: 'student' } as const;
  const signalHero = { expecting_baby: 'FamilyBudgetHero', going_freelance: 'TaxReserveHero', retiring: 'PensionHero', studying: 'RunwayHero' } as const;
  for (const d of h.declared) {
    const persona = signalPersona[d.signal];
    h.persona_mix = h.persona_mix.filter((p) => p.persona !== persona).map((p) => ({ ...p, weight: p.weight * .4 }));
    h.persona_mix.unshift({ persona, weight: .6, evidence: [`You told Kate on ${d.created_at}`] });
    const sum = h.persona_mix.reduce((n, p) => n + p.weight, 0);
    h.persona_mix.forEach((p) => { p.weight /= sum; });
    const chosen = palette[signalHero[d.signal]];
    if (chosen) h.layout.sections = [copy(chosen), ...h.layout.sections.filter((s) => !hero(s))];
  }
  const sections = h.layout.sections.filter((s) => !local.hidden.includes(s.component));
  const pinned = Object.entries(local.pins) as [Component, { position: number | null }][];
  const pinnedHero = pinned.find(([component]) => palette[component]?.size === 'hero');
  if (pinnedHero) {
    const component = pinnedHero[0];
    const tile = sections.find((s) => s.component === component) ?? palette[component];
    sections.splice(0, sections.length, { ...copy(tile), pinned: true }, ...sections.filter((s) => !hero(s)));
  }
  for (const [component, pin] of pinned) {
    if (palette[component]?.size === 'hero') continue;
    const source = sections.find((s) => s.component === component) ?? palette[component];
    if (!source) continue;
    const tile = copy(source);
    const old = sections.findIndex((s) => s.component === component);
    if (old >= 0) sections.splice(old, 1);
    tile.pinned = true;
    const feedIndex = sections.findIndex((s) => s.component === 'ForYouFeed');
    const at = pin.position === null ? sections.length : Math.min(sections.length, feedIndex + 1 + pin.position);
    sections.splice(at, 0, tile);
    h.layout.explanations[component] = 'Pinned by you. Your choice stays in place.';
  }
  h.layout.sections = sections;
  const shown = new Set(sections.map((s) => s.component));
  h.gallery.forEach((g) => { g.state = shown.has(g.component) ? 'shown' : local.hidden.includes(g.component) ? 'hidden' : 'available'; });
  h.suggestions = h.suggestions.filter((s) => !local.dismissedSuggestions.includes(s.component) && !local.pins[s.component]);
  const before = h.feed.cards.length;
  h.feed.cards = h.feed.cards.filter((card) => {
    if (card.commercial && !h.customer.consent_personalization) return false;
    const feedback = local.feedback[card.card_key];
    if (feedback && (feedback.until === null || feedback.until > h.as_of)) return false;
    return !Object.values(local.feedback).some((f) => f.decision === 'less' && f.type === card.card_type);
  });
  h.feed.hidden_count += before - h.feed.cards.length;
  h.feed.caught_up = true;
  const theme = h.layout.theme;
  const style = h.style;
  theme.density = style.density ?? theme.density;
  theme.contrast = style.contrast ?? theme.contrast;
  theme.tone = style.tone ?? theme.tone;
  theme.appearance = style.appearance ?? theme.appearance;
  theme.accent = style.accent ?? theme.accent;
  theme.reduce_motion = style.reduce_motion;
  theme.privacy = style.privacy;
  theme.overrides = (Object.keys(style) as (keyof StylePrefs)[]).filter((key) => style[key] !== null && style[key] !== false);
  return h;
}
function pin(component: Component, position: number | null): void {
  const state = current();
  const palette = customerFixture().tiles;
  if (!palette[component]) throw new Error('Unknown tile');
  if (palette[component].size === 'hero') {
    for (const key of Object.keys(state.pins) as Component[]) if (palette[key].size === 'hero') delete state.pins[key];
  }
  delete state.pins[component];
  state.pins[component] = { position };
  state.hidden = state.hidden.filter((c) => c !== component);
}
function mutate(fn: () => void, asOf?: string): Promise<HomeResponse> {
  fn(); persist(); return reply(home(asOf));
}
const action = (kind: KateAction['kind'], label: string, extra: Partial<KateAction> = {}): KateAction => ({
  kind, label, component: null, card_key: null, card_type: null, style: null, signal: null, ...extra,
});
function kate(message: string, cardKey: string | null, _history: KateTurn[], asOf?: string): KateReply {
  const h = home(asOf);
  const m = message.toLowerCase();
  const card = h.feed.cards.find((c) => c.card_key === cardKey);
  const quick = ['Make the text bigger', 'Switch to dark mode', "I'm going freelance", 'What can you do?'];
  const result = (text: string, actions: KateAction[] = []): KateReply => ({ reply: text, actions, quick_replies: quick, source: 'rules' });
  if (m.includes('dark')) return result('I can switch your home to dark mode.', [action('set_style', 'Switch to dark', { style: { ...h.style, appearance: 'dark' } })]);
  if (/bigger|larger|big text/.test(m)) return result('I can make the text and tiles larger.', [action('set_style', 'Use large text', { style: { ...h.style, density: 'large' } })]);
  if (/reset|auto/.test(m)) return result('Put your appearance settings back to Auto?', [action('reset_style', 'Reset to Auto')]);
  if (/baby|expecting|pregnan/.test(m)) return result('Congratulations! Shall I adapt your home for your growing family?', [action('declare', "Yes, I'm expecting", { signal: 'expecting_baby' }), action('start_goal', 'Plan for a new baby', { playbook_id: 'new_baby' })]);
  if (/contribution|regularisation|coming up|deadline/.test(m)) return result(customerFixture().results['go_freelance/tax_reserve'] || 'Your goals show the upcoming steps, with illustrative amounts and dates.');
  const intents: [RegExp, string][] = [[/freelance|self.employ|business/, 'go_freelance'], [/owe|paid|invoice/, 'get_paid'], [/house|buy a home|property/, 'buy_home'], [/renovat|energy/, 'energy_upgrade'], [/retir|pension|invest/, 'retire_well'], [/travel|trip|holiday/, 'travel'], [/employee|hire/, 'first_employee'], [/safe|scam/, 'peace_of_mind']];
  const goalId = intents.find(([pattern]) => pattern.test(m))?.[1];
  if (goalId) {
    const existing = current().goals.find((g) => g.playbook_id === goalId && g.status !== 'cancelled');
    const template = customerFixture().templates[goalId];
    return result(`I can help with “${template.title}”. You review and approve each step.`, [existing ? action('open_goal', 'Open my journey', { goal_id: existing.goal_id, playbook_id: goalId }) : action('start_goal', 'Show me the plan', { playbook_id: goalId })]);
  }
  if (card) return result(`About “${card.title}”: ${card.evidence.join(' ')} ${card.body}`, [action('snooze_card', 'Snooze 7 days', { card_key: card.card_key, card_type: card.card_type })]);
  if (!message) {
    const candidate = snapshot(asOf).goals.candidates[0];
    return result(`Hi ${h.customer.first_name}, I'm Kate. ${candidate ? candidate.why_now : 'I can explain your cards or help shape your home.'}`, candidate ? [action('start_goal', 'Show me the plan', { playbook_id: candidate.playbook_id })] : []);
  }
  return result('I can explain cards, open goal journeys, or propose changes to your home. Tap a proposal to apply it.', [action('add_tile', 'Add Subscriptions', { component: 'SubscriptionsTile' })]);
}
export const localData = {
  async login(username: string, password: string) {
    const name = username.toLowerCase().trim();
    if (password !== 'demo' || (name !== 'advisor' && !CUSTOMER_NAMES.includes(name as typeof CUSTOMER_NAMES[number]))) throw new ApiError(401, 'Use lotte, sara, jan, marc or advisor, with password demo');
    saved.session = { username: name, role: name === 'advisor' ? 'advisor' : 'customer' };
    persist(); return reply(saved.session);
  },
  async session() { if (!saved.session) throw new ApiError(401, 'Choose a demo customer'); return reply(saved.session); },
  async logout() { saved.session = null; persist(); return { ok: true }; },
  home: async (asOf?: string) => reply(home(asOf)),
  timeline: async () => reply(customerFixture().timeline),
  feedback: (key: string, type: string, decision: Decision, asOf?: string) => mutate(() => {
    if (decision === 'reset') current().feedback = {};
    else current().feedback[key] = { type, decision, until: decision === 'snooze' ? addDays(asOf ?? TODAY, 7) : null };
  }, asOf),
  layoutPref: (component: Component, state: LayoutPrefState, asOf?: string) => mutate(() => {
    if (state === 'pinned') pin(component, null);
    else {
      delete current().pins[component];
      current().hidden = current().hidden.filter((c) => c !== component);
      if (state === 'hidden' && component !== 'ForYouFeed' && customerFixture().tiles[component]?.size !== 'hero') current().hidden.push(component);
    }
  }, asOf),
  pinAt: (component: Component, position: number | null, asOf?: string) => mutate(() => pin(component, position), asOf),
  layoutReset: (asOf?: string) => mutate(() => {
    current().pins = {}; current().hidden = []; current().dismissedSuggestions = []; delete current().tileGrid;
  }, asOf),
  saveTileGrid: async (grid: TileGridPrefs) => { current().tileGrid = copy(grid); persist(); return { ok: true }; },
  style: (style: StylePrefs, asOf?: string) => mutate(() => { current().style = copy(style); }, asOf),
  suggestion: (component: Component, decision: 'accept' | 'dismiss', asOf?: string) => mutate(() => { if (decision === 'accept') pin(component, null); else current().dismissedSuggestions.push(component); }, asOf),
  consent: (consent: boolean, asOf?: string) => mutate(() => { current().consent = consent; }, asOf),
  declare: (signal: DeclaredSignal, state: 'set' | 'clear', asOf?: string) => mutate(() => {
    current().declared = current().declared.filter((d) => d.signal !== signal);
    if (state === 'set') current().declared.push({ signal, created_at: asOf ?? TODAY });
  }, asOf),
  kate: async (message: string, cardKey: string | null, history: KateTurn[], asOf?: string) => reply(kate(message, cardKey, history, asOf)),
};
