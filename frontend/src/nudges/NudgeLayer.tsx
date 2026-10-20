// Kate's lock-screen-style notifications inside the phone frame, the bell and the Kate inbox.
// Tap = run the one action (and ack "opened"); swipe or ✕ = "dismissed"; long-press or ⋯ = "Mute this topic".
// Text nodes only: every string from the backend is rendered as plain text.
import { AnimatePresence, motion, type PanInfo } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import { NAV_ICONS } from "../components/icons";
import { MaskedText } from "../privacy";
import Sheet from "../ui/Sheet";
import type { Banner, Nudge } from "./types";
import { TIER_LABEL } from "./types";
import type { NudgesState } from "./useNudges";
import "./nudges.css";

const SHOW_MS = 8000;
const GAP_MS = 700;
const LONG_PRESS_MS = 550;
const SWIPE_PX = 90;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function when(iso: string): string {
  const [d, t] = iso.split("T");
  const [, m, day] = d.split("-").map(Number);
  return `${day} ${MONTHS[(m || 1) - 1]}, ${(t ?? "").slice(0, 5)}`;
}

function channelLine(n: Nudge): string {
  if (n.channel === "push") return n.tier === "urgent" ? "Sent straight away (urgent)" : "Kate buzzed you";
  if (n.channel === "digest") return "In your morning digest";
  return n.held_reason ?? "Kept quiet in your inbox";
}

export function BellIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
    </svg>
  );
}

/** The bell for the phone header. */
export function NudgeBell({ nudges }: { nudges: NudgesState }) {
  const n = nudges.unread;
  return (
    <button type="button" className="icon-btn nudge-bell" aria-label={n ? `Kate inbox, ${n} new` : "Kate inbox"} title="Kate inbox" onClick={() => nudges.setInboxOpen(true)}>
      <BellIcon />
      {n > 0 && <span className="nudge-badge" aria-hidden="true">{n > 9 ? "9+" : n}</span>}
    </button>
  );
}

interface BannerProps {
  banner: Banner;
  reduceMotion: boolean;
  onRun: (n: Nudge) => void;
  onAck: (n: Nudge, a: "dismissed" | "mute") => void;
  onInbox: () => void;
  onDone: () => void;
}

function NudgeBanner({ banner, reduceMotion, onRun, onAck, onInbox, onDone }: BannerProps) {
  const [menu, setMenu] = useState(false);
  const [paused, setPaused] = useState(false);
  const press = useRef<number | null>(null);
  const longPressed = useRef(false);
  const single = banner.kind === "single" ? banner.nudge : null;

  useEffect(() => {
    if (menu || paused) return;
    const t = window.setTimeout(onDone, SHOW_MS);
    return () => window.clearTimeout(t);
  }, [menu, paused, onDone]);

  const clearPress = () => { if (press.current) window.clearTimeout(press.current); press.current = null; };
  const startPress = () => {
    longPressed.current = false;
    clearPress();
    press.current = window.setTimeout(() => { longPressed.current = true; setMenu(true); }, LONG_PRESS_MS);
  };
  const tap = () => {
    clearPress();
    if (longPressed.current) { longPressed.current = false; return; }
    if (single) onRun(single); else onInbox();
  };
  const dismiss = () => { if (single) onAck(single, "dismissed"); else onDone(); };
  const onDragEnd = (_: unknown, info: PanInfo) => { if (Math.abs(info.offset.x) > SWIPE_PX) dismiss(); };

  const urgent = single?.tier === "urgent";
  const title = single ? single.title : `Your morning digest: ${banner.kind === "digest" ? banner.nudges.length : 0} things`;
  const why = single ? single.why : banner.kind === "digest" ? banner.nudges.map((n) => n.title).join(" · ") : "";
  const stamp = single ? single.delivered_at : banner.kind === "digest" ? banner.nudges[0].delivered_at : "";

  return (
    <motion.div
      className={`nudge-banner ${urgent ? "urgent" : ""}`}
      role="alert"
      initial={{ y: -150, opacity: 0 }}
      animate={reduceMotion ? { y: 0, opacity: 1 } : { y: 0, opacity: 1, x: [0, -5, 5, -4, 4, -2, 0] }}
      exit={{ y: -150, opacity: 0, transition: { duration: 0.25 } }}
      transition={{ y: { type: "spring", stiffness: 420, damping: 34 }, opacity: { duration: 0.2 }, x: { duration: 0.5, delay: 0.35 } }}
      drag={reduceMotion ? false : "x"}
      dragSnapToOrigin
      onDragEnd={onDragEnd}
      onHoverStart={() => setPaused(true)}
      onHoverEnd={() => setPaused(false)}
    >
      <div className="nudge-head">
        <span className="nudge-app" aria-hidden="true">K</span>
        <span className="nudge-from">Kate · KBC</span>
        {single && single.tier !== "moment" && <span className={`nudge-tier t-${single.tier}`}>{TIER_LABEL[single.tier]}</span>}
        <span className="nudge-time">{stamp ? when(stamp) : ""}</span>
        <button type="button" className="nudge-x" aria-label="More options" aria-expanded={menu} onClick={() => setMenu((v) => !v)}>⋯</button>
        <button type="button" className="nudge-x" aria-label="Dismiss" onClick={dismiss}><NAV_ICONS.close /></button>
      </div>
      <button
        type="button"
        className="nudge-main"
        onClick={tap}
        onPointerDown={startPress}
        onPointerUp={clearPress}
        onPointerLeave={clearPress}
        onContextMenu={(e) => { e.preventDefault(); setMenu(true); }}
      >
        <b><MaskedText text={title} /></b>
        <span className="nudge-why"><MaskedText text={why} /></span>
        <span className="nudge-cta"><MaskedText text={single ? single.action.label : "Open Kate's inbox"} /> →</span>
      </button>
      <AnimatePresence>
        {menu && (
          <motion.div className="nudge-menu" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}>
            {single ? (
              <>
                <button type="button" onClick={() => onAck(single, "dismissed")}>Not now</button>
                {single.mutable
                  ? <button type="button" onClick={() => onAck(single, "mute")}>Mute this topic for 90 days</button>
                  : <span className="nudge-note">Security alerts can't be muted.</span>}
              </>
            ) : (
              <button type="button" onClick={onInbox}>Open inbox</button>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function InboxItem({ n, onRun, onAck }: { n: Nudge; onRun: (n: Nudge) => void; onAck: (n: Nudge, a: "dismissed" | "mute") => void }) {
  const done = n.status !== "new";
  return (
    <li className={`nudge-item ${done ? "done" : ""} ${n.channel === "inbox" ? "quiet" : ""}`}>
      <div className="nudge-item-top">
        <span className={`nudge-tier t-${n.tier}`}>{TIER_LABEL[n.tier]}</span>
        <span className="nudge-time">{when(n.delivered_at)}</span>
        {n.status !== "new" && <span className="nudge-status">{n.status}</span>}
      </div>
      <b><MaskedText text={n.title} /></b>
      <p><MaskedText text={n.why} /></p>
      {n.evidence.length > 0 && (
        <details className="nudge-evidence">
          <summary>Why now?</summary>
          <ul>{n.evidence.map((e, i) => <li key={i}><MaskedText text={e} /></li>)}</ul>
        </details>
      )}
      <div className="nudge-item-foot">
        <span className="nudge-channel">{channelLine(n)}</span>
      </div>
      <div className="nudge-item-actions">
        <button type="button" className="btn-primary small" onClick={() => onRun(n)}><MaskedText text={n.action.label} /></button>
        {n.status === "new" && <button type="button" className="link" onClick={() => onAck(n, "dismissed")}>Not now</button>}
        {n.mutable && n.status !== "muted" && <button type="button" className="link" onClick={() => onAck(n, "mute")}>Mute topic</button>}
      </div>
    </li>
  );
}

interface LayerProps {
  nudges: NudgesState;
  reduceMotion: boolean;
  /** Runs the nudge's action in the app (start_goal / open_goal / open_card / passport). */
  onRun: (n: Nudge) => Promise<boolean> | boolean | void;
}

/** Mount once inside the .phone root (position: relative). */
export default function NudgeLayer({ nudges, reduceMotion, onRun }: LayerProps) {
  const { current, next, ack, inbox, inboxOpen, setInboxOpen } = nudges;
  const [visible, setVisible] = useState(true);

  // one banner at a time, with a short gap between them
  const done = useCallback(() => setVisible(false), []);
  useEffect(() => { setVisible(true); }, [current]);

  const run = useCallback((n: Nudge) => {
    void ack(n, "opened");
    setVisible(false);
    setInboxOpen(false);
    void onRun(n);
  }, [ack, onRun, setInboxOpen]);
  const onAck = useCallback((n: Nudge, a: "dismissed" | "mute") => { void ack(n, a); setVisible(false); }, [ack]);
  const openInbox = useCallback(() => { setVisible(false); setInboxOpen(true); }, [setInboxOpen]);

  const list = inbox ? [...inbox.nudges].reverse() : [];
  const b = inbox?.budget;

  return (
    <>
      <div className="nudge-slot" aria-live="polite">
        <AnimatePresence onExitComplete={() => window.setTimeout(next, GAP_MS)}>
          {current && visible && (
            <NudgeBanner
              key={current.kind === "single" ? current.nudge.nudge_key : current.id}
              banner={current}
              reduceMotion={reduceMotion}
              onRun={run}
              onAck={onAck}
              onInbox={openInbox}
              onDone={done}
            />
          )}
        </AnimatePresence>
      </div>
      <AnimatePresence>
        {inboxOpen && (
          <Sheet key="nudge-inbox" title="Kate's inbox" onClose={() => setInboxOpen(false)} className="nudge-sheet">
            {b && (
              <div className="nudge-budget">
                Kate buzzed you {b.used} of {b.limit} time{b.limit === 1 ? "" : "s"} this week. Urgent alerts always
                come through; everything else waits outside quiet hours ({b.quiet_hours}).
              </div>
            )}
            {list.length === 0 ? (
              <div className="nudge-empty">Nothing needs you right now. Kate only speaks up when money, a deadline or a next step is at stake.</div>
            ) : (
              <ul className="nudge-list">
                {list.map((n) => <InboxItem key={n.nudge_key} n={n} onRun={run} onAck={(x, a) => void ack(x, a)} />)}
              </ul>
            )}
          </Sheet>
        )}
      </AnimatePresence>
    </>
  );
}
