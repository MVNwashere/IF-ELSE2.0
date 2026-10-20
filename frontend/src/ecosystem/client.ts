// Ecosystem endpoints, or with ?mock=1 the demo engine (demo/ecosystem.ts), like data.ts.
import { api, call } from "../api";
import { MOCK } from "../data";
import { localEco } from "../demo/ecosystem";
import type { ConsentsResponse, EcosystemOverview, Goal, GoalsResponse, SimMode, SourcesResponse, StallAnswer, StepDecision } from "./types";

const withAsOf = (path: string, asOf?: string) => (asOf ? `${path}?as_of=${encodeURIComponent(asOf)}` : path);

const apiEco = {
  goals: (asOf?: string): Promise<GoalsResponse> => api.goals(asOf),
  // a goal's roadmap before it starts: read-only, nothing is stored or shared
  previewGoal: (playbookId: string, asOf?: string): Promise<Goal> => api.previewGoal(playbookId, asOf),
  startGoal: (playbookId: string, asOf?: string): Promise<Goal> => api.startGoal(playbookId, asOf),
  stepDecision: (goalId: number, stepId: string, decision: StepDecision, asOf?: string, partnerId?: string): Promise<Goal> =>
    call<Goal>("POST", withAsOf(`/api/me/goals/${encodeURIComponent(goalId)}/steps/${encodeURIComponent(stepId)}`, asOf),
      partnerId ? { decision, partner_id: partnerId } : { decision }),
  cancelGoal: (goalId: number): Promise<unknown> => api.cancelGoal(goalId),
  consents: (): Promise<ConsentsResponse> => api.consents(),
  revokeConsent: (grantId: number): Promise<ConsentsResponse> => api.revokeConsent(grantId),
  goalsReset: (): Promise<unknown> => api.goalsReset(),
  overview: (): Promise<EcosystemOverview> => api.ecosystemOverview(),
  // inbound data sources: data KBC reads, with the customer's OK
  sources: (asOf?: string): Promise<SourcesResponse> => call<SourcesResponse>("GET", withAsOf("/api/me/sources", asOf)),
  connectSource: (sourceId: string, playbookId: string, asOf?: string): Promise<SourcesResponse> =>
    call<SourcesResponse>("POST", withAsOf(`/api/me/sources/${encodeURIComponent(sourceId)}/connect`, asOf), { playbook_id: playbookId }),
  disconnectSource: (sourceId: string, asOf?: string): Promise<SourcesResponse> =>
    call<SourcesResponse>("POST", withAsOf(`/api/me/sources/${encodeURIComponent(sourceId)}/disconnect`, asOf)),
  // households: share a goal, accept an invitation
  invite: (goalId: number, username: string, asOf?: string): Promise<Goal | null> =>
    call<Goal>("POST", withAsOf(`/api/me/goals/${encodeURIComponent(goalId)}/household`, asOf), { username }),
  answerInvite: (goalId: number, accept: boolean, asOf?: string): Promise<unknown> =>
    call("POST", withAsOf(`/api/me/household/${encodeURIComponent(goalId)}`, asOf), { accept }),
  // "still want this?": keep, pause, resume or stop a stalled journey
  stall: (goalId: number, answer: StallAnswer, asOf?: string): Promise<unknown> =>
    call("POST", withAsOf(`/api/me/goals/${encodeURIComponent(goalId)}/stall`, asOf), { answer }),
  // console demo switch: how a simulated partner answers
  simulatePartner: (partnerId: string, mode: SimMode): Promise<unknown> =>
    call("POST", `/api/ecosystem/partners/${encodeURIComponent(partnerId)}/simulate`, { mode }),
};

// The demo engine has one customer at a time and no partners to steer: households, stalls and the partner switch
// are no-ops there.
const mockEco: typeof apiEco = {
  ...localEco,
  invite: () => Promise.resolve(null),
  answerInvite: () => Promise.resolve(null),
  stall: () => Promise.resolve(null),
  simulatePartner: () => Promise.resolve(null),
};

export const eco = MOCK ? mockEco : apiEco;
