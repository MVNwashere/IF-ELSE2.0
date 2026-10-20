// Ecosystem endpoints, switching to the in-memory mock engine with ?mock=1 (like data.ts).
import { api } from "../api";
import { MOCK } from "../data";
import { mockEco } from "./mock";
import type { ConsentsResponse, EcosystemOverview, Goal, GoalsResponse, StepDecision } from "./types";

export const eco = {
  goals: (asOf?: string): Promise<GoalsResponse> => (MOCK ? mockEco.goals(asOf) : api.goals(asOf)),
  startGoal: (playbookId: string, asOf?: string): Promise<Goal> => (MOCK ? mockEco.startGoal(playbookId) : api.startGoal(playbookId, asOf)),
  stepDecision: (goalId: number, stepId: string, decision: StepDecision, asOf?: string): Promise<Goal> =>
    MOCK ? mockEco.stepDecision(goalId, stepId, decision) : api.stepDecision(goalId, stepId, decision, asOf),
  cancelGoal: (goalId: number) => (MOCK ? mockEco.cancelGoal(goalId) : api.cancelGoal(goalId)),
  consents: (): Promise<ConsentsResponse> => (MOCK ? mockEco.consents() : api.consents()),
  revokeConsent: (grantId: number): Promise<ConsentsResponse> => (MOCK ? mockEco.revokeConsent(grantId) : api.revokeConsent(grantId)),
  goalsReset: () => (MOCK ? mockEco.goalsReset() : api.goalsReset()),
  overview: (): Promise<EcosystemOverview> => (MOCK ? mockEco.overview() : api.ecosystemOverview()),
};
