// Kate, the chat assistant. Her actions are proposals: nothing happens until the customer taps a button,
// and the button calls the same validated endpoint the rest of the app uses. Text is rendered as text nodes only.
import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import type { GalleryItem, KateAction, KateReply, KateTurn } from "../api";
import { NAV_ICONS } from "../components/icons";
import { componentLabel } from "../format";
import Sheet from "./Sheet";

export const KATE_MAX_INPUT = 500;
const TURN_MAX = 600;
const HISTORY_MAX = 12;

export interface KateMsg {
  id: number;
  role: "user" | "kate";
  text: string;
  actions?: KateAction[];
  done?: number[];
  quick?: string[];
  source?: KateReply["source"];
}

type AskFn = (message: string, cardKey: string | null, history: KateTurn[]) => Promise<KateReply>;
/** Runs a proposal. Resolves true when it succeeded. */
type ExecFn = (action: KateAction) => Promise<boolean>;

function toHistory(log: KateMsg[]): KateTurn[] {
  return log.slice(-HISTORY_MAX).map((m) => ({ role: m.role, text: m.text.slice(0, TURN_MAX) }));
}

export function confirmation(action: KateAction, gallery: GalleryItem[]): string | null {
  const label = action.component ? componentLabel(action.component, gallery) : "that tile";
  switch (action.kind) {
    case "pin_tile": return `Done, pinned ${label} to your home.`;
    case "add_tile": return `Done, added ${label} to your home.`;
    case "hide_tile": return `Done, ${label} is hidden. You can bring it back with Edit → Add tile.`;
    case "snooze_card": return "Done, I've snoozed that for 7 days.";
    case "dismiss_card": return "Done, I've dismissed that one.";
    case "set_style": return "Done, I've updated how your app looks. You can change it any time via your avatar.";
    case "reset_style": return "Done, everything is back to Auto.";
    case "declare": return "Thanks for telling me. I've adapted your home to it.";
    case "open_card": return null;
  }
}

let nextId = 1;

export function useKateChat(ask: AskFn, exec: ExecFn, gallery: GalleryItem[]) {
  const [log, setLog] = useState<KateMsg[]>([]);
  const [pending, setPending] = useState(false);
  const [cardKey, setCardKey] = useState<string | null>(null);
  const logRef = useRef<KateMsg[]>([]);
  const seq = useRef(0);

  const commit = useCallback((next: KateMsg[]) => { logRef.current = next; setLog(next); }, []);

  const send = useCallback(async (text: string, key: string | null, base: KateMsg[]) => {
    const message = text.trim().slice(0, KATE_MAX_INPUT);
    const history = toHistory(base);
    const withUser = message ? [...base, { id: nextId++, role: "user" as const, text: message }] : base;
    commit(withUser);
    const mySeq = ++seq.current;
    setPending(true);
    try {
      const r = await ask(message, key, history);
      if (mySeq !== seq.current) return;
      commit([...logRef.current, { id: nextId++, role: "kate", text: r.reply, actions: r.actions, done: [], quick: r.quick_replies, source: r.source }]);
    } catch {
      if (mySeq !== seq.current) return;
      commit([...logRef.current, { id: nextId++, role: "kate", text: "Sorry, I can't answer right now. Please try again in a moment." }]);
    } finally {
      if (mySeq === seq.current) setPending(false);
    }
  }, [ask, commit]);

  /** From a card or a KateTile chip: a fresh conversation. From the nav: resume, or let Kate open. */
  const start = useCallback((key: string | null, message?: string) => {
    if (key || message) {
      setCardKey(key);
      void send(message ?? "", key, []);
    } else if (logRef.current.length === 0) {
      setCardKey(null);
      void send("", null, []);
    }
  }, [send]);

  const reset = useCallback(() => {
    setCardKey(null);
    void send("", null, []);
  }, [send]);

  const say = useCallback((text: string) => { void send(text, cardKey, logRef.current); }, [send, cardKey]);

  const runAction = useCallback(async (msgId: number, idx: number, action: KateAction) => {
    const markDone = () => commit(logRef.current.map((m) => (m.id === msgId ? { ...m, done: [...(m.done ?? []), idx] } : m)));
    if (action.kind === "open_card") { markDone(); await exec(action); return; }
    const ok = await exec(action);
    if (!ok) return;
    markDone();
    const text = confirmation(action, gallery);
    if (text) commit([...logRef.current, { id: nextId++, role: "kate", text }]);
  }, [commit, exec, gallery]);

  return { log, pending, start, reset, say, runAction };
}

export type KateChat = ReturnType<typeof useKateChat>;

export default function KateSheet({ chat, onClose }: { chat: KateChat; onClose: () => void }) {
  const [input, setInput] = useState("");
  const logEl = useRef<HTMLDivElement>(null);
  const { log, pending } = chat;
  const lastSourced = [...log].reverse().find((m) => m.role === "kate" && m.source);
  const last = log[log.length - 1];
  const quick = !pending && last?.role === "kate" ? last.quick ?? [] : [];

  useEffect(() => {
    const el = logEl.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [log.length, pending]);

  const submit = () => {
    const t = input.trim();
    if (!t || pending) return;
    setInput("");
    chat.say(t);
  };

  return (
    <Sheet
      full
      className="kate-sheet"
      onClose={onClose}
      title={<span className="kate-title"><span className="kate-avatar sm" aria-hidden="true">K</span>Kate</span>}
      headerExtra={
        <>
          {lastSourced?.source && (
            <span className="kate-source" title={lastSourced.source === "llm" ? "Written by an AI model, checked by rules" : "Answer from built-in rules"}>
              {lastSourced.source === "llm" ? "AI" : "rules"}
            </span>
          )}
          <button type="button" className="kate-new" title="New conversation" aria-label="New conversation" onClick={chat.reset}>↺</button>
        </>
      }
    >
      <div className="kate-log" ref={logEl}>
        <AnimatePresence initial={false}>
          {log.map((m) => (
            <motion.div
              key={m.id}
              className={`bubble-row ${m.role}`}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
            >
              <div className={`bubble ${m.role}`}>{m.text}</div>
              {m.actions && m.actions.length > 0 && (
                <div className="kate-actions">
                  {m.actions.map((a, i) => {
                    const done = m.done?.includes(i) ?? false;
                    return (
                      <button key={i} type="button" className="kate-action" disabled={done || pending} onClick={() => void chat.runAction(m.id, i, a)}>
                        {done ? `✓ ${a.label}` : a.label}
                      </button>
                    );
                  })}
                </div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
        {pending && (
          <div className="bubble-row kate">
            <div className="bubble kate typing" aria-label="Kate is typing"><i /><i /><i /></div>
          </div>
        )}
      </div>
      {quick.length > 0 && (
        <div className="kate-quick">
          {quick.map((q) => <button key={q} type="button" className="kate-chip" onClick={() => chat.say(q)}>{q}</button>)}
        </div>
      )}
      <form className="kate-input" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          maxLength={KATE_MAX_INPUT}
          placeholder="Ask Kate anything…"
          aria-label="Message to Kate"
        />
        <button type="submit" aria-label="Send" disabled={!input.trim() || pending}><NAV_ICONS.send /></button>
      </form>
    </Sheet>
  );
}
