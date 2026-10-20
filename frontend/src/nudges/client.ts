// Nudge endpoints, switching to the in-memory mock with ?mock=1 (like data.ts and ecosystem/client.ts).
import { call } from "../api";
import { MOCK } from "../data";
import { mockNudges } from "./mock";
import type { AckResponse, NudgeAck, NudgeStats, NudgesResponse } from "./types";

const ISO = /^\d{4}-\d{2}-\d{2}$/;

function query(asOf?: string, since?: string): string {
  const q = new URLSearchParams();
  if (asOf && ISO.test(asOf)) q.set("as_of", asOf);
  if (since && ISO.test(since)) q.set("since", since);
  const s = q.toString();
  return s ? `?${s}` : "";
}

export const nudgeApi = {
  list: (asOf?: string, since?: string): Promise<NudgesResponse> =>
    MOCK ? mockNudges.list(asOf, since) : call<NudgesResponse>("GET", `/api/me/nudges${query(asOf, since)}`),
  ack: (key: string, action: NudgeAck, asOf?: string): Promise<AckResponse> =>
    MOCK ? mockNudges.ack(key, action)
      : call<AckResponse>("POST", `/api/me/nudges/${encodeURIComponent(key)}/ack${query(asOf)}`, { action }),
  reset: () => (MOCK ? mockNudges.reset() : call<{ ok: boolean }>("POST", "/api/me/nudges-reset")),
  stats: (): Promise<NudgeStats> => (MOCK ? mockNudges.stats() : call<NudgeStats>("GET", "/api/ecosystem/nudge-stats")),
};
