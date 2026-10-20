// The profile behind ?mock=1: a few fields per demo customer, kept in memory, enough to click through "What KBC
// knows about you". Same interface as profileData in data.ts.
import type { CorrectionKind, FactValue, ProfileFactKey, ProfileField, ProfileResponse, Purpose } from '../api';
import { copy, currentName, snapshot, type CustomerName } from './store';

const opts = (o: Record<string, string>) => Object.entries(o).map(([value, label]) => ({ value, label }));
const field = (f: Pick<ProfileField, 'key' | 'label' | 'category' | 'kind' | 'hint'> & Partial<ProfileField>): ProfileField =>
  ({ options: [], min: null, max: null, used_for: ["Kate's answers", 'your advisor'], value: null, value_label: null, source: null, updated_on: null, ...f });

function fresh(): ProfileResponse {
  const home = snapshot().home;
  return {
    as_of: home.as_of,
    first_name: home.customer.first_name,
    fields: [
      field({ key: 'partner', label: 'Relationship', category: 'household', kind: 'enum', hint: 'Shared costs and protection depend on it.', options: opts({ single: 'single', partner: 'living together', married: 'married' }) }),
      field({ key: 'children', label: 'Children living with you', category: 'household', kind: 'int', hint: 'Your home shows family budget tools when you have children.', min: 0, max: 12, used_for: ['your home and feed', "Kate's answers", 'your advisor'] }),
      field({ key: 'employment', label: 'Work', category: 'work', kind: 'enum', hint: 'Freelancers see VAT and invoices; retirees see their pension.', options: opts({ employee: 'an employee', self_employed: 'self-employed', retired: 'retired' }), used_for: ['your home and feed', "Kate's answers", 'your advisor'] }),
      field({ key: 'avoid_topics', label: 'No offers about', category: 'contact', kind: 'set', hint: 'We hold back offers and goal suggestions on these topics.', options: opts({ investing: 'investing', insurance: 'insurance', credit: 'loans and credit' }) }),
    ],
    declared: [],
    personas: home.persona_mix.map((p) => ({ persona: p.persona, label: p.persona.replace(/_/g, ' '), weight_pct: Math.round(p.weight * 100), evidence: p.evidence, from_you: false })),
    goals: snapshot().goals.candidates.map((c) => ({ playbook_id: c.playbook_id, title: c.title, evidence: c.evidence })),
    corrections: [],
    permissions: [
      { purpose: 'personalise_offers', label: 'Offers based on my data', description: 'KBC may use your transactions to pick the offers you see.', when_off: 'You only see service messages and alerts, no offers.', allowed: true },
      { purpose: 'detect_life_events', label: 'Spot life changes from my transactions', description: 'KBC may notice changes like a move, a new job or a baby on the way, and suggest a plan.', when_off: 'No goal suggestions from your transactions.', allowed: true },
      { purpose: 'kate_memory', label: 'Kate may remember what I tell her', description: 'When you mention something about yourself, Kate offers to save it here.', when_off: "Kate won't offer to save anything you tell her.", allowed: true },
      { purpose: 'kate_ai', label: 'Kate may use an AI model', description: "Kate's answers are written by an AI model.", when_off: 'Kate answers with built-in rules only.', allowed: false },
      { purpose: 'advisor_view', label: 'My advisor may see my profile', description: 'Your KBC advisor can see this page to prepare a conversation.', when_off: 'Your advisor sees your products, not this profile.', allowed: true },
    ],
    data_access: { partners_with_access: 0, fields_shared: 0, sources_connected: 0 },
  };
}

const profiles = new Map<CustomerName, ProfileResponse>();
function mine(): ProfileResponse {
  const name = currentName();
  if (!profiles.has(name)) profiles.set(name, fresh());
  return profiles.get(name)!;
}
function update(fn: (p: ProfileResponse) => ProfileResponse): Promise<ProfileResponse> {
  const next = fn(mine());
  profiles.set(currentName(), next);
  return Promise.resolve(copy(next));
}
function withFact(p: ProfileResponse, key: ProfileFactKey, value: FactValue | null, source: 'you' | 'kate' | null): ProfileResponse {
  return {
    ...p,
    fields: p.fields.map((f) => f.key !== key ? f : {
      ...f, value, source, updated_on: value === null ? null : p.as_of,
      value_label: value === null ? null : Array.isArray(value)
        ? value.map((v) => f.options.find((o) => o.value === v)?.label ?? v).join(', ')
        : f.kind === 'int' ? `${value} child${value === 1 ? '' : 'ren'}`
        : f.options.find((o) => o.value === value)?.label ?? String(value),
    }),
  };
}

export const localProfile = {
  get: (_asOf?: string) => Promise.resolve(copy(mine())),
  setFact: (key: ProfileFactKey, value: FactValue, via: 'you' | 'kate', _asOf?: string) => update((p) => withFact(p, key, value, via)),
  deleteFact: (key: ProfileFactKey, _asOf?: string) => update((p) => withFact(p, key, null, null)),
  forgetKate: (_asOf?: string) => update((p) => p.fields.filter((f) => f.source === 'kate').reduce((acc, f) => withFact(acc, f.key, null, null), p)),
  correction: (kind: CorrectionKind, target: string, state: 'set' | 'clear', _asOf?: string) => update((p) => {
    const rest = p.corrections.filter((c) => !(c.kind === kind && c.target === target));
    const label = kind === 'persona' ? `Not ${target.replace(/_/g, ' ')}` : `Not interested: ${target.replace(/_/g, ' ')}`;
    return {
      ...p,
      corrections: state === 'set' ? [...rest, { kind, target, label, created_on: p.as_of }] : rest,
      personas: kind === 'persona' && state === 'set' ? p.personas.filter((x) => x.persona !== target) : p.personas,
      goals: kind === 'goal' && state === 'set' ? p.goals.filter((g) => g.playbook_id !== target) : p.goals,
    };
  }),
  permission: (purpose: Purpose, allowed: boolean, _asOf?: string) =>
    update((p) => ({ ...p, permissions: p.permissions.map((x) => (x.purpose === purpose ? { ...x, allowed } : x)) })),
};
