// Ecosystem endpoints, switching to the in-memory mock engine with ?mock=1 (like data.ts).
import { api, call } from "../api";
import { MOCK } from "../data";
import { mockEco } from "./mock";
import type { ConsentsResponse, EcosystemOverview, Goal, GoalsResponse, SourcesResponse, StepDecision } from "./types";

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
  disconnectSource: (sourceId: string, asOf?: string): Promise<SourcesResponse> =>
    MOCK ? mockEco.disconnectSource(sourceId)
      : call<SourcesResponse>("POST", withAsOf(`/api/me/sources/${encodeURIComponent(sourceId)}/disconnect`, asOf)),
};
