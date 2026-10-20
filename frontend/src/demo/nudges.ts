import statsJson from '../demo-data/nudge-stats.json';
import type { NudgeAck, NudgeStats, NudgeStatus, NudgesResponse } from '../nudges/types';
import { addDays, copy, current, customerFixture, persist, reply, saved, snapshot, TODAY } from './store';

const status = (action?: NudgeAck): NudgeStatus => action === 'opened' ? 'opened' : action === 'dismissed' ? 'dismissed' : action === 'mute' ? 'muted' : 'new';
export const localNudges = {
  async list(asOf?: string, since?: string): Promise<NudgesResponse> {
    const response = copy(snapshot(asOf).nudges);
    const state = current();
    const hi = asOf ?? TODAY;
    const lo = since ?? addDays(hi, -30);
    const byKey = new Map(customerFixture().snapshots.flatMap((s) => s.nudges.nudges).map((n) => [n.nudge_key, n]));
    response.as_of = hi; response.since = lo;
    response.nudges = [...byKey.values()].filter((n) => n.delivered_at.slice(0, 10) > lo && n.delivered_at.slice(0, 10) <= hi).map((n) => {
      const ack = state.nudgeAcks[n.nudge_key];
      return { ...copy(n), status: ack?.action === 'mute' && ack.mutedUntil && ack.mutedUntil < hi ? 'new' : status(ack?.action) };
    });
    response.candidates = response.nudges.length;
    response.held = response.nudges.filter((n) => n.channel === 'inbox').length;
    return reply(response);
  },
  async ack(key: string, action: NudgeAck, asOf?: string) {
    const known = customerFixture().snapshots.flatMap((s) => s.nudges.nudges).find((n) => n.nudge_key === key);
    if (!known) throw new Error('Nudge not found');
    if (action === 'mute' && !known.mutable) throw new Error('Urgent safety alerts cannot be muted');
    const mutedUntil = action === 'mute' ? addDays(asOf ?? TODAY, 90) : null;
    current().nudgeAcks[key] = { action, mutedUntil };
    persist(); return { nudge_key: key, status: status(action), muted_until: mutedUntil };
  },
  async reset() { current().nudgeAcks = {}; persist(); return { ok: true }; },
  async stats(): Promise<NudgeStats> {
    const stats = copy(statsJson) as NudgeStats;
    const acks = Object.values(saved.customers).flatMap((s) => Object.values(s.nudgeAcks));
    stats.acks = acks.length;
    stats.open_rate = acks.length ? acks.filter((a) => a.action === 'opened').length / acks.length : null;
    stats.dismiss_rate = acks.length ? acks.filter((a) => a.action === 'dismissed').length / acks.length : null;
    stats.mute_rate = acks.length ? acks.filter((a) => a.action === 'mute').length / acks.length : null;
    return reply(stats);
  },
};
