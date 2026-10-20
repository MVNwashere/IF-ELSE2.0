// Kate nudges on the phone: the inbox for the current date, and a playback queue. When the demo's time-travel date
// moves forward, the nudges that would have buzzed in (previous date, new date] play one after another.
import { useCallback, useEffect, useRef, useState } from "react";
import { addDays, daysBetween } from "../format";
import { nudgeApi } from "./client";
import type { Banner, Nudge, NudgeAck, NudgesResponse } from "./types";
import { NUDGE_REPLAY_EVENT, NUDGE_RESET_EVENT } from "./types";

const INBOX_DAYS = 30;
const MAX_PLAY_DAYS = 92;

export function toBanners(nudges: Nudge[]): Banner[] {
  const out: Banner[] = [];
  const digests = new Map<string, Nudge[]>();
  for (const n of nudges) {
    if (n.status !== "new" || n.channel === "inbox") continue;
    if (n.channel === "digest" && n.digest_id) {
      const group = digests.get(n.digest_id);
      if (group) { group.push(n); continue; }
      const fresh = [n];
      digests.set(n.digest_id, fresh);
      out.push({ kind: "digest", id: n.digest_id, nudges: fresh });
    } else {
      out.push({ kind: "single", nudge: n });
    }
  }
  return out;
}

export function useNudges(asOf: string, customerKey: string) {
  const [inbox, setInbox] = useState<NudgesResponse | null>(null);
  const [queue, setQueue] = useState<Banner[]>([]);
  const [inboxOpen, setInboxOpen] = useState(false);
  const prev = useRef<{ asOf: string; customer: string } | null>(null);
  const seq = useRef(0);

  const loadInbox = useCallback(async () => {
    const my = ++seq.current;
    try {
      const r = await nudgeApi.list(asOf, addDays(asOf, -INBOX_DAYS));
      if (my === seq.current) setInbox(r);
    } catch (e) {
      if (my === seq.current) setInbox(null);
      console.warn("nudges unavailable", e);   // keep the rest of the app working
    }
  }, [asOf]);

  // windows are fetched one after another so a fast slider drag still plays in date order
  const chain = useRef<Promise<void>>(Promise.resolve());
  const play = useCallback((since: string, to: string) => {
    chain.current = chain.current.then(async () => {
      try {
        const r = await nudgeApi.list(to, since);
        const banners = toBanners(r.nudges);
        if (banners.length) setQueue((q) => [...q, ...banners]);
      } catch (e) {
        console.warn("nudge playback unavailable", e);
      }
    });
    return chain.current;
  }, []);

  useEffect(() => {
    const p = prev.current;
    prev.current = { asOf, customer: customerKey };
    void loadInbox();
    if (!p || p.customer !== customerKey) { setQueue([]); return; }
    const gap = daysBetween(p.asOf, asOf);
    if (gap > 0 && gap <= MAX_PLAY_DAYS) void play(p.asOf, asOf);
  }, [asOf, customerKey, loadInbox, play]);

  useEffect(() => {
    const onReplay = (e: Event) => {
      const days = Number((e as CustomEvent<{ days?: number }>).detail?.days ?? 10);
      void play(addDays(asOf, -Math.min(MAX_PLAY_DAYS, Math.max(1, days))), asOf);
    };
    const onReset = () => { setQueue([]); void loadInbox(); };
    window.addEventListener(NUDGE_REPLAY_EVENT, onReplay);
    window.addEventListener(NUDGE_RESET_EVENT, onReset);
    return () => {
      window.removeEventListener(NUDGE_REPLAY_EVENT, onReplay);
      window.removeEventListener(NUDGE_RESET_EVENT, onReset);
    };
  }, [asOf, play, loadInbox]);

  const ack = useCallback(async (n: Nudge, action: NudgeAck) => {
    const status = action === "mute" && n.mutable ? "muted" : action === "opened" ? "opened" : "dismissed";
    setInbox((r) => (r ? { ...r, nudges: r.nudges.map((x) => (x.nudge_key === n.nudge_key ? { ...x, status } : x)) } : r));
    try {
      await nudgeApi.ack(n.nudge_key, action, asOf);
    } catch (e) {
      console.warn("nudge ack failed", e);
    }
    if (action === "mute") void loadInbox();
  }, [asOf, loadInbox]);

  const next = useCallback(() => setQueue((q) => q.slice(1)), []);
  const unread = inbox?.nudges.filter((n) => n.status === "new" && n.channel !== "inbox").length ?? 0;

  return { inbox, current: queue[0] ?? null, queued: queue.length, next, ack, unread, inboxOpen, setInboxOpen, reload: loadInbox };
}

export type NudgesState = ReturnType<typeof useNudges>;
