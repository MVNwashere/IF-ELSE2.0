// Ecosystem endpoints, switching to the in-memory mock engine with ?mock=1 (like data.ts).
import { api, call } from "../api";
import { MOCK } from "../data";
import { mockEco } from "./mock";
import type { ConsentsResponse, EcosystemOverview, Goal, GoalsResponse, SimMode, SourcesResponse, StallAnswer, StepDecision } from "./types";

const withAsOf = (path: string, asOf?: string) => (asOf ? `${path}?as_of=${encodeURIComponent(asOf)}` : path);

export const eco = {
  goals: (asOf?: string): Promise<GoalsResponse> => (MOCK ? mockEco.goals(asOf) : api.goals(asOf)),
  startGoal: (playbookId: string, asOf?: string): Promise<Goal> => (MOCK ? mockEco.startGoal(playbookId) : api.startGoal(playbookId, asOf)),
  stepDecision: (goalId: number, stepId: string, decision: StepDecision, asOf?: string, partnerId?: string): Promise<Goal> =>
    MOCK
      ? mockEco.stepDecision(goalId, stepId, decision)
      : call<Goal>("POST", withAsOf(`/api/me/goals/${encodeURIComponent(goalId)}/steps/${encodeURIComponent(stepId)}`, asOf),
        partnerId ? { decision, partner_id: partnerId } : { decision }),
  cancelGoal: (goalId: number) => (MOCK ? mockEco.cancelGoal(goalId) : api.cancelGoal(goalId)),
  consents: (): Promise<ConsentsResponse> => (MOCK ? mockEco.consents() : api.consents()),
  revokeConsent: (grantId: number): Promise<ConsentsResponse> => (MOCK ? mockEco.revokeConsent(grantId) : api.revokeConsent(grantId)),
  goalsReset: () => (MOCK ? mockEco.goalsReset() : api.goalsReset()),
  overview: (): Promise<EcosystemOverview> => (MOCK ? mockEco.overview() : api.ecosystemOverview()),
  // inbound data sources: data KBC reads, with the customer's OK
  sources: (asOf?: string): Promise<SourcesResponse> =>
    MOCK ? mockEco.sources() : call<SourcesResponse>("GET", withAsOf("/api/me/sources", asOf)),
  connectSource: (sourceId: string, playbookId: string, asOf?: string): Promise<SourcesResponse> =>
    MOCK ? mockEco.connectSource(sourceId, playbookId)
      : call<SourcesResponse>("POST", withAsOf(`/api/me/sources/${encodeURIComponent(sourceId)}/connect`, asOf), { playbook_id: playbookId }),
  // households: share a goal, accept an invitation (the mock engine has no second customer: no-ops there)
  invite: (goalId: number, username: string, asOf?: string): Promise<Goal | null> =>
    MOCK ? Promise.resolve(null)
      : call<Goal>("POST", withAsOf(`/api/me/goals/${encodeURIComponent(goalId)}/household`, asOf), { username }),
  answerInvite: (goalId: number, accept: boolean, asOf?: string): Promise<unknown> =>
    MOCK ? Promise.resolve(null) : call("POST", withAsOf(`/api/me/household/${encodeURIComponent(goalId)}`, asOf), { accept }),
  // "still want this?": keep, pause, resume or stop a stalled journey
  stall: (goalId: number, answer: StallAnswer, asOf?: string): Promise<unknown> =>
    MOCK ? Promise.resolve(null) : call("POST", withAsOf(`/api/me/goals/${encodeURIComponent(goalId)}/stall`, asOf), { answer }),
  // console demo switch: how a simulated partner answers
  simulatePartner: (partnerId: string, mode: SimMode): Promise<unknown> =>
    MOCK ? Promise.resolve(null) : call("POST", `/api/ecosystem/partners/${encodeURIComponent(partnerId)}/simulate`, { mode }),
  disconnectSource: (sourceId: string, asOf?: string): Promise<SourcesResponse> =>
    MOCK ? mockEco.disconnectSource(sourceId)
      : call<SourcesResponse>("POST", withAsOf(`/api/me/sources/${encodeURIComponent(sourceId)}/disconnect`, asOf)),
};
