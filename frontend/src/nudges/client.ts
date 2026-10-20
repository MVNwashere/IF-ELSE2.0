// Nudge endpoints, or with ?mock=1 the demo engine (demo/nudges.ts), like data.ts and ecosystem/client.ts.
import { call } from "../api";
import { MOCK } from "../data";
import { localNudges } from "../demo/nudges";
import type { AckResponse, NudgeAck, NudgeStats, NudgesResponse } from "./types";

const ISO = /^\d{4}-\d{2}-\d{2}$/;

function query(asOf?: string, since?: string): string {
  const q = new URLSearchParams();
  if (asOf && ISO.test(asOf)) q.set("as_of", asOf);
  if (since && ISO.test(since)) q.set("since", since);
  const s = q.toString();
  return s ? `?${s}` : "";
}

const apiNudges = {
  list: (asOf?: string, since?: string): Promise<NudgesResponse> => call<NudgesResponse>("GET", `/api/me/nudges${query(asOf, since)}`),
  ack: (key: string, action: NudgeAck, asOf?: string): Promise<AckResponse> =>
    call<AckResponse>("POST", `/api/me/nudges/${encodeURIComponent(key)}/ack${query(asOf)}`, { action }),
  reset: (): Promise<{ ok: boolean }> => call<{ ok: boolean }>("POST", "/api/me/nudges-reset"),
  stats: (): Promise<NudgeStats> => call<NudgeStats>("GET", "/api/ecosystem/nudge-stats"),
};

export const nudgeApi: typeof apiNudges = MOCK ? localNudges : apiNudges;
