import { AnimatePresence, LayoutGroup, MotionConfig, motion, type HTMLMotionProps } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AccountsZoom, { type ZoomOrigin } from "./accounts/AccountsZoom";
import { accountsFor } from "./accounts/accounts";
import { ChevronRight } from "./accounts/glyphs";
import type {
  Card, Component, Decision, HomeResponse, KateAction, KateReply, KateTurn, LayoutPrefState, Section, StylePrefs,
} from "./api";
import { NAV_ICONS } from "./components/icons";
import { resolve } from "./components/registry";
import type { SectionCtx } from "./components/types";
import { FEED_PERSONA_LABEL, longDate, PERSONA_LABEL, pct } from "./format";
import { PrivacyContext } from "./privacy";
import { greeting, themeVars } from "./theme";
import GallerySheet from "./ui/GallerySheet";
import KateSheet, { useKateChat } from "./ui/KateSheet";
import PersonaliseSheet from "./ui/PersonaliseSheet";
import SuggestionBanner from "./ui/SuggestionBanner";

interface Props {
  home: HomeResponse;
  asOf: string;
  explain: boolean;
  loading: boolean;
  toast: string | null;
  onFeedback: (card: Card, decision: Decision) => void;
  onCta: (action: string) => void;
  onLayoutPref: (component: Component, state: LayoutPrefState) => void;
  onPinAt: (component: Component, position: number | null) => void;
  onLayoutReset: () => void;
  onStyle: (style: StylePrefs) => void;
  onSuggestion: (component: Component, decision: "accept" | "dismiss") => void;
  onKate: (message: string, cardKey: string | null, history: KateTurn[]) => Promise<KateReply>;
  onKateAction: (action: KateAction) => Promise<boolean>;
}

type SheetKind = "gallery" | "style" | "kate" | null;

const REVEAL_MS = 8000;

/** Movable tiles: the non-hero sections after ForYouFeed. Their index is the `position` the backend expects. */
function movable(sections: Section[]): Component[] {
  const feed = sections.findIndex((s) => s.component === "ForYouFeed");
  return sections.filter((s, i) => i > feed && s.size !== "hero").map((s) => s.component);
}

function EditBar({ s, pos, count, onMove, onPin, onHide }: {
  s: Section; pos: number; count: number;
  onMove: (to: number) => void; onPin: () => void; onHide: () => void;
}) {
  const hero = s.size === "hero";
  return (
    <div className="edit-bar">
      {!hero && pos >= 0 && (
        <>
          <button type="button" aria-label="Move up" title="Move up" disabled={pos <= 0} onClick={() => onMove(pos - 1)}>↑</button>
          <button type="button" aria-label="Move down" title="Move down" disabled={pos >= count - 1} onClick={() => onMove(pos + 1)}>↓</button>
        </>
      )}
      {hero && <span className="edit-label">Main tile</span>}
      <span className="spacer" />
      <button type="button" className={s.pinned ? "on" : ""} aria-pressed={s.pinned} title={s.pinned ? "Unpin (let it adapt again)" : "Pin here"} onClick={onPin}>📌</button>
      <button type="button" aria-label="Hide" title="Hide this tile" onClick={onHide}>✕</button>
    </div>
  );
}

export default function Phone(p: Props) {
  const { home, asOf, explain, loading, toast } = p;
  const theme = home.layout.theme;
  const [editing, setEditing] = useState(false);
  const [sheet, setSheet] = useState<SheetKind>(null);
  const [revealed, setRevealed] = useState(false);
  const phoneRef = useRef<HTMLDivElement>(null);
  const masked = theme.privacy && !revealed;

  // Reveal masked amounts for a few seconds.
  useEffect(() => {
    if (!revealed) return;
    const t = window.setTimeout(() => setRevealed(false), REVEAL_MS);
    return () => window.clearTimeout(t);
  }, [revealed]);

  useEffect(() => {
    if (!sheet) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setSheet(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sheet]);

  const { onKate, onKateAction } = p;
  const execKate = useCallback(async (action: KateAction) => {
    if (action.kind === "open_card") {
      setSheet(null);
      const key = action.card_key;
      if (key) {
        window.setTimeout(() => {
          const el = phoneRef.current?.querySelector<HTMLElement>(`[data-card-key="${CSS.escape(key)}"]`);
          if (!el) return;
          el.scrollIntoView({ behavior: "smooth", block: "center" });
          el.classList.add("flash");
          window.setTimeout(() => el.classList.remove("flash"), 1800);
        }, 320);
      }
      return true;
    }
    return onKateAction(action);
  }, [onKateAction]);

  const chat = useKateChat(onKate, execKate, home.gallery);

  const openKate = useCallback((cardKey?: string | null, message?: string) => {
    setSheet("kate");
    chat.start(cardKey ?? null, message);
  }, [chat]);

  const ctx: SectionCtx = { home, asOf, explain, onFeedback: p.onFeedback, onCta: p.onCta, openKate };
  const mix = home.feed_personas?.length
    ? home.feed_personas.map((w) => `${pct(w.weight)} ${FEED_PERSONA_LABEL[w.code] ?? w.code}`).join(" · ")
    : home.persona_mix.map((w) => `${pct(w.weight)} ${PERSONA_LABEL[w.persona] ?? w.persona}`).join(" · ");
  const themeExplain = home.layout.explanations["theme"];
  const initials = home.customer.first_name.slice(0, 1).toUpperCase();
  const order = movable(home.layout.sections);
  const suggestion = home.suggestions[0];

  const revealOnTap = (e: React.MouseEvent) => {
    if (!masked) return;
    if ((e.target as HTMLElement).closest("button, a, input")) return;
    setRevealed(true);
  };

  // The hero tile opens the accounts screen with a zoom.
  const triggerRef = useRef<HTMLElement | null>(null);
  const restoreFocus = useRef(false);
  const [zoom, setZoom] = useState<ZoomOrigin | null>(null);
  const [tileHidden, setTileHidden] = useState(false);
  const heroSection = home.layout.sections.find((s) => s.size === "hero");
  const HeroC = heroSection ? resolve(heroSection.component) : null;
  const accounts = useMemo(() => accountsFor(home, heroSection), [home, heroSection]);

  // A different customer or hero means the tile we zoomed from is gone: close.
  const heroKey = `${home.customer.first_name}|${heroSection?.component ?? ""}`;
  useEffect(() => { setZoom(null); }, [heroKey]);

  // After the zoom closes, hand the keyboard focus back to the tile (it can only take focus once visible again).
  useEffect(() => {
    if (!tileHidden && restoreFocus.current) {
      restoreFocus.current = false;
      triggerRef.current?.focus({ preventScroll: true });
    }
  }, [tileHidden]);

  const openAccounts = (section: HTMLElement) => {
    const phone = phoneRef.current;
    const card = section.querySelector<HTMLElement>(".hero");
    if (!phone || !card || !accounts) return;
    const pr = phone.getBoundingClientRect();
    const k = pr.width / phone.offsetWidth || 1; // PhoneScaler shrinks the phone with a CSS transform
    const r = card.getBoundingClientRect();
    triggerRef.current = section;
    setZoom({
      x: (r.left - pr.left) / k,
      y: (r.top - pr.top) / k,
      w: r.width / k,
      h: r.height / k,
      radius: parseFloat(getComputedStyle(card).borderTopLeftRadius) || 20,
      variant: card.className,
      stageW: phone.offsetWidth,
      stageH: phone.offsetHeight,
    });
    setTileHidden(true);
  };

  const tileProps: HTMLMotionProps<"div"> = {
    role: "button",
    tabIndex: 0,
    "aria-label": "Show all accounts",
    onClick: (e) => openAccounts(e.currentTarget),
    onKeyDown: (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openAccounts(e.currentTarget); }
    },
  };

  return (
    <div className="phone-bezel">
      <MotionConfig reducedMotion={theme.reduce_motion ? "always" : "never"}>
        <PrivacyContext.Provider value={masked}>
          <div ref={phoneRef} className={`phone ${theme.appearance === "dark" ? "dark" : ""} ${theme.privacy ? "privacy" : ""}`} style={themeVars(theme)}>
            <div className="phone-top">
              <div className="greet">
                <div>
                  <h1>{greeting(theme.tone, home.customer.first_name)}</h1>
                  <div className="date">{longDate(home.as_of)}</div>
                </div>
                <div className="head-tools">
                  {theme.privacy && (
                    <button type="button" className="icon-btn" aria-label={masked ? "Show amounts" : "Hide amounts"} title={masked ? "Show amounts for a few seconds" : "Hide amounts"} onClick={() => setRevealed((v) => !v)}>
                      {masked ? <NAV_ICONS.eye /> : <NAV_ICONS.eyeOff />}
                    </button>
                  )}
                  <button type="button" className={`icon-btn ${editing ? "on" : ""}`} aria-label="Edit home" title="Edit home" onClick={() => setEditing((v) => !v)}>
                    <NAV_ICONS.edit />
                  </button>
                  <button type="button" className="avatar" aria-label="Personalise" title="Personalise" onClick={() => setSheet("style")}>{initials}</button>
                </div>
              </div>
              <AnimatePresence initial={false}>
                {editing && (
                  <motion.div className="edit-head" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}>
                    <span>Editing your home</span>
                    <button type="button" className="link" onClick={p.onLayoutReset}>Reset to adaptive</button>
                    <button type="button" className="btn-primary small" onClick={() => setEditing(false)}>Done</button>
                  </motion.div>
                )}
              </AnimatePresence>
              <AnimatePresence initial={false}>
                {explain && (
                  <motion.div
                    className="explain-head"
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                  >
                    <div><b>Composed for:</b> {mix}</div>
                    {themeExplain && <div>{themeExplain}</div>}
                    {theme.overrides.length > 0 && <div><b>You chose:</b> {theme.overrides.join(", ").replace(/_/g, " ")}</div>}
                    <div style={{ opacity: .8 }}>theme: {theme.density} · {theme.tone} · {theme.contrast} contrast · {theme.appearance}{theme.accent ? ` · ${theme.accent}` : ""}</div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {loading && <div className="phone-loading">updating…</div>}

            <div className="phone-scroll" onClickCapture={revealOnTap}>
              <AnimatePresence initial={false}>
                {suggestion && !editing && (
                  <SuggestionBanner key={suggestion.component} suggestion={suggestion} onDecide={p.onSuggestion} />
                )}
              </AnimatePresence>
              <LayoutGroup id="home-sections">
                <div className={`sections ${editing ? "editing" : ""}`}>
                  <AnimatePresence initial={false} mode="popLayout">
                    {home.layout.sections.map((s) => {
                      const C = resolve(s.component);
                      if (!C) return null;
                      const why = home.layout.explanations[s.component];
                      const pos = order.indexOf(s.component);
                      const tappable = s.size === "hero" && accounts !== null && !editing;
                      return (
                        <motion.div
                          key={s.component}
                          layout
                          layoutId={s.component}
                          className={`section s-${s.size} ${s.pinned ? "pinned" : ""}${tappable ? " tappable" : ""}${tappable && tileHidden ? " tile-hidden" : ""}`}
                          initial={{ opacity: 0, scale: 0.96, y: 14 }}
                          animate={{ opacity: 1, scale: 1, y: 0 }}
                          exit={{ opacity: 0, scale: 0.94, transition: { duration: 0.2 } }}
                          transition={{ type: "spring", stiffness: 300, damping: 30, mass: 0.9 }}
                          {...(tappable ? tileProps : {})}
                        >
                          {editing && s.component !== "ForYouFeed" && (
                            <EditBar
                              s={s}
                              pos={pos}
                              count={order.length}
                              onMove={(to) => p.onPinAt(s.component, to)}
                              onPin={() => (s.pinned ? p.onLayoutPref(s.component, "reset") : p.onPinAt(s.component, pos >= 0 ? pos : null))}
                              onHide={() => p.onLayoutPref(s.component, "hidden")}
                            />
                          )}
                          {s.pinned && !editing && <span className="pin-badge" title="Pinned by you" aria-label="Pinned">📌</span>}
                          <C props={s.props} ctx={ctx} />
                          {tappable && <span className="hero-chevron" aria-hidden="true"><ChevronRight /></span>}
                          {explain && (
                            <div className="explain-badge">
                              <span>{why ?? `${s.component}: no explanation provided.`}</span>
                              {s.component !== "ForYouFeed" && s.size !== "hero" && (
                                <span className="tools">
                                  <button type="button" title="Pin this section" onClick={() => p.onLayoutPref(s.component, "pinned")}>📌</button>
                                  <button type="button" title="Hide this section" onClick={() => p.onLayoutPref(s.component, "hidden")}>hide</button>
                                </span>
                              )}
                            </div>
                          )}
                        </motion.div>
                      );
                    })}
                  </AnimatePresence>
                </div>
              </LayoutGroup>
              <AnimatePresence>
                {editing && (
                  <motion.button
                    type="button"
                    className="add-tile"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 10 }}
                    onClick={() => setSheet("gallery")}
                  >
                    + Add tile
                  </motion.button>
                )}
              </AnimatePresence>
            </div>

            <AnimatePresence
              onExitComplete={() => {
                restoreFocus.current = true;
                setTileHidden(false);
              }}
            >
              {zoom && accounts && HeroC && heroSection && (
                <AccountsZoom
                  key="accounts"
                  origin={zoom}
                  view={accounts}
                  home={home}
                  hero={heroSection}
                  tile={<HeroC props={heroSection.props} ctx={ctx} />}
                  onClose={() => setZoom(null)}
                  onReveal={() => setRevealed(true)}
                />
              )}
            </AnimatePresence>

            <AnimatePresence>
              {toast && (
                <motion.div className="toast" key={toast} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 10 }}>
                  {toast}
                </motion.div>
              )}
            </AnimatePresence>

            <nav className="bottom-nav" aria-label="Main navigation">
              <button type="button" className={sheet !== "kate" ? "active" : ""} onClick={() => setSheet(null)}><NAV_ICONS.home />Home</button>
              <button type="button"><NAV_ICONS.pay />Pay</button>
              <button type="button" className={sheet === "kate" ? "active" : ""} onClick={() => openKate()}><NAV_ICONS.kate />Kate</button>
              <button type="button"><NAV_ICONS.cards />Cards</button>
              <button type="button"><NAV_ICONS.more />More</button>
            </nav>

            <AnimatePresence>
              {sheet === "gallery" && (
                <GallerySheet
                  key="gallery"
                  gallery={home.gallery}
                  onAdd={(c) => { p.onPinAt(c, null); setSheet(null); }}
                  onClose={() => setSheet(null)}
                />
              )}
              {sheet === "style" && <PersonaliseSheet key="style" home={home} onStyle={p.onStyle} onClose={() => setSheet(null)} />}
              {sheet === "kate" && <KateSheet key="kate" chat={chat} onClose={() => setSheet(null)} />}
            </AnimatePresence>
          </div>
        </PrivacyContext.Provider>
      </MotionConfig>
    </div>
  );
}
