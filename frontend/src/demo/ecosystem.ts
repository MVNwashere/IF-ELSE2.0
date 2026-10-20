import overviewJson from '../demo-data/overview.json';
import type { ConsentsResponse, EcosystemOverview, Goal, GoalsResponse, SourcesResponse, Step, StepDecision, WinTotals } from '../ecosystem/types';
import { addDays, copy, current, customerFixture, event, fixtures, persist, reply, saved, snapshot, TODAY } from './store';
import type { CustomerFixture, LocalCustomer } from './store';

function totals(steps: Step[], onlyDone: boolean): WinTotals {
  const total: WinTotals = { customer_eur: 0, hours_saved: 0, kbc_revenue_eur: 0, partner_fees_eur: 0, kbc_products: [], partner_leads: 0 };
  for (const step of steps) {
    if (step.already_held || (onlyDone && step.status !== 'done') || step.status === 'declined') continue;
    total.customer_eur += step.estimates.customer_eur;
    total.hours_saved += step.estimates.hours_saved;
    total.kbc_revenue_eur += step.estimates.kbc_revenue_eur;
    total.partner_fees_eur += step.estimates.partner_fee_eur;
    if (step.provider.kind === 'partner') total.partner_leads++;
    else if (step.estimates.kbc_revenue_eur > 0) total.kbc_products.push(step.products[0]?.name ?? step.title);
  }
  return total;
}
function refresh(goal: Goal): Goal {
  goal.progress = { done: goal.steps.filter((s) => s.status === 'done').length, total: goal.steps.length };
  if (goal.status !== 'cancelled') goal.status = goal.steps.every((s) => s.status === 'done' || s.status === 'declined') ? 'completed' : 'active';
  goal.outcome = totals(goal.steps, true);
  goal.potential = totals(goal.steps, false);
  return goal;
}
function settle(state: LocalCustomer, fixture: CustomerFixture, date: string): void {
  let changed = false;
  for (const grant of state.grants) {
    if (grant.status === 'active' && grant.expires_on < date) {
      grant.status = 'expired';
      grant.deletion_confirmed_by = `${grant.partner_name} (local simulation)`;
      grant.deletion_confirmed_at = new Date().toISOString();
      const step = state.goals.find((g) => g.goal_id === grant.goal_id)?.steps.find((s) => s.step_id === grant.step_id);
      if (step && step.status !== 'done') step.status = 'blocked';
      delete state.pending[`${grant.goal_id}/${grant.step_id}`];
      changed = true;
    }
  }
  for (const [key, pending] of Object.entries(state.pending)) {
    if (pending.due > Date.now()) continue;
    const [goalId, stepId] = key.split('/');
    const goal = state.goals.find((g) => g.goal_id === Number(goalId));
    const step = goal?.steps.find((s) => s.step_id === stepId);
    const grant = state.grants.find((g) => g.grant_id === step?.grant_id);
    if (goal && goal.status !== 'cancelled' && step?.status === 'in_progress' && step.ref === pending.ref && grant?.status === 'active') {
      step.status = 'done';
      step.result = fixture.results[`${goal.playbook_id}/${stepId}`] || `Completed by ${step.provider.name}.`;
      step.updated_at = new Date().toISOString();
      step.done_on = date;
      event(state, step.provider.id, 'done', `${step.provider.name}: ${step.result} (local simulation)`);
      refresh(goal);
    }
    delete state.pending[key];
    changed = true;
  }
  for (const source of state.sources ?? []) {
    if (source.status === 'connected' && source.expires_on && source.expires_on < date) {
      source.status = 'expired'; source.values = {}; changed = true;
    }
  }
  if (changed) persist();
}
function findGoal(id: number): Goal {
  const goal = current().goals.find((g) => g.goal_id === id && g.status !== 'cancelled');
  if (!goal) throw new Error('Goal not found for this customer');
  return goal;
}
function sources(date?: string): SourcesResponse {
  const state = current();
  state.sources ??= copy(customerFixture().sources.sources);
  settle(state, customerFixture(), date ?? state.asOf);
  return { sources: state.sources, connected: state.sources.filter((s) => s.status === 'connected').length, note: 'Browser-local demo data. No external services are connected.' };
}
function consents(): ConsentsResponse {
  const state = current();
  settle(state, customerFixture(), state.asOf);
  const active = state.grants.filter((g) => g.status === 'active' && g.granted_on <= state.asOf);
  return { grants: state.grants.filter((g) => g.granted_on <= state.asOf), partners_with_access: new Set(active.map((g) => g.partner_id)).size, fields_shared: active.reduce((n, g) => n + g.fields.length, 0), sources: sources().sources };
}
function revoke(id: number): void {
  const state = current();
  const grant = state.grants.find((g) => g.grant_id === id);
  if (!grant) throw new Error('Consent not found for this customer');
  if (grant.status !== 'active') return;
  grant.status = 'revoked'; grant.revoked_on = state.asOf;
  grant.deletion_confirmed_by = `${grant.partner_name} (local simulation)`;
  grant.deletion_confirmed_at = new Date().toISOString();
  const goal = state.goals.find((g) => g.goal_id === grant.goal_id);
  const step = goal?.steps.find((s) => s.step_id === grant.step_id);
  if (step && step.status !== 'done') step.status = 'blocked';
  delete state.pending[`${grant.goal_id}/${grant.step_id}`];
  if (goal) refresh(goal);
  event(state, grant.partner_id, 'revoked', `Access revoked; deletion simulated for ${grant.partner_name}`);
}

export const localEco = {
  async previewGoal(playbookId: string): Promise<Goal> {
    const template = customerFixture().templates[playbookId];
    if (!template) throw new Error('Unknown goal');
    return reply(template);
  },
  async goals(asOf?: string): Promise<GoalsResponse> {
    const base = copy(snapshot(asOf).goals);
    const state = current();
    settle(state, customerFixture(), state.asOf);
    const active = state.goals.filter((g) => g.status !== 'cancelled' && g.created_on <= state.asOf);
    const ids = new Set(active.map((g) => g.playbook_id));
    base.as_of = state.asOf;
    base.goals = active.map((g) => {
      const goal = copy(refresh(g));
      goal.steps.forEach((step) => {
        if (step.source_hint) step.source_hint.connected = sources().sources.some((s) => s.source_id === step.source_hint?.source_id && s.status === 'connected');
      });
      return goal;
    });
    base.candidates = base.candidates.filter((c) => !ids.has(c.playbook_id));
    return reply(base);
  },
  async startGoal(playbookId: string, asOf?: string): Promise<Goal> {
    snapshot(asOf);
    const state = current();
    const existing = state.goals.find((g) => g.playbook_id === playbookId && g.status !== 'cancelled');
    if (existing) return reply(refresh(existing));
    const template = customerFixture().templates[playbookId];
    if (!template) throw new Error('Unknown goal');
    const goal = copy(template);
    goal.goal_id = saved.nextId++;
    goal.created_on = state.asOf;
    goal.target_date = addDays(state.asOf, 60);
    goal.origin = snapshot(asOf).goals.candidates.some((c) => c.playbook_id === playbookId) ? 'detected' : 'stated';
    state.goals.push(refresh(goal));
    persist(); return reply(goal);
  },
  async stepDecision(goalId: number, stepId: string, decision: StepDecision, asOf?: string, partnerId?: string): Promise<Goal> {
    snapshot(asOf);
    const state = current();
    const goal = findGoal(goalId);
    const step = goal.steps.find((s) => s.step_id === stepId);
    if (!step) throw new Error('Step not found');
    if (step.already_held || step.status === 'done') return reply(goal);
    const key = `${goalId}/${stepId}`;
    if (decision === 'reset' || decision === 'decline') {
      if (step.grant_id) revoke(step.grant_id);
      delete state.pending[key]; step.result = ''; step.grant_id = null;
      step.status = decision === 'reset' ? 'proposed' : 'declined';
    } else {
      if (step.status === 'in_progress') return reply(goal);
      if (partnerId) {
        const option = step.alternatives?.find((o) => o.provider.id === partnerId);
        if (!option) throw new Error('Choose a listed partner');
        step.provider = copy(option.provider); step.fee = copy(option.fee); step.data_shared = copy(option.data_shared);
        step.alternatives?.forEach((o) => { o.chosen = o.provider.id === partnerId; });
      }
      if (step.provider.kind !== 'partner') {
        step.status = 'done'; step.done_on = state.asOf;
        step.result = customerFixture().results[`${goal.playbook_id}/${stepId}`] || 'Arranged in this local preview.';
        if (step.provider.kind === 'advisor') step.booking = `Demo appointment: ${addDays(state.asOf, 3)} at 10:00`;
        event(state, step.provider.id, 'done', `${step.title} (local simulation)`);
      } else {
        const grantId = saved.nextId++;
        step.grant_id = grantId; step.status = 'in_progress'; step.ref = `local-${goalId}-${stepId}-${grantId}`;
        state.grants.push({
          grant_id: grantId, partner_id: step.provider.id, partner_name: step.provider.name,
          goal_id: goalId, goal_title: goal.title, step_id: stepId, step_title: step.title,
          fields: copy(step.data_shared), purpose: step.description,
          granted_on: state.asOf, expires_on: addDays(state.asOf, step.consent_days), status: 'active', revoked_on: null,
          kbc_earns: step.fee?.kbc_earns,
        });
        state.pending[key] = { due: Date.now() + 1800, ref: step.ref };
        event(state, step.provider.id, 'outbound', `${step.title}: local partner simulation started`);
      }
    }
    step.updated_at = new Date().toISOString();
    refresh(goal); persist(); return reply(goal);
  },
  async cancelGoal(id: number) {
    const goal = findGoal(id);
    current().grants.filter((g) => g.goal_id === id && g.status === 'active').forEach((g) => revoke(g.grant_id));
    goal.status = 'cancelled';
    for (const key of Object.keys(current().pending)) if (key.startsWith(`${id}/`)) delete current().pending[key];
    persist(); return { ok: true };
  },
  async goalsReset() {
    const state = current();
    state.goals = []; state.grants = []; state.pending = {};
    persist(); return { ok: true };
  },
  async consents() { return reply(consents()); },
  async revokeConsent(id: number) { revoke(id); persist(); return reply(consents()); },
  async sources(asOf?: string) { return reply(sources(asOf)); },
  async connectSource(id: string, playbookId: string, asOf?: string): Promise<SourcesResponse> {
    snapshot(asOf);
    const source = sources(asOf).sources.find((s) => s.source_id === id);
    if (!source || !source.goals.includes(playbookId)) throw new Error('Source is unavailable for this goal');
    if (source.needs_consent) Object.assign(source, {
      status: 'connected', connected_on: current().asOf, expires_on: addDays(current().asOf, source.consent_days),
      playbook_id: playbookId, purpose: `${source.name} for ${customerFixture().templates[playbookId].title}`,
      values: copy(customerFixture().source_values[id] ?? {}),
    });
    persist(); return reply(sources(asOf));
  },
  async disconnectSource(id: string, asOf?: string): Promise<SourcesResponse> {
    const source = sources(asOf).sources.find((s) => s.source_id === id);
    if (source?.needs_consent) Object.assign(source, { status: 'available', connected_on: null, expires_on: null, playbook_id: null, purpose: '', values: {} });
    persist(); return reply(sources(asOf));
  },
  async overview(): Promise<EcosystemOverview> {
    const overview = copy(overviewJson) as EcosystemOverview;
    const localGoals: Goal[] = [];
    for (const name of Object.keys(fixtures) as (keyof typeof fixtures)[]) {
      const state = saved.customers[name];
      settle(state, fixtures[name], TODAY);
      localGoals.push(...state.goals.filter((g) => g.status !== 'cancelled').map(refresh));
    }
    for (const row of overview.funnel) {
      const matching = localGoals.filter((g) => g.playbook_id === row.playbook_id);
      row.started = matching.length;
      row.steps_done = matching.reduce((n, g) => n + g.progress.done, 0);
      row.completed = matching.filter((g) => g.status === 'completed').length;
    }
    overview.events = Object.values(saved.customers).flatMap((s) => s.events).sort((a, b) => b.at.localeCompare(a.at)).slice(0, 40);
    overview.realised = totals(localGoals.flatMap((g) => g.steps), true);
    overview.assumptions = ['Local frontend preview: actions and partner events are simulated in your browser.', 'Detection counts are fixed synthetic sample data; journey activity reflects your saved demo actions.'];
    overview.learning?.forEach((row) => {
      const goals = localGoals.filter((g) => g.playbook_id === row.playbook_id);
      row.started = goals.length; row.completed = goals.filter((g) => g.status === 'completed').length;
      row.start_rate = row.detected ? row.started / row.detected : null;
      row.completion_rate = row.started ? row.completed / row.started : null;
    });
    return reply(overview);
  },
};
