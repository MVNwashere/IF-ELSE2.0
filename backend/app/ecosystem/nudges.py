"""Kate nudges: proactive messages that are useful and attentive, never spammy.

Sources (all read-only): the card generators (engine/cards.py), intent detection (intent.py), deadlines and
forecasts (signals.py) and the journey state (store.py). Every source proposes *candidates*; the policy below
decides which ones may interrupt the customer:

- Only money at stake, a deadline or something waiting on the customer. Never promos, price nudges or summaries.
- Urgent (possible scam / new payee, duplicate charge, balance going negative before income) always goes out.
- Everything else shares an attention budget: max 2 pushes per rolling 7 days (1 for retirees), never between
  21:00 and 08:00 (held until the 08:00 morning digest), and never on a day that already had an urgent alert.
  Several items in one slot are bundled into one digest push. What doesn't fit goes to Kate's inbox, silently.
- Each topic is sent once (dedupe key). "Mute" silences a topic for 90 days; two dismissals of a topic, or
  "show less" on the matching feed card, keep that topic in the inbox from then on.
- Intent candidates need confidence >= 0.75 (in-app needs 0.5) and are offered once, ever.

Everything is computed *as of* a date: `simulate()` replays the policy day by day, deterministically, so the demo's
time-travel slider can show exactly which nudges would have buzzed between two dates.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import logging
import re
import sqlite3
import threading
from dataclasses import dataclass, field, replace
from typing import Literal

from pydantic import BaseModel, Field

from .. import db
from ..engine import cards as C
from ..engine.features import fmt_date, fmt_eur
from ..schemas import Customer, DeclaredSignalRow, KateAction, Transaction
from . import signals, store
from .context import PROPERTY_SEARCH, TRAVEL_MERCHANTS, CustomerContext, build_context
from .intent import detect_with_suppressed
from .registry import registry
from .service import withheld_goals

log = logging.getLogger(__name__)

Tier = Literal["urgent", "deadline", "waiting", "moment"]
Channel = Literal["push", "digest", "inbox"]
AckAction = Literal["opened", "dismissed", "mute"]
NudgeStatus = Literal["new", "opened", "dismissed", "muted"]
OpenView = Literal["passport"]

NUDGE_KEY_PATTERN = r"^[a-z0-9_]{2,40}:[a-z0-9_:\-]{1,80}$"
TOPIC_PATTERN = re.compile(
    r"^(new_payee|duplicate_charge|runway|vat_return|advance_tax|insurance_renewal|pension_savings|trip|"
    r"journey_result|journey_waiting|consent_expiry|goal_done|intent_[a-z_]{2,40}|deadline_[a-z_]{2,30}|"
    r"forecast_[a-z_]{2,30})$")

# ---- policy knobs ---------------------------------------------------------------------------------------------------
BUDGET_WINDOW_DAYS = 7
BUDGET_DEFAULT = 2
BUDGET_RETIREE = 1
RETIREE_AGE = 65
QUIET_START, QUIET_END = 21, 8          # 21:00–08:00: non-urgent nudges wait for the morning
MORNING_HOUR = 8                        # the morning digest slot
DIGEST_MAX = 3
MUTE_DAYS = 90
LEARN_DISMISSALS = 2                    # two dismissals of a topic → inbox only from then on
LEARN_DAYS = 90
INTENT_PUSH_CONFIDENCE = 0.75           # the in-app threshold is intent.THRESHOLD (0.5)
WARMUP_DAYS = 21                        # replay this long before `since`: budget and dedupe state
MAX_WINDOW_DAYS = 92
DEADLINE_PUSH_DAYS = 14
INSURANCE_PUSH_DAYS = 21
PENSION_PUSH_DAYS = 30
FORECAST_PUSH_DAYS = 60
FORECAST_MIN_EUR = 500
RUNWAY_URGENT_DAYS = 3
RUNWAY_BEFORE_INCOME_DAYS = 10
TRIP_PUSH_CONFIDENCE = 0.7
NON_MUTABLE = {"new_payee"}             # security alerts can be dismissed, not silenced
TIER_ORDER = {"urgent": 0, "deadline": 1, "waiting": 2, "moment": 3}
LIFE_EVENT_GOALS = {"first_invoice": "go_freelance", "baby": "new_baby"}
DEADLINE_TOPICS = {"vat_return", "advance_tax", "insurance_renewal", "pension_savings", "trip"}
ALWAYS_PUSH_DEADLINES = {"pension_savings", "trip", "advance_tax"}   # insurance: only with a cheaper option (card)
MONEY_DEADLINES = {"vat_return", "advance_tax", "pension_savings", "social_contribution"}


# ---- API models -----------------------------------------------------------------------------------------------------


class Nudge(BaseModel):
    nudge_key: str = Field(pattern=NUDGE_KEY_PATTERN)
    topic: str
    tier: Tier
    title: str = Field(max_length=100)
    why: str = Field(max_length=260)            # "why now", with the evidence
    evidence: list[str] = Field(default_factory=list, max_length=3)
    action: KateAction                          # exactly one action
    open_view: OpenView | None = None           # an app view the action opens instead (frontend mapping)
    delivered_at: dt.datetime                   # simulated local time (quiet hours applied)
    channel: Channel                            # push = buzzed alone, digest = bundled, inbox = silent
    digest_id: str | None = None
    held_reason: str | None = None              # why it stayed in the inbox
    mutable: bool = True
    status: NudgeStatus = "new"
    source: str


class BudgetInfo(BaseModel):
    limit: int
    used: int                                   # non-urgent pushes in the 7 days up to as_of
    window_days: int = BUDGET_WINDOW_DAYS
    quiet_hours: str = f"{QUIET_START:02d}:00–{QUIET_END:02d}:00"
    persona: str


class NudgesResponse(BaseModel):
    as_of: dt.date
    since: dt.date
    nudges: list[Nudge]                         # chronological
    budget: BudgetInfo
    candidates: int                             # everything the sources proposed in the window
    held: int                                   # kept silent (inbox)


class AckRequest(BaseModel):
    action: AckAction


class AckResponse(BaseModel):
    nudge_key: str
    status: NudgeStatus
    muted_until: dt.date | None = None


class TierStats(BaseModel):
    tier: Tier
    candidates: int
    pushed: int
    held: int


class CustomerNudgeStats(BaseModel):
    label: str
    persona: str
    pushes: int
    urgent: int
    held: int
    max_non_urgent_7d: int
    budget: int


class NudgeStats(BaseModel):
    since: dt.date
    as_of: dt.date
    customers: int
    weeks: float
    pushes_per_customer_week: float
    non_urgent_per_customer_week: float
    max_non_urgent_any_7d: int                  # must stay <= the budget: the attention-budget KPI
    budget_default: int = BUDGET_DEFAULT
    budget_retiree: int = BUDGET_RETIREE
    candidates: int
    pushed_items: int
    held_items: int
    naive_pushes: int                           # baseline: one push per new feed card or goal suggestion
    pushes: int                                 # what the policy actually sent (a digest counts once)
    noise_avoided_pct: float                    # 1 - pushes / naive_pushes
    open_rate: float | None = None
    dismiss_rate: float | None = None
    mute_rate: float | None = None
    acks: int
    by_tier: list[TierStats]
    per_customer: list[CustomerNudgeStats]
    rules: list[str]


# ---- schema and ack storage ----------------------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS nudge_acks (
  id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  nudge_key TEXT NOT NULL,
  topic TEXT NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('opened','dismissed','mute')),
  at TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_nudge_acks_customer ON nudge_acks(customer_id);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


@dataclass
class Ack:
    nudge_key: str
    topic: str
    action: str
    at: dt.date


def acks(conn, customer_id: int) -> list[Ack]:
    rows = conn.execute("SELECT nudge_key, topic, action, at FROM nudge_acks WHERE customer_id = ? ORDER BY id",
                        (customer_id,)).fetchall()
    return [Ack(r["nudge_key"], r["topic"], r["action"], dt.date.fromisoformat(r["at"])) for r in rows]


def topic_of(nudge_key: str) -> str | None:
    topic = nudge_key.split(":", 1)[0]
    return topic if TOPIC_PATTERN.match(topic) else None


def record_ack(conn, customer_id: int, nudge_key: str, action: str, at: dt.date) -> AckResponse:
    topic = topic_of(nudge_key)
    if topic is None:
        raise ValueError("Unknown nudge topic")
    if action == "mute" and topic in NON_MUTABLE:
        action = "dismissed"      # a scam alert can't be silenced for 90 days
    conn.execute("INSERT INTO nudge_acks (customer_id, nudge_key, topic, action, at, created_at) "
                 "VALUES (?, ?, ?, ?, ?, ?)", (customer_id, nudge_key, topic, action, at.isoformat(), store.now()))
    status = {"opened": "opened", "dismissed": "dismissed", "mute": "muted"}[action]
    return AckResponse(nudge_key=nudge_key, status=status,
                       muted_until=at + dt.timedelta(days=MUTE_DAYS) if action == "mute" else None)


def reset_acks(conn, customer_id: int) -> None:
    conn.execute("DELETE FROM nudge_acks WHERE customer_id = ?", (customer_id,))


# ---- candidates -----------------------------------------------------------------------------------------------------


@dataclass
class Cand:
    key: str
    topic: str
    tier: str
    title: str
    why: str
    evidence: list[str]
    action: KateAction
    at: dt.datetime                     # when the signal arrived (deterministic, simulated time of day)
    source: str
    playbook_id: str | None = None
    skip_if_taken: bool = False         # an intent: not when the goal is already running or done
    card_type: str | None = None        # the feed card this mirrors ("show less" on it learns)
    mutable: bool = True
    open_view: str | None = None
    eur: float = 0.0


def _hash(key: str) -> int:
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)


def _at(day: dt.date, key: str, lo: int, hi: int) -> dt.datetime:
    """A deterministic time of day in [lo, hi) for a signal: the data is daily, the phone isn't."""
    h = _hash(key)
    return dt.datetime.combine(day, dt.time(lo + h % max(1, hi - lo), (h >> 8) % 60))


def _morning(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(MORNING_HOUR, 0))


def _clip(s: str, n: int) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", s.lower()).strip("_")[:30] or "x"


def _card_action(label: str, card) -> KateAction:
    return KateAction(kind="open_card", label=label, card_key=card.card_key, card_type=card.card_type)


def _goal_action(label: str, playbook_id: str) -> KateAction:
    return KateAction(kind="start_goal", label=label, playbook_id=playbook_id)


def _card_candidates(ctx: CustomerContext, detected: dict) -> list[Cand]:
    f, c, txs, day = ctx.features, ctx.customer, ctx.txs, ctx.as_of
    out: list[Cand] = []

    # urgent: a first, large payment to someone never paid before (not a booking we can explain)
    for card in C.gen_new_payee(f, c, txs, day):
        name = card.title.split(" to ", 1)[-1].split(". Was")[0]
        if card.stage != "urgent" or any(m in name.lower() for m in TRAVEL_MERCHANTS + PROPERTY_SEARCH):
            continue
        out.append(Cand(
            key=card.card_key, topic="new_payee", tier="urgent", source="card:new_payee",
            title=_clip(f"Was this you? {fmt_eur(card.eur_impact)} to {name}", 100),
            why=_clip(f"{card.evidence[0]}: a first payment to someone you've never paid. If anyone pushed you "
                      "to pay quickly, call KBC now.", 260),
            evidence=card.evidence[:3], action=_card_action("Check this payment", card),
            at=_at(day, card.card_key, 9, 19), card_type="new_payee", mutable=False, eur=card.eur_impact))

    # urgent: the same amount twice at the same shop within 48 h
    for card in C.gen_duplicate_charge(f, c, txs, day):
        out.append(Cand(
            key=card.card_key, topic="duplicate_charge", tier="urgent", source="card:duplicate_charge",
            title=_clip(card.title, 100),
            why=_clip(card.body.replace("we can help you", "KBC can help you"), 260),
            evidence=card.evidence[:3], action=_card_action("Review the charges", card),
            at=_at(day, card.card_key, 9, 19), card_type="duplicate_charge", eur=card.eur_impact))

    # urgent: the balance hits zero within days, or before the next income arrives
    for card in C.gen_runway(f, c, txs, day):
        runway = f.runway_days or 0
        zero = day + dt.timedelta(days=runway)
        before_income = f.next_income_date is None or f.next_income_date > zero
        if not (runway < RUNWAY_URGENT_DAYS or (runway <= RUNWAY_BEFORE_INCOME_DAYS and before_income)):
            continue
        key = f"runway:{day:%Y-%m}"
        out.append(Cand(
            key=key, topic="runway", tier="urgent", source="card:runway",
            title=_clip(f"Your balance may hit €0 by {fmt_date(zero)}", 100),
            why=_clip(f"{fmt_eur(f.balance_eur)} left and about {runway} days of spending at this pace"
                      + (", before your next income arrives." if before_income else "."), 260),
            evidence=card.evidence[:3], action=_card_action("Plan the month", card),
            at=_at(day, key, 9, 19), card_type="runway", eur=card.eur_impact))

    # deadline: VAT due soon and the money isn't there
    for card in C.gen_vat_reserve(f, c, txs, day):
        due = card.due_date
        days = (due - day).days if due else 99
        shortfall = card.eur_impact - max(0.0, f.balance_eur - f.monthly_spend_avg_90d)
        if not 0 <= days <= DEADLINE_PUSH_DAYS or shortfall <= 0:
            continue
        out.append(Cand(
            key=f"vat_return:{due:%Y-%m}", topic="vat_return", tier="deadline", source="card:vat_reserve",
            title=_clip(f"VAT due {fmt_date(due)}: about {fmt_eur(shortfall)} short", 100),
            why=_clip(f"Set aside about {fmt_eur(card.eur_impact)} for {card.details.get('quarter', 'this quarter')}"
                      f"; after a month of spending your account is about {fmt_eur(shortfall)} short.", 260),
            evidence=card.evidence[:3], action=_card_action("Set it aside", card),
            at=_morning(day), card_type="vat_reserve", eur=shortfall))

    # deadline: car insurance renews soon and comparable cover is cheaper
    for card in C.gen_insurance_renewal(f, c, txs, day):
        due = card.due_date
        if not due or not 0 <= (due - day).days <= INSURANCE_PUSH_DAYS:
            continue
        out.append(Cand(
            key=f"insurance_renewal:{due:%Y-%m}", topic="insurance_renewal", tier="deadline",
            source="card:insurance_renewal",
            title=_clip(f"Car insurance renews {fmt_date(due)}: about {fmt_eur(card.eur_impact)} a year to save", 100),
            why=_clip(f"{card.evidence[0]}. Compare before it renews; after that you're tied in for a year.", 260),
            evidence=card.evidence[:3], action=_card_action("Compare cover", card),
            at=_morning(day), card_type="insurance_renewal", eur=card.eur_impact))

    # deadline: pension savings deposit before 31 December
    for card in C.gen_pension_savings(f, c, txs, day):
        due = card.due_date
        if not due or not 0 <= (due - day).days <= PENSION_PUSH_DAYS:
            continue
        out.append(Cand(
            key=f"pension_savings:{due.year}", topic="pension_savings", tier="deadline",
            source="card:pension_savings",
            title=_clip(f"Up to {fmt_eur(card.eur_impact)} tax back if you deposit before {fmt_date(due)}", 100),
            why=_clip(f"{card.evidence[1]}. Deposits count for {due.year} until {fmt_date(due)}.", 260),
            evidence=card.evidence[:3], action=_card_action("See how it works", card),
            at=_morning(day), card_type="pension_savings", eur=card.eur_impact))

    # moment: a life event that opens a journey (THE hero: first invoice paid → go freelance)
    for card in C.gen_life_event(f, c, txs, day):
        etype = card.card_key.split(":", 1)[1].rsplit("-", 3)[0]
        pid = LIFE_EVENT_GOALS.get(etype)
        if not pid or pid not in detected:
            continue
        if etype == "first_invoice":
            first = next((t for t in txs if t.category == "invoice_income" and t.amount > 0), None)
            title = "Your first invoice is paid 🎉"
            why = (f"{fmt_eur(first.amount)} from {C._name(first.counterparty)} on {fmt_date(first.date)}. "
                   if first else "") + "Want KBC to set up everything a freelancer needs?"
        else:
            title, why = card.title, f"{card.evidence[0]}. {detected[pid][2]}"
        out.append(Cand(
            key=f"intent_{pid}:once", topic=f"intent_{pid}", tier="moment", source=f"life_event:{etype}",
            title=_clip(title, 100), why=_clip(why, 260), evidence=detected[pid][1][:3],
            action=_goal_action("Set it up for me", pid), at=_at(day, card.card_key, 9, 19), playbook_id=pid,
            skip_if_taken=True))
    return out


def _playbook(pid: str):
    try:
        return registry().playbooks.get(pid)
    except Exception:  # noqa: BLE001 - the registry belongs to another module; never break nudges over it
        log.exception("registry unavailable")
        return None


def _intent_candidates(ctx: CustomerContext, detected: dict) -> list[Cand]:
    out = []
    for pid, (conf, ev, why) in detected.items():
        if conf < INTENT_PUSH_CONFIDENCE:
            continue
        pb = _playbook(pid)
        key = f"intent_{pid}:once"
        out.append(Cand(
            key=key, topic=f"intent_{pid}", tier="moment", source="intent",
            title=_clip(f"{pb.icon} {pb.title}?" if pb else pid.replace("_", " ").capitalize() + "?", 100),
            why=_clip((f"{ev[0]}. " if ev else "") + why, 260), evidence=ev[:3],
            action=_goal_action("Show me the plan", pid), at=_at(ctx.as_of, key, 9, 19), playbook_id=pid,
            skip_if_taken=True))
    return out


def _signal_candidates(ctx: CustomerContext) -> list[Cand]:
    """Deadlines and forecasts from signals.py (another module; any failure there must not break nudges)."""
    out: list[Cand] = []
    day = ctx.as_of
    try:
        deadlines = list(signals.upcoming_deadlines(ctx, 45) or [])
    except Exception:  # noqa: BLE001
        log.exception("signals.upcoming_deadlines failed")
        deadlines = []
    try:
        fcs = list(signals.forecasts(ctx) or [])
    except Exception:  # noqa: BLE001
        log.exception("signals.forecasts failed")
        fcs = []
    for d in deadlines:
        kind = "vat_return" if d.kind == "vat" else _slug(d.kind)
        topic = kind if kind in DEADLINE_TOPICS else f"deadline_{kind}"
        days = (d.date - day).days
        limit = PENSION_PUSH_DAYS if kind == "pension_savings" else (
            INSURANCE_PUSH_DAYS if kind == "insurance_renewal" else DEADLINE_PUSH_DAYS)
        short = d.shortfall_eur or 0.0
        if not 0 <= days <= limit or not (short > 0 or kind in ALWAYS_PUSH_DEADLINES):
            continue
        key = f"{topic}:{d.date:%Y-%m}"
        money = f": about {fmt_eur(short)} short" if short > 0 else ""
        when = "" if fmt_date(d.date) in d.title else f", {fmt_date(d.date)}"
        why = (d.evidence[0] + ". ") if d.evidence else ""
        if kind in MONEY_DEADLINES and d.amount_eur:
            why += f"About {fmt_eur(d.amount_eur)} due {fmt_date(d.date)}."
        elif kind == "trip":
            why += (d.evidence[1] + ". " if len(d.evidence) > 1 else "") +                 "No travel insurance yet: sorted in one go, before you leave."
        elif len(d.evidence) > 1:
            why += d.evidence[1] + "."
        action = (_goal_action("Let KBC handle it", d.playbook_id) if d.playbook_id
                  else KateAction(kind="open_card", label="Show me"))
        out.append(Cand(
            key=key, topic=topic, tier="deadline", source=f"signals:{kind}",
            title=_clip(f"{d.title}{when}{money}", 100), why=_clip(why, 260),
            evidence=list(d.evidence)[:3], action=action, at=_morning(day), playbook_id=d.playbook_id,
            skip_if_taken=kind == "trip", eur=short or (d.amount_eur or 0.0)))
    for fc in fcs:
        # undated insights (client concentration, ...) stay in the app: a push needs a date and money at stake
        if (fc.amount_eur or 0) < FORECAST_MIN_EUR or not fc.due or not 0 <= (fc.due - day).days <= FORECAST_PUSH_DAYS:
            continue
        kind = _slug(fc.kind)
        key = f"forecast_{kind}:{fc.due:%Y-%m}"
        why = (fc.evidence[0] + ". ") if fc.evidence else ""
        why += f"KBC expects about {fmt_eur(fc.amount_eur or 0)} by {fmt_date(fc.due)}."
        action = (_goal_action("Plan for it", fc.playbook_id) if fc.playbook_id
                  else KateAction(kind="open_card", label="Show me"))
        out.append(Cand(
            key=key, topic=f"forecast_{kind}", tier="deadline", source=f"forecast:{kind}",
            title=_clip(fc.title, 100), why=_clip(why, 260), evidence=list(fc.evidence)[:3], action=action,
            at=_morning(day), playbook_id=fc.playbook_id, eur=fc.amount_eur or 0.0))
    return out


_cache: dict[tuple, tuple[list[Cand], frozenset[str]]] = {}
_cache_lock = threading.Lock()
CACHE_MAX = 20_000


def day_candidates(customer: Customer, txs: list[Transaction], balance: float, day: dt.date,
                   declared: list[DeclaredSignalRow]) -> list[Cand]:
    return _day(customer, txs, balance, day, declared)[0]


def naive_keys(customer: Customer, txs: list[Transaction], balance: float, day: dt.date,
               declared: list[DeclaredSignalRow]) -> frozenset[str]:
    """What a naive "push every new card and suggestion" system would send: the baseline for the KPI."""
    return _day(customer, txs, balance, day, declared)[1]


def _day(customer: Customer, txs: list[Transaction], balance: float, day: dt.date,
         declared: list[DeclaredSignalRow]) -> tuple[list[Cand], frozenset[str]]:
    """Everything the customer's own data proposes on `day`. Pure, so cached per (customer, day, data)."""
    decl = [d for d in declared if d.created_at <= day]
    key = (customer.id, day, len(txs), round(balance, 2), tuple((d.signal, d.created_at) for d in decl))
    with _cache_lock:
        hit = _cache.get(key)
    if hit is not None:
        return hit
    ctx = build_context(customer, txs, balance, day)
    kept, suppressed = detect_with_suppressed(ctx, decl)
    detected = dict(kept)
    out = _card_candidates(ctx, detected) + _intent_candidates(ctx, detected) + _signal_candidates(ctx)
    # same rule as the journeys: in hard times nothing pushes a commercial goal (urgent alerts still go through)
    held = {pid for pid, _ in suppressed}
    out = [c for c in out if c.tier == "urgent" or c.playbook_id not in held]
    # one candidate per key per day (a card and a signal may describe the same deadline: keep the first, the card
    # is evaluated first only when signals gave nothing)
    seen: dict[str, Cand] = {}
    for cnd in sorted(out, key=lambda x: 0 if x.source.startswith("signals") else 1):
        seen.setdefault(cnd.key, cnd)
    by_topic: dict[str, Cand] = {}
    for cnd in seen.values():
        if cnd.topic in DEADLINE_TOPICS and cnd.topic in by_topic:
            continue
        by_topic.setdefault(cnd.topic if cnd.topic in DEADLINE_TOPICS else cnd.key, cnd)
    raw = frozenset([c.card_key for c in C.generate_cards(ctx.features, customer, ctx.txs, day)]
                    + [f"intent_{pid}:once" for pid in detected])
    result = (list(by_topic.values()), raw)
    with _cache_lock:
        if len(_cache) > CACHE_MAX:
            _cache.clear()
        _cache[key] = result
    return result


def journey_candidates(conn, customer_id: int) -> list[Cand]:
    try:
        return _journey_candidates(conn, customer_id)
    except Exception:  # noqa: BLE001 - journey state is read from the CORE engine; degrade to data-only nudges
        log.exception("journey nudges unavailable")
        return []


def _journey_candidates(conn, customer_id: int) -> list[Cand]:
    """Partner results, steps waiting on the customer, consents about to expire, goals completed.

    Dated in as-of time: a partner step on the date the customer granted access (the simulated partner answers
    within the demo), a goal's completion on its last grant."""
    from . import service   # late import: service is the CORE engine; read-only use

    out: list[Cand] = []
    reg = registry()
    grants = store.grants(conn, customer_id)
    for row in store.goals(conn, customer_id):
        if row["status"] == "cancelled":
            continue                       # stopped by the customer
        g = service.goal_model(conn, row)
        if g.paused:
            continue                       # paused by the customer: no journey nudges until they pick it up again
        mine = [r for r in grants if r["goal_id"] == g.goal_id]
        by_step = {r["step_id"]: r for r in mine}
        last = max([dt.date.fromisoformat(r["granted_on"]) for r in mine] + [g.created_on])
        for s in g.steps:
            gr = by_step.get(s.step_id)
            # a completed goal gets one "done" moment instead of one nudge per partner result
            if g.status == "active" and s.status == "done" and s.provider.kind == "partner" and not s.already_held and gr:
                key = f"journey_result:{g.goal_id}-{s.step_id}"
                out.append(Cand(
                    key=key, topic="journey_result", tier="waiting", source="journey:webhook",
                    title=_clip(f"{s.provider.name} is done: {s.title}", 100),
                    why=_clip(s.result or "The result is in your journey.", 260), evidence=[],
                    action=KateAction(kind="open_goal", label="See the result", goal_id=g.goal_id,
                                      playbook_id=g.playbook_id),
                    at=_at(dt.date.fromisoformat(gr["granted_on"]), key, 0, 24)))
        waiting = next((s for s in g.steps if s.status == "proposed"), None)
        if g.status == "active" and waiting:
            key = f"journey_waiting:{g.goal_id}"
            out.append(Cand(
                key=key, topic="journey_waiting", tier="waiting", source="journey:waiting",
                title=_clip(f"{g.title}: a step is waiting for you", 100),
                why=_clip(f"“{waiting.title}” has waited since {fmt_date(g.created_on)}. Approve or skip it; "
                          "KBC does the rest.", 260), evidence=[],
                action=KateAction(kind="open_goal", label="Open my plan", goal_id=g.goal_id,
                                  playbook_id=g.playbook_id),
                at=_at(g.created_on + dt.timedelta(days=8), key, 9, 19)))
        for gr in mine:
            if gr["status"] != "active":
                continue
            expires = dt.date.fromisoformat(gr["expires_on"])
            key = f"consent_expiry:{gr['id']}"
            partner = reg.partners[gr["partner_id"]].name if gr["partner_id"] in reg.partners else "A partner"
            out.append(Cand(
                key=key, topic="consent_expiry", tier="waiting", source="journey:consent",
                title=_clip(f"{partner}'s access to your data ends {fmt_date(expires)}", 100),
                why=_clip(f"You shared data for “{gr['purpose']}”. Nothing to do if the work is finished; "
                          "renew it if it isn't.", 260), evidence=[],
                action=KateAction(kind="open_goal", label="Review access", goal_id=g.goal_id,
                                  playbook_id=g.playbook_id),
                open_view="passport", at=_at(expires - dt.timedelta(days=3), key, 9, 19)))
        if g.status == "completed":
            o = g.outcome
            bits = [f"{fmt_eur(o.customer_eur)} for you"] if o.customer_eur else []
            if o.hours_saved:
                bits.append(f"{o.hours_saved:g} hours of admin saved")
            key = f"goal_done:{g.goal_id}"
            out.append(Cand(
                key=key, topic="goal_done", tier="moment", source="journey:completed",
                title=_clip(f"{g.icon} Done: {g.title}", 100),
                why=_clip(("Outcome: " + ", ".join(bits) + ".") if bits else "Every step is done.", 260),
                evidence=[], action=KateAction(kind="open_goal", label="See the outcome", goal_id=g.goal_id,
                                               playbook_id=g.playbook_id),
                at=_at(last, key, 9, 19), eur=o.customer_eur))
    return out


# ---- the policy -----------------------------------------------------------------------------------------------------


@dataclass
class Delivery:
    cand: Cand
    at: dt.datetime
    channel: str
    digest_id: str | None = None
    held_reason: str | None = None


@dataclass
class SimResult:
    deliveries: list[Delivery] = field(default_factory=list)   # pushed, digested or held, all dates
    candidates: list[tuple[dt.date, Cand, str]] = field(default_factory=list)   # (day, cand, outcome)
    budget: int = BUDGET_DEFAULT
    persona: str = "default"
    pushes: list[dt.datetime] = field(default_factory=list)     # non-urgent push slots (a digest counts once)
    naive: list[dt.date] = field(default_factory=list)          # baseline: one push per new card/suggestion


def _deliver_at(c: Cand) -> dt.datetime:
    if c.tier == "urgent":
        return c.at
    h = c.at.hour
    if h >= QUIET_START:
        return _morning(c.at.date() + dt.timedelta(days=1))
    if h < QUIET_END:
        return _morning(c.at.date())
    return c.at


def _muted(c: Cand, day: dt.date, ack_list: list[Ack]) -> bool:
    """Muting one nudge silences the rest of its topic for 90 days (the muted nudge itself stays, as muted)."""
    return any(a.action == "mute" and a.topic == c.topic and a.nudge_key != c.key
               and a.at <= day <= a.at + dt.timedelta(days=MUTE_DAYS) for a in ack_list)


def _learned(c: Cand, day: dt.date, ack_list: list[Ack], less: dict[str, dt.date]) -> str | None:
    lo = day - dt.timedelta(days=LEARN_DAYS)
    n = len({a.nudge_key for a in ack_list if a.action == "dismissed" and a.topic == c.topic
             and a.nudge_key != c.key and lo <= a.at <= day})
    if n >= LEARN_DISMISSALS:
        return "You dismissed the last ones like this, so Kate keeps it in your inbox"
    if c.card_type and c.card_type in less and less[c.card_type] <= day:
        return "You asked to see less of these"
    return None


def simulate(conn, customer_id: int, since: dt.date, as_of: dt.date, warmup_days: int = WARMUP_DAYS) -> SimResult:
    customer = db.get_customer(conn, customer_id)
    if not customer:
        return SimResult()
    txs = db.get_transactions(conn, customer_id)
    balance = db.get_balance_today(conn, customer_id)
    prefs = db.get_prefs(conn, customer_id)
    ack_list = acks(conn, customer_id)
    less = {}
    for fb in prefs.feedback:
        if fb.decision == "less":
            less.setdefault(fb.card_type, fb.created_at)
    journey = journey_candidates(conn, customer_id)
    withheld = withheld_goals(prefs)
    goal_rows = [r for r in store.goals(conn, customer_id) if r["status"] != "cancelled"]

    start = since - dt.timedelta(days=warmup_days)
    res = SimResult()
    consumed: set[str] = set()                        # each key once (acks only change its status)
    for c in day_candidates(customer, txs, balance, start, prefs.declared):
        consumed.add(c.key)                            # conditions that already held before: not news
    consumed |= {j.key for j in journey if j.at.date() <= start}
    naive_seen = set(naive_keys(customer, txs, balance, start, prefs.declared))
    pending: list[tuple[dt.datetime, Cand]] = []
    urgent_days: set[dt.date] = set()

    day = start + dt.timedelta(days=1)
    while day <= as_of:
        age = day.year - customer.birth_year
        retiree = age >= RETIREE_AGE
        res.budget = BUDGET_RETIREE if retiree else BUDGET_DEFAULT
        res.persona = "retiree" if retiree else "default"
        goals_now = [r for r in goal_rows if dt.date.fromisoformat(r["created_on"]) <= day]
        # goals started before today: the suggestion is old news (started today: the nudge is likely why)
        taken = {r["playbook_id"] for r in goals_now if dt.date.fromisoformat(r["created_on"]) < day}
        active = {r["playbook_id"]: r["id"] for r in goals_now if r["status"] == "active"}
        todays = day_candidates(customer, txs, balance, day, prefs.declared) + \
            [j for j in journey if j.at.date() == day]
        for k in naive_keys(customer, txs, balance, day, prefs.declared) - naive_seen:
            naive_seen.add(k)
            res.naive.append(day)
        for c in todays:
            if c.key in consumed:
                continue
            consumed.add(c.key)
            if c.skip_if_taken and c.playbook_id in taken:
                continue
            if c.source == "intent" and (withheld is None or c.playbook_id in withheld):
                continue                               # the customer's profile says: don't suggest this
            if c.action.kind == "start_goal" and c.action.playbook_id in active:
                c = replace(c, action=KateAction(kind="open_goal", label="Open my plan",
                                                 goal_id=active[c.action.playbook_id],
                                                 playbook_id=c.action.playbook_id))
            pending.append((_deliver_at(c), c))

        due_today = sorted([(t, c) for t, c in pending if t.date() == day], key=lambda x: x[0])
        pending = [(t, c) for t, c in pending if t.date() != day]
        slots: dict[dt.datetime, list[Cand]] = {}
        for t, c in due_today:
            slots.setdefault(t, []).append(c)
        for t in sorted(slots):
            _process_slot(res, t, slots[t], ack_list, less, urgent_days)
        day += dt.timedelta(days=1)
    return res


def _process_slot(res: SimResult, t: dt.datetime, cands: list[Cand], ack_list: list[Ack],
                  less: dict[str, dt.date], urgent_days: set[dt.date]) -> None:
    day = t.date()
    eligible: list[Cand] = []
    for c in sorted(cands, key=lambda x: (TIER_ORDER[x.tier], -x.eur, x.key)):
        if c.mutable and _muted(c, day, ack_list):
            res.candidates.append((day, c, "muted"))
            continue
        if c.tier == "urgent":
            res.deliveries.append(Delivery(c, t, "push"))
            res.candidates.append((day, c, "push"))
            urgent_days.add(day)
            continue
        reason = _learned(c, day, ack_list, less)
        if reason is None and day in urgent_days:
            reason = "Kept quiet: you already had an urgent alert today"
        if reason:
            res.deliveries.append(Delivery(c, t, "inbox", held_reason=reason))
            res.candidates.append((day, c, "inbox"))
            continue
        eligible.append(c)
    if not eligible:
        return
    used = sum(1 for p in res.pushes if t - dt.timedelta(days=BUDGET_WINDOW_DAYS) < p <= t)
    if used >= res.budget:
        n = res.budget
        reason = f"Attention budget: {n} nudge{'s' if n != 1 else ''} a week, already used"
        for c in eligible:
            res.deliveries.append(Delivery(c, t, "inbox", held_reason=reason))
            res.candidates.append((day, c, "inbox"))
        return
    res.pushes.append(t)
    if len(eligible) == 1:
        res.deliveries.append(Delivery(eligible[0], t, "push"))
        res.candidates.append((day, eligible[0], "push"))
        return
    digest_id = t.strftime("digest-%Y%m%d%H%M")
    for i, c in enumerate(eligible):
        if i < DIGEST_MAX:
            res.deliveries.append(Delivery(c, t, "digest", digest_id=digest_id))
            res.candidates.append((day, c, "digest"))
        else:
            res.deliveries.append(Delivery(c, t, "inbox", held_reason="More than a digest can hold"))
            res.candidates.append((day, c, "inbox"))


def _status(key: str, ack_list: list[Ack]) -> str:
    st = "new"
    for a in ack_list:
        if a.nudge_key == key:
            st = {"opened": "opened", "dismissed": "dismissed", "mute": "muted"}[a.action]
    return st


def nudges_for(conn, customer_id: int, since: dt.date, as_of: dt.date) -> NudgesResponse:
    res = simulate(conn, customer_id, since, as_of)
    ack_list = acks(conn, customer_id)
    lo = dt.datetime.combine(since + dt.timedelta(days=1), dt.time(0, 0))
    out = []
    for d in res.deliveries:
        if d.at < lo:
            continue
        c = d.cand
        out.append(Nudge(
            nudge_key=c.key, topic=c.topic, tier=c.tier, title=c.title, why=c.why, evidence=c.evidence[:3],
            action=c.action, open_view=c.open_view, delivered_at=d.at, channel=d.channel, digest_id=d.digest_id,
            held_reason=d.held_reason, mutable=c.mutable and c.topic not in NON_MUTABLE,
            status=_status(c.key, ack_list), source=c.source))
    out.sort(key=lambda n: (n.delivered_at, TIER_ORDER[n.tier]))
    in_window = [x for x in res.candidates if x[0] > since]
    week_lo = dt.datetime.combine(as_of, dt.time(23, 59)) - dt.timedelta(days=BUDGET_WINDOW_DAYS)
    return NudgesResponse(
        as_of=as_of, since=since, nudges=out,
        budget=BudgetInfo(limit=res.budget, used=sum(1 for p in res.pushes if p > week_lo), persona=res.persona),
        candidates=len(in_window), held=sum(1 for x in in_window if x[2] in ("inbox", "muted")))


# ---- the attention-budget KPI ---------------------------------------------------------------------------------------

_stats_cache: dict[tuple, NudgeStats] = {}


DEMO_USERS = ("lotte", "sara", "jan", "marc")
SAMPLE_SIZE = 16


def sample_customer_ids(conn, size: int = SAMPLE_SIZE) -> list[int]:
    """The demo customers plus the first synthetic customers, up to `size` (a sample keeps the console fast)."""
    ids = []
    for u in DEMO_USERS:
        row = db.get_user(conn, u)
        if row and row["customer_id"] is not None:
            ids.append(row["customer_id"])
    ids += [i for i in db.all_customer_ids(conn) if i not in ids][: max(0, size - len(ids))]
    return ids


def stats(conn, as_of: dt.date, weeks: int = 4) -> NudgeStats:
    ids = sample_customer_ids(conn)
    n_acks = conn.execute("SELECT COUNT(*) AS n FROM nudge_acks").fetchone()["n"]
    goals_n = conn.execute("SELECT COUNT(*) AS n FROM eco_goals").fetchone()["n"]
    ck = (tuple(ids), as_of, weeks, n_acks, goals_n)
    if ck in _stats_cache:
        return _stats_cache[ck]
    since = as_of - dt.timedelta(days=7 * weeks)
    tiers = {t: {"candidates": 0, "pushed": 0, "held": 0} for t in TIER_ORDER}
    per: list[CustomerNudgeStats] = []
    total_pushes = non_urgent = cands = pushed_items = held_items = naive = 0
    max7 = 0
    delivered_keys: set[tuple[int, str]] = set()
    for cid in ids:
        customer = db.get_customer(conn, cid)
        if not customer:
            continue
        res = simulate(conn, cid, since, as_of, warmup_days=7)
        win = [x for x in res.candidates if x[0] > since]
        lo = dt.datetime.combine(since + dt.timedelta(days=1), dt.time(0, 0))
        pushes = [p for p in res.pushes if p >= lo]
        urgent = sum(1 for _, c, o in win if c.tier == "urgent" and o == "push")
        worst = max((sum(1 for q in res.pushes if p - dt.timedelta(days=BUDGET_WINDOW_DAYS) < q <= p)
                     for p in pushes), default=0)
        max7 = max(max7, worst)
        held = sum(1 for _, _, o in win if o in ("inbox", "muted"))
        for _, c, o in win:
            tiers[c.tier]["candidates"] += 1
            if o in ("push", "digest"):
                tiers[c.tier]["pushed"] += 1
                delivered_keys.add((cid, c.key))
            else:
                tiers[c.tier]["held"] += 1
        total_pushes += len(pushes) + urgent
        non_urgent += len(pushes)
        cands += len(win)
        naive += sum(1 for d in res.naive if d > since)
        pushed_items += sum(1 for _, _, o in win if o in ("push", "digest"))
        held_items += held
        per.append(CustomerNudgeStats(label=customer.first_name, persona=res.persona, pushes=len(pushes) + urgent,
                                      urgent=urgent, held=held, max_non_urgent_7d=worst, budget=res.budget))
    rows = conn.execute("SELECT customer_id, nudge_key, action FROM nudge_acks").fetchall()
    acted = {(r["customer_id"], r["nudge_key"]): r["action"] for r in rows}
    mine = {k: v for k, v in acted.items() if k in delivered_keys}
    denom = len(delivered_keys)

    def rate(action: str) -> float | None:
        return round(sum(1 for v in mine.values() if v == action) / denom, 3) if denom else None

    n = max(1, len(per))
    out = NudgeStats(
        since=since, as_of=as_of, customers=len(per), weeks=weeks,
        pushes_per_customer_week=round(total_pushes / n / weeks, 2),
        non_urgent_per_customer_week=round(non_urgent / n / weeks, 2), max_non_urgent_any_7d=max7,
        candidates=cands, pushed_items=pushed_items, held_items=held_items,
        naive_pushes=naive, pushes=total_pushes,
        noise_avoided_pct=round(100 * max(0, naive - total_pushes) / naive, 1) if naive else 0.0,
        open_rate=rate("opened"), dismiss_rate=rate("dismissed"), mute_rate=rate("mute"), acks=len(rows),
        by_tier=[TierStats(tier=t, **v) for t, v in tiers.items()], per_customer=per,
        rules=[
            f"Max {BUDGET_DEFAULT} non-urgent nudges per rolling 7 days ({BUDGET_RETIREE} for retirees)",
            f"Quiet hours {QUIET_START:02d}:00–{QUIET_END:02d}:00: non-urgent nudges wait for the morning digest",
            "Urgent (new payee, duplicate charge, balance below zero before income) bypasses the budget",
            f"Each topic once; mute = {MUTE_DAYS} days of silence; {LEARN_DISMISSALS} dismissals = inbox only",
            f"Goal suggestions only at confidence >= {INTENT_PUSH_CONFIDENCE} and only once, ever",
            "Never pushed: price changes, spending summaries, product promos",
        ],
    )
    if len(_stats_cache) > 32:
        _stats_cache.clear()
    _stats_cache[ck] = out
    return out
