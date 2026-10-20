// The hero tile zooms open into the accounts screen.
//
// Open: a blue box starts exactly on top of the tile and grows into the big blue account tile (about half the
// screen). The tile's content cross-fades into the account: balance, a balance curve, money in/out and a
// scrollable history. The other accounts slide in underneath.
//
// Pick another account: its row turns blue and jumps up into the big tile, while the account that was in the
// tile drops into the slot the row came from. Closing plays the zoom backwards.
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";
import type { HomeResponse, Section } from "../api";
import { Icon } from "../components/icons";
import { useEur, useMasked } from "../privacy";
import type { Account, AccountKind, AccountsView } from "./accounts";
import BalanceChart from "./BalanceChart";
import { ChevronLeft } from "./glyphs";
import { buildHistory, groupByDay, txnMeta } from "./history";
import "./accounts.css";

/** Where the tile sits inside the phone, in the phone's own (unscaled) pixels. */
export interface ZoomOrigin {
  x: number;
  y: number;
  w: number;
  h: number;
  radius: number;
  /** class list of the hero card inside the tile (e.g. "hero tight"), so the main account keeps its colour. */
  variant: string;
  stageW: number;
  stageH: number;
}

interface Rect { x: number; y: number; w: number; h: number; radius: number }
interface Jump { id: string; rect: Rect; key: number }

interface Props {
  origin: ZoomOrigin;
  view: AccountsView;
  home: HomeResponse;
  hero: Section;
  /** The hero component again, shown at the start of the zoom so the tile visibly grows. */
  tile: ReactNode;
  onClose: () => void;
  /** Tapping the screen while amounts are hidden shows them for a few seconds (same as on the home screen). */
  onReveal: () => void;
}

/** The big blue tile takes this share of the phone screen. */
const TILE_SHARE = 0.52;
const TILE_RADIUS = 28;

const KIND_ICON: Record<AccountKind, string> = {
  current: "card",
  savings: "savings",
  reserve: "budget",
  child: "savings",
  business: "invoice",
  joint: "split",
};

const maskIban = (last4: string) => `BE•• •••• •••• ${last4}`;

const corners = (tl: number, tr: number, br: number, bl: number) => ({
  borderTopLeftRadius: tl,
  borderTopRightRadius: tr,
  borderBottomRightRadius: br,
  borderBottomLeftRadius: bl,
});

/** Position of an element inside the phone, undoing the PhoneScaler transform. */
function measure(phone: HTMLElement, el: HTMLElement): Rect {
  const p = phone.getBoundingClientRect();
  const k = p.width / phone.offsetWidth || 1;
  const r = el.getBoundingClientRect();
  return {
    x: (r.left - p.left) / k,
    y: (r.top - p.top) / k,
    w: r.width / k,
    h: r.height / k,
    radius: parseFloat(getComputedStyle(el).borderTopLeftRadius) || 14,
  };
}

function RowBody({ account }: { account: Account }) {
  const eur = useEur();
  return (
    <>
      <span className="zb-ico"><Icon name={KIND_ICON[account.kind]} /></span>
      <span className="zb-meta">
        <b>{account.name}</b>
        <small>{maskIban(account.last4)}</small>
      </span>
      <span className="zb-amt">{eur(account.balance_eur)}</span>
    </>
  );
}

export default function AccountsZoom({ origin, view, home, hero, tile, onClose, onReveal }: Props) {
  const reduce = useReducedMotion();
  const eur = useEur();
  const masked = useMasked();
  const tileH = Math.round(origin.stageH * TILE_SHARE);

  const byId = useMemo(() => new Map(view.accounts.map((a) => [a.id, a])), [view]);
  const mainId = view.accounts[0].id;

  // `current` is what the big tile shows, `slots` is the list below it. They only change together with a jump.
  const [current, setCurrent] = useState(mainId);
  const [slots, setSlots] = useState(() => view.accounts.slice(1).map((a) => a.id));
  const [hidden, setHidden] = useState(false);
  const [jump, setJump] = useState<Jump | null>(null);
  const jumped = useRef(false);

  // A different set of accounts (e.g. another customer) starts over on the main account.
  const signature = view.accounts.map((a) => a.id).join("|");
  useEffect(() => {
    setCurrent(mainId);
    setSlots(view.accounts.slice(1).map((a) => a.id));
    setHidden(false);
    setJump(null);
    jumped.current = false;
  }, [signature]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const cur = byId.get(current) ?? view.accounts[0];
  const others = slots.map((id) => byId.get(id)).filter((a): a is Account => a !== undefined);
  const history = useMemo(() => buildHistory(cur, home, hero.props), [cur, home, hero.props]);
  const days = useMemo(() => groupByDay(history.txns, home.as_of), [history, home.as_of]);

  const pick = (id: string, row: HTMLElement) => {
    if (jump || id === current) return;
    const phone = row.closest<HTMLElement>(".phone");
    if (!phone) return;
    jumped.current = true;
    setHidden(true);
    setSlots((s) => s.map((x) => (x === id ? current : x)));
    setJump({ id, rect: measure(phone, row), key: Date.now() });
  };

  const land = () => {
    if (!jump) return;
    setCurrent(jump.id);
    setHidden(false);
    setJump(null);
  };

  const spring = reduce ? { duration: 0 } : { type: "spring" as const, stiffness: 230, damping: 28, mass: 0.9 };
  const bounce = reduce ? { duration: 0 } : { type: "spring" as const, stiffness: 280, damping: 24, mass: 0.9 };
  const fade = (duration: number, delay = 0) => (reduce ? { duration: 0 } : { duration, delay });

  const from = {
    top: origin.y, left: origin.x, width: origin.w, height: origin.h,
    ...corners(origin.radius, origin.radius, origin.radius, origin.radius),
  };
  const to = {
    top: 0, left: 0, width: origin.stageW, height: tileH,
    ...corners(0, 0, TILE_RADIUS, TILE_RADIUS),
  };

  const jumpAccount = jump ? byId.get(jump.id) : undefined;
  const isMain = cur.id === mainId;

  return (
    <div
      className="zoom-layer"
      role="dialog"
      aria-label="Your accounts"
      onClickCapture={(e) => {
        if (masked && !(e.target as HTMLElement).closest("button, a, input")) onReveal();
      }}
    >
      <motion.div
        className="zb-scrim"
        onClick={onClose}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={fade(0.3)}
      />

      <motion.div
        className="zb-body"
        style={{ top: tileH - TILE_RADIUS }}
        initial={{ opacity: 0, y: 36 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 24, transition: fade(0.16) }}
        transition={reduce ? { duration: 0 } : { ...spring, delay: 0.14 }}
      >
        <h4>Other accounts</h4>
        {others.map((a, i) => (
          <motion.button
            key={a.id}
            type="button"
            className="zb-row"
            onClick={(e) => pick(a.id, e.currentTarget)}
            initial={jumped.current ? { opacity: 0, y: -26, scale: 0.97 } : { opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, transition: fade(0.1) }}
            transition={reduce ? { duration: 0 } : { ...spring, delay: jumped.current ? 0.3 : 0.24 + i * 0.07 }}
          >
            <RowBody account={a} />
          </motion.button>
        ))}
        {view.illustrative && <p className="zb-note">Demo accounts · synthetic data</p>}
      </motion.div>

      <motion.div
        className="zoom-box"
        initial={from}
        animate={to}
        exit={from}
        transition={spring}
      >
        <motion.div
          className="zb-tile"
          style={{ width: origin.w, height: origin.h }}
          initial={{ opacity: 1 }}
          animate={{ opacity: 0 }}
          exit={{ opacity: 1, transition: fade(0.16, 0.18) }}
          transition={fade(0.16)}
        >
          {tile}
        </motion.div>

        <motion.div
          className={`zb-acct ${isMain ? origin.variant : "hero"}`}
          initial={{ opacity: 0 }}
          animate={{ opacity: hidden ? 0 : 1 }}
          exit={{ opacity: 0, transition: fade(0.12) }}
          transition={hidden ? fade(0.14) : fade(0.24, jumped.current ? 0.02 : 0.14)}
        >
          <div className="zb-bar">
            <button type="button" className="zb-back" onClick={onClose} aria-label="Back to home" autoFocus>
              <ChevronLeft />
            </button>
            <span className="zb-title">Accounts</span>
            <span className="zb-count">{view.accounts.length} accounts · {eur(view.total_eur)}</span>
          </div>

          <h3>{cur.name}{isMain && <span className="zb-badge">Most used</span>}</h3>
          <div className="amount">{eur(cur.balance_eur)}</div>
          <div className="line">{maskIban(cur.last4)}</div>

          <div className="zb-scroll" key={cur.id}>
            <BalanceChart points={history.balances} />

            <div className="zb-stats">
              <div className="zb-stat in">
                <span>Money in · 30 days</span>
                <b>{eur(history.in_30d, { sign: true })}</b>
              </div>
              <div className="zb-stat">
                <span>Money out · 30 days</span>
                <b>{eur(-history.out_30d)}</b>
              </div>
            </div>

            <div className="zb-hist">
              <h5>History</h5>
              {days.length === 0 && <p className="zb-empty">No bookings yet.</p>}
              {days.map((g) => (
                <div key={g.date}>
                  <div className="zb-day">{g.label}</div>
                  {g.items.map((t) => {
                    const meta = txnMeta(t.category);
                    return (
                      <div key={t.id} className={`zb-txn ${t.amount_eur > 0 ? "in" : "out"}`}>
                        <span className="ti" aria-hidden="true">{meta.icon}</span>
                        <span className="tm">
                          <b>{t.counterparty}</b>
                          <small>{meta.label}</small>
                        </span>
                        <span className="ta">{eur(t.amount_eur, { sign: true })}</span>
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      </motion.div>

      {jump && jumpAccount && (
        <motion.div
          key={jump.key}
          className="zb-flyer"
          initial={{
            top: jump.rect.y, left: jump.rect.x, width: jump.rect.w, height: jump.rect.h,
            ...corners(jump.rect.radius, jump.rect.radius, jump.rect.radius, jump.rect.radius),
          }}
          animate={to}
          exit={{ opacity: 0 }}
          transition={bounce}
          onAnimationComplete={land}
        >
          <motion.div
            className="zb-flyer-blue"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={fade(0.22)}
          />
          <motion.div
            className="zb-row zb-flyer-row"
            style={{ width: jump.rect.w, height: jump.rect.h }}
            initial={{ opacity: 1 }}
            animate={{ opacity: 0 }}
            transition={fade(0.18)}
          >
            <RowBody account={jumpAccount} />
          </motion.div>
        </motion.div>
      )}
    </div>
  );
}
