"""The ecosystem engine: intent → goal → journey → consent → provider → outcome.

Step state machine:  proposed ─approve─► in_progress ─partner webhook─► done
                         │                    │  (KBC steps complete immediately)
                         └─decline─► declined └─grant revoked─► blocked ─approve─► in_progress
                                              └─partner rejects / misses its SLA─► blocked + fallback partner
Every transition is caused by the customer (approve/decline/revoke), by a verified partner event, or by a partner
missing its SLA. A fallback partner never receives data until the customer approves again (a fresh grant).

Households: the owner can share a goal with a household member. On a shared goal a step that sends data to a
partner needs every member's approval first; either member can revoke.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import secrets
import time
from dataclasses import dataclass

from .. import db
from ..profile.fields import held_back_playbooks
from ..schemas import DeclaredSignalRow, Prefs
from . import outcomes, sources, store
from .context import CustomerContext, apply_sources, build_context
from .intent import detect
from .models import (
    ConsentGrant, ConsentsResponse, DataField, EcosystemOverview, EventRow, FallbackOffer, FeeDisclosure, FunnelRow,
    Goal, GoalCandidate, GoalsResponse, HouseholdInvite, HouseholdMember, LearningRow, ManifestResult,
    OutcomeSummary, Partner, PartnerManifest, PartnerOption, PartnerRow, PartnerWebhook, PlaybookSummary, Progress,
    ProductRef, RuleRow, SigningSetup, StallPrompt, Step, WinTotals,
)
from .registry import Playbook, PlaybookStep, partner_problems, registry
from .webhooks import (
    WebhookError, behaviour_of, secret_of, set_behaviour, simulate_deletion, simulate_partner, verify,
)

PORTFOLIO_SIZE = 2_300_000
ADOPTION = 0.15            # assumed share of customers with a detected goal who start the journey
DEMO_TODAY = dt.date.fromisoformat(os.environ.get("DEMO_TODAY", "2026-10-20"))
OPEN = ("proposed", "approved", "in_progress", "blocked")
DEMOTE_AFTER = 2           # SLA misses before a partner is ranked below the partners that do answer
STALL_DAYS = 30            # no progress for a month: one gentle "still want this?"
STALL_SHOW_DAYS = 14       # the prompt stays two weeks if unanswered, then never again
# Goals a household can share. Separation is deliberately not shareable: its data never goes to the other person.
JOINT_PLAYBOOKS = ("buy_home", "new_baby", "together", "energy_upgrade", "move_house")


def _col(row, name: str):
    """A column added by a migration (None on rows from joins that don't select it)."""
    return row[name] if row is not None and name in row.keys() else None


def _tried(row) -> list[str]:
    return json.loads(_col(row, "tried_partners") or "[]")


def _fallback(row) -> FallbackOffer | None:
    raw = _col(row, "fallback")
    return FallbackOffer.model_validate(json.loads(raw)) if raw else None


class EcosystemError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass
class PendingSimulation:
    """A partner call to fire after the transaction commits (the simulated partner calls back over HTTP-like
    signed webhooks, which need their own transaction)."""
    partner_id: str
    ref: str
    result: str
    kind: str = "done"        # "done": the partner finishes the step; "deleted": it confirms data deletion


def effective_step(s: PlaybookStep, row) -> PlaybookStep:
    """The step as routed for this customer: the partner they picked among the alternatives, if any."""
    chosen = row["partner_id"] if row is not None and "partner_id" in row.keys() else None
    if chosen and chosen != s.provider and chosen in registry().partners:
        return s.model_copy(update={"provider": chosen})
    return s


def fee_disclosure(partner: Partner) -> FeeDisclosure:
    """Fee transparency in plain words: what KBC earns if the customer goes ahead."""
    v = partner.value_share
    if partner.kind != "partner":
        return FeeDisclosure(model=None, kbc_earns="KBC's own service: no partner fee involved.",
                             you_pay_extra="")
    if v.amount_eur == 0 and v.pct == 0:
        note = f" {v.note.rstrip('.')}." if v.note else ""
        return FeeDisclosure(model=v.model, kbc_earns=f"KBC earns nothing from {partner.name} for this step.{note}")
    if v.model == "revenue_share":
        what = f"{round(v.pct * 100, 1):g}% ({v.note})" if v.pct else "nothing extra"
        text = f"KBC earns {what} from {partner.name} if you go ahead."
    elif v.model == "subscription":
        text = f"KBC earns €{v.amount_eur:g} a month from {partner.name} while you use it."
    elif v.model == "lead_fee":
        text = f"KBC earns €{v.amount_eur:g} from {partner.name} if you go ahead."
    else:
        text = f"KBC earns €{v.amount_eur:g} from {partner.name} when this step is completed."
    return FeeDisclosure(model=v.model, amount_eur=v.amount_eur, pct=v.pct, kbc_earns=text)


def _is_kbc_side(partner: Partner) -> bool:
    return partner.kind in ("kbc", "advisor")


def advisor_slot(as_of: dt.date) -> dt.datetime:
    """Simulated agenda: the next working day after as_of, 10:00."""
    d = as_of + dt.timedelta(days=1)
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return dt.datetime.combine(d, dt.time(10, 0))


# ---- context -------------------------------------------------------------------------------------------------------


def context_for(conn, customer_id: int, as_of: dt.date) -> CustomerContext:
    customer = db.get_customer(conn, customer_id)
    if not customer:
        raise EcosystemError(404, "Customer not found")
    ctx = build_context(customer, db.get_transactions(conn, customer_id), db.get_balance_today(conn, customer_id),
                        as_of)
    from .sources import values_for   # local import: sources imports this module's store/models
    return apply_sources(ctx, values_for(conn, customer_id, as_of))


def _holdings_with_journeys(conn, ctx: CustomerContext) -> list[ProductRef]:
    reg = registry()
    from .context import HOLDING_CATALOGUE
    ids = [HOLDING_CATALOGUE[h] for h in sorted(ctx.holdings) if h in HOLDING_CATALOGUE]
    for g in store.goals(conn, ctx.customer.id, ctx.as_of):
        for row in store.ledger(conn, g["id"]):
            if row["metric"] == "product" and row["label"] not in ids:
                ids.append(row["label"])
    return [reg.product(i) for i in ids if i in reg.catalogue]


# ---- building the response models -------------------------------------------------------------------------------


def _potential(pb: Playbook) -> WinTotals:
    t = WinTotals()
    for s in pb.steps:
        t.customer_eur += s.estimates.customer_eur
        t.hours_saved += s.estimates.hours_saved
        t.kbc_revenue_eur += s.estimates.kbc_revenue_eur
        t.partner_fees_eur += s.estimates.partner_fee_eur
        t.kbc_products += [p for p in s.kbc_products if p not in t.kbc_products]
        t.partner_leads += 1 if registry().partners[s.provider].kind == "partner" else 0  # noqa: E501
    return t


def _totals(rows) -> WinTotals:
    t = WinTotals()
    for r in rows:
        if r["metric"] == "eur" and r["party"] == "customer":
            t.customer_eur += r["value"]
        elif r["metric"] == "hours":
            t.hours_saved += r["value"]
        elif r["metric"] == "revenue_eur":
            t.kbc_revenue_eur += r["value"]
        elif r["metric"] == "fee_eur":
            t.partner_fees_eur += r["value"]
        elif r["metric"] == "product" and r["label"] not in t.kbc_products:
            t.kbc_products.append(r["label"])
        elif r["metric"] == "lead":
            t.partner_leads += int(r["value"])
    return t


def _data_shared(step: PlaybookStep) -> tuple[list[DataField], list[str]]:
    reg = registry()
    if _is_kbc_side(reg.partners[step.provider]):
        return [], ["Nothing leaves KBC"]
    shared = [reg.fields[f] for f in step.fields]
    labels = {f.label for f in shared}
    return shared, [label for label in reg.never_shared_default if label not in labels]


def demoted_partners(conn) -> set[str]:
    """Partners that missed their SLA DEMOTE_AFTER times or more (from the live partner calls)."""
    misses: dict[str, int] = {}
    for c in store.calls(conn):
        if c["outcome"] == "timeout":
            misses[c["partner_id"]] = misses.get(c["partner_id"], 0) + 1
    return {pid for pid, n in misses.items() if n >= DEMOTE_AFTER}


def ranked_options(playbook_id: str, s: PlaybookStep, demoted: set[str] | frozenset = frozenset()) -> list[str]:
    """The registry ranking (outcome rate, then rating; never fee) with partners that keep missing their SLA
    moved to the back. A stable sort, so the registry order holds within each group."""
    return sorted(registry().options(playbook_id, s), key=lambda pid: pid in demoted)


def _options(pb: Playbook, s: PlaybookStep, chosen: str, demoted: set[str] | frozenset = frozenset(),
             tried: list[str] | None = None) -> list[PartnerOption]:
    reg = registry()
    ids = ranked_options(pb.id, s, demoted)
    if len(ids) < 2:
        return []
    tried = tried or []
    best = next((pid for pid in ids if pid not in tried), None)
    out = []
    for rank, pid in enumerate(ids):
        p = reg.partners[pid]
        out.append(PartnerOption(
            provider=reg.provider(pid), rating=p.rating, outcome_rate=p.outcome_rate, rank=rank + 1,
            recommended=pid == best, chosen=pid == chosen, fee=fee_disclosure(p),
            data_shared=[reg.fields[f] for f in s.fields if f in reg.fields],
            demoted=pid in demoted, tried=pid in tried,
        ))
    return out


def _step_model(pb: Playbook, s: PlaybookStep, order: int, row, connected: set[str] | None = None,
                demoted: set[str] | frozenset = frozenset(), joint: dict | None = None) -> Step:
    reg = registry()
    s = effective_step(s, row)
    shared, not_shared = _data_shared(s)
    partner = reg.partners[s.provider]
    keys = row.keys()
    done_on = row["done_on"] if "done_on" in keys else None
    booking = ""
    if partner.kind == "advisor" and row["status"] in ("in_progress", "done") and row["result"]:
        booking = row["result"]
    return Step(
        step_id=s.id, order=order, title=s.title, description=s.description, provider=reg.provider(s.provider),
        why_this_provider=s.why, products=[reg.product(p) for p in s.products], status=row["status"],
        data_shared=shared, data_not_shared=not_shared, consent_days=s.consent_days, win=s.win,
        estimates=s.estimates, result=row["result"], ref=row["ref"], grant_id=row["grant_id"],
        updated_at=dt.datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        already_held=bool(row["already_held"]),
        done_on=dt.date.fromisoformat(done_on) if done_on else None,
        fee=fee_disclosure(partner), alternatives=_options(pb, s, s.provider, demoted, _tried(row)),
        source_hint=sources.hint_for(pb.id, s.id, connected or set()), booking=booking,
        fallback=_fallback(row) if row["status"] == "blocked" else None,
        **(joint or {}),
    )


def _measure(conn, goal: Goal, customer_id: int, as_of: dt.date) -> list:
    try:
        txs = db.get_transactions(conn, customer_id)
        return outcomes.measure(goal, txs, as_of, db.get_balance_today(conn, customer_id))
    except Exception:  # noqa: BLE001 - measuring must never break the journey view
        return []


def _participants(conn, g) -> list[tuple[int, str]]:
    """(customer id, first name) of the owner and every active household member of a goal."""
    owner = db.get_customer(conn, g["customer_id"])
    out = [(g["customer_id"], owner.first_name if owner else "")]
    out += [(m["customer_id"], m["first_name"]) for m in store.members(conn, g["id"]) if m["status"] == "active"]
    return out


def _is_joint(conn, g) -> bool:
    return g["playbook_id"] in JOINT_PLAYBOOKS and len(_participants(conn, g)) > 1


def _joint_state(conn, g, step_id: str, partner_id: str) -> tuple[list[str], list[str]]:
    """(approved by, waiting for): first names, for approvals of this step with this partner."""
    ok = {a["customer_id"] for a in store.joint_approvals(conn, g["id"], step_id) if a["partner_id"] == partner_id}
    people = _participants(conn, g)
    return [n for cid, n in people if cid in ok], [n for cid, n in people if cid not in ok]


def goal_model(conn, row, as_of: dt.date | None = None, viewer: int | None = None) -> Goal:
    reg = registry()
    pb = reg.playbooks[row["playbook_id"]]
    at = as_of or DEMO_TODAY
    rows = store.steps(conn, row["id"])
    try:
        connected = sources.connected_ids(conn, row["customer_id"], at)
    except Exception:  # noqa: BLE001
        connected = set()
    demoted = demoted_partners(conn)
    joint_goal = _is_joint(conn, row)
    steps = []
    for i, s in enumerate(pb.steps):
        if s.id not in rows:
            continue
        joint = None
        eff = effective_step(s, rows[s.id])
        if joint_goal and reg.partners[eff.provider].kind == "partner":
            approved, waiting = _joint_state(conn, row, s.id, eff.provider)
            open_ = rows[s.id]["status"] in ("proposed", "blocked", "declined")
            joint = {"joint": True, "approved_by": approved if open_ else [], "waiting_for": waiting if open_ else []}
        steps.append(_step_model(pb, s, i + 1, rows[s.id], connected, demoted, joint))
    done = sum(1 for s in steps if s.status == "done")
    goal = Goal(
        goal_id=row["id"], playbook_id=pb.id, title=pb.title, icon=pb.icon, tagline=pb.tagline,
        ecosystems=pb.ecosystems, status=row["status"], created_on=dt.date.fromisoformat(row["created_on"]),
        target_date=dt.date.fromisoformat(row["target_date"]) if row["target_date"] else None,
        origin=row["origin"], evidence=json.loads(row["evidence"]),
        progress=Progress(done=done, total=len(steps)), steps=steps,
        outcome=_totals(store.ledger(conn, row["id"])), potential=_potential(pb), next_goal=pb.next_goal,
        next_goal_title=reg.playbooks[pb.next_goal].title if pb.next_goal in reg.playbooks else None,
    )
    goal.measured = _measure(conn, goal, row["customer_id"], at)
    goal.paused = bool(_col(row, "paused_on"))
    if viewer is not None and viewer != row["customer_id"]:
        goal.role = "member"
    owner = db.get_customer(conn, row["customer_id"])
    members = store.members(conn, row["id"])
    if members:
        goal.household = [HouseholdMember(first_name=owner.first_name if owner else "", role="owner", status="active",
                                          you=viewer in (None, row["customer_id"]))]
        goal.household += [HouseholdMember(first_name=m["first_name"], role="member", status=m["status"],
                                           you=viewer == m["customer_id"]) for m in members]
    return goal


def _last_progress(goal: Goal) -> dt.date:
    return max([goal.created_on] + [s.done_on for s in goal.steps if s.done_on and not s.already_held])


def stall_prompt(conn, row, goal: Goal, at: dt.date) -> StallPrompt | None:
    """One gentle "still want this?" after STALL_DAYS without progress. Shown for STALL_SHOW_DAYS at most, never
    again once answered; never on a paused goal or while a partner is still working on a step."""
    if goal.status != "active" or goal.paused or _col(row, "stall_answer"):
        return None
    if any(s.status == "in_progress" for s in goal.steps) or not any(s.status in ("proposed", "blocked")
                                                                       for s in goal.steps):
        return None
    last = _last_progress(goal)
    days = (at - last).days
    if days < STALL_DAYS:
        return None
    prompted = _col(row, "stall_prompted_on")
    if prompted:
        if not 0 <= (at - dt.date.fromisoformat(prompted)).days <= STALL_SHOW_DAYS:
            return None
    else:
        store.set_stall(conn, row["id"], prompted_on=at)
    return StallPrompt(since=last, days=days,
                       question=f"Nothing has moved on “{goal.title}” for {days} days. Still want KBC to take care "
                                "of it? You can keep it, pause it (no reminders) or stop it.")


def playbook_summaries() -> list[PlaybookSummary]:
    return [PlaybookSummary(playbook_id=p.id, title=p.title, icon=p.icon, tagline=p.tagline, ecosystems=p.ecosystems,
                            steps=len(p.steps)) for p in registry().playbooks.values()]


def withheld_goals(prefs: Prefs) -> set[str] | None:
    """Goals KBC may not suggest on its own: None = none at all (the customer switched off life-event detection),
    otherwise the ones the customer rejected ("not for me") or whose topic they asked not to hear about."""
    if not prefs.allows("detect_life_events"):
        return None
    return held_back_playbooks(prefs.facts) | {c.target for c in prefs.corrections if c.kind == "goal"}


def candidates(conn, ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> list[GoalCandidate]:
    reg = registry()
    withheld = withheld_goals(db.get_prefs(conn, ctx.customer.id))
    if withheld is None:
        return []
    taken = {g["playbook_id"] for g in store.goals(conn, ctx.customer.id) + store.shared_goals(conn, ctx.customer.id)
             if g["status"] != "cancelled"}
    out = []
    for playbook_id, (confidence, evidence, why) in detect(ctx, declared):
        if playbook_id in taken or playbook_id in withheld:
            continue
        pb = reg.playbooks[playbook_id]
        partners = []
        for s in pb.steps:
            name = reg.partners[s.provider].name
            if reg.partners[s.provider].kind == "partner" and name not in partners:
                partners.append(name)
        out.append(GoalCandidate(
            playbook_id=pb.id, title=pb.title, icon=pb.icon, tagline=pb.tagline, ecosystems=pb.ecosystems,
            confidence=confidence, evidence=evidence, why_now=why, steps_preview=[s.title for s in pb.steps],
            partners_preview=partners, potential=_potential(pb),
        ))
    return out


def relevant_playbooks(conn, customer, txs, balance_today: float, as_of: dt.date,
                       declared: list[DeclaredSignalRow]) -> set[str]:
    """Goals that fit this customer now: detected ones plus the ones already running."""
    ctx = build_context(customer, txs, balance_today, as_of)
    running = {g["playbook_id"] for g in store.goals(conn, customer.id, as_of) if g["status"] == "active"}
    return {pid for pid, _ in detect(ctx, declared)} | running


def goals_response(conn, customer_id: int, as_of: dt.date, declared: list[DeclaredSignalRow]) -> GoalsResponse:
    ctx = context_for(conn, customer_id, as_of)
    rows = [g for g in store.goals(conn, customer_id, as_of) + store.shared_goals(conn, customer_id, as_of)
            if g["status"] != "cancelled"]
    goals = []
    for r in rows:
        m = goal_model(conn, r, as_of, viewer=customer_id)
        m.stall = stall_prompt(conn, r, m, as_of)
        goals.append(m)
    cands = candidates(conn, ctx, declared)
    store.mark_shown(conn, customer_id, [c.playbook_id for c in cands])   # learning loop: shown → started
    reg = registry()
    invites = [HouseholdInvite(goal_id=r["id"], title=reg.playbooks[r["playbook_id"]].title,
                               icon=reg.playbooks[r["playbook_id"]].icon, from_name=r["from_name"])
               for r in store.invitations(conn, customer_id) if r["playbook_id"] in reg.playbooks]
    return GoalsResponse(as_of=as_of, candidates=cands, goals=goals, invitations=invites,
                         holdings=_holdings_with_journeys(conn, ctx), playbooks=playbook_summaries())


# ---- customer actions -------------------------------------------------------------------------------------------


def start_goal(conn, customer_id: int, playbook_id: str, as_of: dt.date, declared: list[DeclaredSignalRow]) -> Goal:
    reg = registry()
    pb = reg.playbooks.get(playbook_id)
    if not pb:
        raise EcosystemError(404, "Unknown goal")
    existing = next((g for g in store.goals(conn, customer_id)
                     if g["playbook_id"] == playbook_id and g["status"] == "active"), None)
    if existing:
        return goal_model(conn, existing, as_of)
    ctx = context_for(conn, customer_id, as_of)
    hit = next((d for pid, d in detect(ctx, declared) if pid == playbook_id), None)
    origin, evidence = ("detected", hit[1]) if hit else ("stated", ["You set this goal yourself"])
    steps = []
    for s in pb.steps:
        held = bool(set(s.held_if) & ctx.holdings)
        steps.append((s.id, "done" if held else "proposed", held, "Already arranged with KBC: nothing to do." if held else ""))
    goal_id = store.insert_goal(conn, customer_id, pb.id, origin, evidence, as_of,
                                as_of + dt.timedelta(days=pb.target_days), steps)
    for sid, status, _, _ in steps:
        if status == "done":
            store.set_step_done_on(conn, goal_id, sid, as_of)
    return goal_model(conn, store.goal(conn, customer_id, goal_id), as_of)


def payload_for(step: PlaybookStep, grant_fields: list[str], ctx: CustomerContext) -> dict[str, str]:
    """Data minimisation in code: only fields in the active grant AND in the partner's allowed list leave KBC."""
    allowed = set(registry().partners[step.provider].allowed_fields)
    return {f: ctx.values[f] for f in grant_fields if f in allowed and f in ctx.values}


def _complete_step(conn, customer_id: int, goal_id: int, s: PlaybookStep, result: str,
                   done_on: dt.date | None = None) -> None:
    store.update_step(conn, goal_id, s.id, status="done", result=result, done_on=done_on)
    partner = registry().partners[s.provider]
    rows = []
    e = s.estimates
    if e.customer_eur:
        rows.append((customer_id, goal_id, s.id, "customer", None, "eur", e.customer_eur, s.win.customer))
    if e.hours_saved:
        rows.append((customer_id, goal_id, s.id, "customer", None, "hours", e.hours_saved, ""))
    if e.kbc_revenue_eur:
        rows.append((customer_id, goal_id, s.id, "kbc", None, "revenue_eur", e.kbc_revenue_eur, s.win.kbc))
    rows += [(customer_id, goal_id, s.id, "kbc", None, "product", 1, p) for p in s.kbc_products]
    if partner.kind == "partner":
        rows.append((customer_id, goal_id, s.id, "partner", partner.id, "lead", 1, s.win.partner))
        if e.partner_fee_eur:
            rows.append((customer_id, goal_id, s.id, "partner", partner.id, "fee_eur", e.partner_fee_eur,
                         partner.value_share.model))
    store.insert_ledger(conn, rows)
    _maybe_complete_goal(conn, goal_id)


def _maybe_complete_goal(conn, goal_id: int) -> None:
    rows = store.steps(conn, goal_id).values()
    if all(r["status"] in ("done", "declined") for r in rows) and any(r["status"] == "done" for r in rows):
        store.set_goal_status(conn, goal_id, "completed")


def decide_step(conn, customer_id: int, goal_id: int, step_id: str, decision: str,
                as_of: dt.date, partner_id: str | None = None) -> tuple[Goal, list[PendingSimulation]]:
    g = store.goal_for(conn, customer_id, goal_id)
    if not g or g["status"] == "cancelled":
        raise EcosystemError(404, "Goal not found")
    owner = g["customer_id"]
    reg = registry()
    base = reg.step(g["playbook_id"], step_id)
    row = store.steps(conn, goal_id).get(step_id)
    if not base or not row:
        raise EcosystemError(404, "Step not found")
    pending: list[PendingSimulation] = []
    tried = _tried(row)
    if partner_id is not None:
        if decision != "approve":
            raise EcosystemError(422, "A partner can only be chosen when approving")
        options = reg.options(g["playbook_id"], base)
        if partner_id not in options:
            raise EcosystemError(422, "This partner is not available for this step")
        if partner_id in tried and any(p not in tried for p in options):
            raise EcosystemError(422, "This partner already declined or didn't answer: pick another one")
    if decision == "approve" and row["status"] in ("proposed", "blocked", "declined"):
        fb = _fallback(row)
        chosen = partner_id or (fb.partner_id if fb and fb.partner_id else None) or row["partner_id"] or base.provider
        if chosen != base.provider or row["partner_id"]:
            store.update_step(conn, goal_id, step_id, partner_id=chosen)
            row = store.steps(conn, goal_id)[step_id]
    s = effective_step(base, row)
    partner = reg.partners[s.provider]

    def view() -> Goal:
        return goal_model(conn, store.goal_for(conn, customer_id, goal_id), as_of, viewer=customer_id)

    if decision == "decline":
        if row["status"] not in ("proposed", "blocked"):
            raise EcosystemError(409, "Only an open step can be declined")
        store.update_step(conn, goal_id, step_id, status="declined")
        store.clear_approvals(conn, goal_id, step_id)
        _maybe_complete_goal(conn, goal_id)
    elif decision == "reset":
        if row["status"] not in ("declined", "blocked"):
            raise EcosystemError(409, "Only a declined or blocked step can be reopened")
        store.update_step(conn, goal_id, step_id, status="proposed")
        if g["status"] == "completed":
            store.set_goal_status(conn, goal_id, "active")
    else:  # approve
        if row["status"] not in ("proposed", "blocked", "declined"):
            raise EcosystemError(409, "This step is already under way")
        joint = partner.kind == "partner" and _is_joint(conn, g)
        if joint:
            store.approve_joint(conn, goal_id, step_id, customer_id, partner.id)
            if _joint_state(conn, g, step_id, partner.id)[1]:
                return view(), []          # waiting for the other household member: nothing is shared yet
        ctx = context_for(conn, owner, as_of)
        if g["status"] == "completed":
            store.set_goal_status(conn, goal_id, "active")
        if _col(g, "paused_on"):
            store.set_goal_pause(conn, goal_id, None)    # acting on a step resumes a paused journey
        if partner.kind == "kbc":
            _complete_step(conn, owner, goal_id, s, ctx.fill(s.result), as_of)
        elif partner.kind == "advisor":
            slot = advisor_slot(as_of)
            booking = (f"Meeting booked with {partner.name}: {slot.strftime('%a %d %b %Y, %H:%M')} (in branch or by "
                       "video). Your advisor already has the file KBC built: your goal, the steps done and the "
                       "numbers, so you never start from zero.")
            _complete_step(conn, owner, goal_id, s, booking, as_of)
            store.insert_event(conn, partner.id, "outbound", f"KBC → {partner.name}: meeting booked for "
                               f"{slot.isoformat(timespec='minutes')} ({s.title}). File stays inside KBC.",
                               customer_id=owner, goal_id=goal_id, step_id=step_id, verified=True)
        else:
            purpose = f"{s.title} ({reg.playbooks[g['playbook_id']].title})"
            if joint:
                purpose += ", approved by every household member"
            grant_id = store.insert_grant(conn, owner, goal_id, step_id, partner.id, s.fields, purpose, as_of,
                                          as_of + dt.timedelta(days=s.consent_days))
            payload = payload_for(s, s.fields, ctx)
            ref = f"{partner.id.replace('_', '-')}-{secrets.token_hex(6)}"
            store.update_step(conn, goal_id, step_id, status="in_progress", ref=ref, grant_id=grant_id,
                              started_at=store.now())
            store.insert_call(conn, partner.id, ref, owner, goal_id, step_id, as_of)
            store.set_step_fallback(conn, goal_id, step_id, tried, None)
            store.clear_approvals(conn, goal_id, step_id)
            labels = ", ".join(reg.fields[f].label.lower() for f in payload)
            store.insert_event(conn, partner.id, "outbound", f"KBC → {partner.name}: {s.title}. Shared under grant "
                               f"#{grant_id}: {labels}", customer_id=owner, goal_id=goal_id, step_id=step_id,
                               verified=True)
            store.set_step_done_on(conn, goal_id, step_id, as_of)   # replaced when the partner reports done
            store.update_step(conn, goal_id, step_id, status="in_progress")
            pending.append(PendingSimulation(partner.id, ref, ctx.fill(s.result)))
    return view(), pending


def _drop_partner(conn, owner: int, goal_id: int, step_id: str, partner: Partner, reason: str, on: dt.date,
                  message: str) -> list[PendingSimulation]:
    """The partner rejected, failed or missed its SLA: end its consent (it must delete the data), block the step
    and propose the next-ranked vetted partner that hasn't been tried. Nothing goes to that partner until the
    customer approves again."""
    reg = registry()
    g = store.goal(conn, owner, goal_id)
    row = store.steps(conn, goal_id).get(step_id)
    base = reg.step(g["playbook_id"], step_id) if g else None
    if not g or not row or not base:
        return []
    tried = _tried(row) + ([partner.id] if partner.id not in _tried(row) else [])
    nxt = next((pid for pid in ranked_options(g["playbook_id"], base, demoted_partners(conn)) if pid not in tried), None)
    pending: list[PendingSimulation] = []
    grant = store.grant(conn, row["grant_id"]) if row["grant_id"] else None
    if grant and grant["status"] == "active":
        store.revoke_grant(conn, grant["id"], on)
        pending += _deletion_request(conn, grant)
    name = reg.partners[nxt].name if nxt else None
    text = message + (f" {name} can do this instead: nothing is shared with them until you approve."
                      if nxt else " There is no other vetted partner for this step yet: try again later or ask "
                                  "your KBC advisor.")
    store.update_step(conn, goal_id, step_id, status="blocked", result=text[:300])
    store.set_step_fallback(conn, goal_id, step_id, tried,
                            {"reason": reason, "message": text, "partner_id": nxt, "partner_name": name})
    store.clear_approvals(conn, goal_id, step_id)
    return pending


def _sla_seconds(partner: Partner) -> float:
    """Real-time SLA. PARTNER_SIM_SLA_S shortens it for a live demo (e.g. 20 s); otherwise sla_hours."""
    env = os.environ.get("PARTNER_SIM_SLA_S")
    return float(env) if env else partner.sla_hours * 3600.0


def sweep_timeouts(conn, as_of: dt.date, customer_id: int | None = None) -> list[PendingSimulation]:
    """Close partner calls that got no answer within the partner's SLA, in simulated time (time travel) or in real
    time, and offer the next partner. Returns the deletion requests to send after the commit."""
    reg = registry()
    pending: list[PendingSimulation] = []
    now = dt.datetime.now(dt.timezone.utc)
    for c in store.open_calls(conn):
        if customer_id is not None and not store.goal_for(conn, customer_id, c["goal_id"]):
            continue
        partner = reg.partners.get(c["partner_id"])
        if not partner or partner.sla_hours <= 0:
            continue
        goal = conn.execute("SELECT status FROM eco_goals WHERE id = ?", (c["goal_id"],)).fetchone()
        if not goal or goal["status"] == "cancelled":
            continue                       # the customer stopped the goal: the partner owes no answer
        sim_hours = (as_of - dt.date.fromisoformat(c["sent_on"])).days * 24
        real_s = (now - dt.datetime.fromisoformat(c["sent_at"])).total_seconds()
        if sim_hours < partner.sla_hours and real_s < _sla_seconds(partner):
            continue
        store.close_call_timeout(conn, c["ref"])
        row = store.steps(conn, c["goal_id"]).get(c["step_id"])
        if not row or row["ref"] != c["ref"] or row["status"] != "in_progress":
            continue
        store.insert_event(conn, partner.id, "sla_missed", f"{partner.name} missed its {partner.sla_hours} h SLA: "
                           "consent ended, data deletion requested, next partner offered to the customer",
                           customer_id=c["customer_id"], goal_id=c["goal_id"], step_id=c["step_id"], verified=True)
        on = max(as_of, dt.date.fromisoformat(c["sent_on"]))
        pending += _drop_partner(conn, c["customer_id"], c["goal_id"], c["step_id"], partner, "timeout", on,
                                 f"{partner.name} didn't answer within {partner.sla_hours} hours, so KBC stopped the "
                                 "request and asked them to delete your data.")
    return pending


def run_simulations(pending: list[PendingSimulation]) -> None:
    for p in pending:
        if p.kind == "deleted":
            simulate_deletion(p.partner_id, p.ref, handle_webhook)
        else:
            simulate_partner(p.partner_id, p.ref, p.result, handle_webhook)


def cancel_goal(conn, customer_id: int, goal_id: int, as_of: dt.date) -> None:
    g = store.goal(conn, customer_id, goal_id)
    if not g:
        raise EcosystemError(404, "Goal not found")
    store.set_goal_status(conn, goal_id, "cancelled")
    pending: list[PendingSimulation] = []
    for grant in store.grants(conn, customer_id):
        if grant["goal_id"] == goal_id and grant["status"] == "active":
            store.revoke_grant(conn, grant["id"], as_of)
            pending += _deletion_request(conn, grant)
    return pending


def _deletion_request(conn, grant) -> list[PendingSimulation]:
    """Ask the (simulated) partner to delete the data; it confirms with a signed 'deleted' webhook."""
    row = store.steps(conn, grant["goal_id"]).get(grant["step_id"])
    if not row or not row["ref"]:
        return []
    return [PendingSimulation(grant["partner_id"], row["ref"], "", kind="deleted")]


# ---- partner webhooks -----------------------------------------------------------------------------------------------


def handle_webhook(partner_id: str, body: bytes, headers: dict[str, str]) -> dict:
    """Verify, then apply. Opens its own transaction (it is called by partners, not by a customer request)."""
    reg = registry()
    if partner_id not in reg.partners or reg.partners[partner_id].kind != "partner":
        raise WebhookError(404, "Unknown partner")
    lower = {k.lower(): v for k, v in headers.items()}
    event: PartnerWebhook = verify(partner_id, lower.get("x-kbc-timestamp"), lower.get("x-kbc-signature"), body)
    pending: list[PendingSimulation] = []
    late = False
    with db.tx() as conn:
        c = store.call(conn, event.ref)
        if c and c["partner_id"] == partner_id and event.status == "deleted":
            if not store.insert_event(conn, partner_id, "deleted", event.result or "deleted", event_id=event.event_id,
                                      customer_id=c["customer_id"], goal_id=c["goal_id"], step_id=c["step_id"],
                                      verified=True):
                return {"ok": True, "duplicate": True}
            if not store.confirm_deletion(conn, c["customer_id"], c["goal_id"], c["step_id"], partner_id):
                raise WebhookError(409, "No ended consent to confirm deletion for")
            return {"ok": True}
        if c and c["partner_id"] == partner_id and c["outcome"] == "timeout":
            # the partner answers after KBC already gave up on it: logged for its scorecard, nothing changes
            if store.insert_event(conn, partner_id, "late", f"Late answer ({event.status}) after the SLA: ignored",
                                  event_id=event.event_id, customer_id=c["customer_id"], goal_id=c["goal_id"],
                                  step_id=c["step_id"], verified=True):
                store.mark_call_late(conn, event.ref)
            late = True
        else:
            row = store.step_by_ref(conn, event.ref)
            base = reg.step(row["playbook_id"], row["step_id"]) if row else None
            if not row or not base or effective_step(base, row).provider != partner_id:
                raise WebhookError(404, "Unknown reference")
            if not store.insert_event(conn, partner_id, event.status, event.result or event.status,
                                      event_id=event.event_id, customer_id=row["customer_id"], goal_id=row["goal_id"],
                                      step_id=row["step_id"], verified=True):
                return {"ok": True, "duplicate": True}
            pending = _apply_partner_event(conn, partner_id, event, row, base, c)
    if late:
        raise WebhookError(409, "Too late: the request timed out and the customer was offered another partner")
    run_simulations(pending)
    return {"ok": True}


def _apply_partner_event(conn, partner_id: str, event: PartnerWebhook, row, base: PlaybookStep,
                         c) -> list[PendingSimulation]:
    if event.status == "deleted":
        # only meaningful once the consent ended: then the partner must erase the data and say so
        if not store.confirm_deletion(conn, row["customer_id"], row["goal_id"], row["step_id"], partner_id):
            raise WebhookError(409, "No ended consent to confirm deletion for")
        return []
    grant = store.grant(conn, row["grant_id"]) if row["grant_id"] else None
    if not grant or grant["status"] != "active":
        raise WebhookError(409, "Consent was revoked")
    if row["status"] != "in_progress":
        raise WebhookError(409, "Step is not in progress")
    s = effective_step(base, row)
    partner = registry().partners[partner_id]
    on = dt.date.fromisoformat(c["sent_on"]) if c else DEMO_TODAY
    if event.status == "in_progress":
        store.answer_call(conn, event.ref, None)
    elif event.status == "done":
        store.answer_call(conn, event.ref, "done")
        done_on = row["done_on"] if "done_on" in row.keys() and row["done_on"] else None
        _complete_step(conn, row["customer_id"], row["goal_id"], s, event.result,
                       dt.date.fromisoformat(done_on) if done_on else None)
    elif event.status == "rejected":
        store.answer_call(conn, event.ref, "rejected")
        reason = (event.result or "no reason given").rstrip(".")
        return _drop_partner(conn, row["customer_id"], row["goal_id"], row["step_id"], partner, "rejected", on,
                             f"{partner.name} can't take this on ({reason}). Your consent for them ended.")
    elif event.status == "failed":
        store.answer_call(conn, event.ref, "failed")
        return _drop_partner(conn, row["customer_id"], row["goal_id"], row["step_id"], partner, "failed", on,
                             event.result or f"{partner.name} could not complete this step.")
    return []


# ---- consent passport ---------------------------------------------------------------------------------------------


def consents(conn, customer_id: int, as_of: dt.date) -> ConsentsResponse:
    reg = registry()
    out = []
    for r in store.grants(conn, customer_id) + store.shared_grants(conn, customer_id):
        g = store.goal_for(conn, customer_id, r["goal_id"])
        if not g:
            continue
        step = reg.step(g["playbook_id"], r["step_id"])
        expires = dt.date.fromisoformat(r["expires_on"])
        status = r["status"] if r["status"] == "revoked" else ("expired" if expires < as_of else "active")
        deleted_at = r["deleted_at"] if "deleted_at" in r.keys() else None
        partner = reg.partners[r["partner_id"]]
        out.append(ConsentGrant(
            deletion_confirmed_at=dt.datetime.fromisoformat(deleted_at) if deleted_at else None,
            deletion_confirmed_by=partner.name if deleted_at else None, kbc_earns=fee_disclosure(partner).kbc_earns,
            grant_id=r["id"], partner_id=r["partner_id"], partner_name=partner.name,
            goal_id=g["id"], goal_title=reg.playbooks[g["playbook_id"]].title, step_id=r["step_id"],
            step_title=step.title if step else r["step_id"],
            fields=[reg.fields[f] for f in json.loads(r["fields"]) if f in reg.fields], purpose=r["purpose"],
            granted_on=dt.date.fromisoformat(r["granted_on"]), expires_on=expires, status=status,
            revoked_on=dt.date.fromisoformat(r["revoked_on"]) if r["revoked_on"] else None,
        ))
    active = [c for c in out if c.status == "active"]
    try:
        inbound = sources.sources_response(conn, customer_id, as_of).sources
    except sources.SourceError:
        inbound = []
    return ConsentsResponse(grants=out, partners_with_access=len({c.partner_id for c in active}),
                            fields_shared=sum(len(c.fields) for c in active), sources=inbound)


def revoke(conn, customer_id: int, grant_id: int, as_of: dt.date) -> list[PendingSimulation]:
    """Revoke a grant. Returns the deletion requests to send to the partner after the commit."""
    r = store.grant_for(conn, grant_id, customer_id)   # owner, or a household member of the goal
    if not r:
        raise EcosystemError(404, "Consent not found")
    if r["status"] != "active":
        return []
    store.revoke_grant(conn, grant_id, as_of)
    store.clear_approvals(conn, r["goal_id"], r["step_id"])
    step = store.steps(conn, r["goal_id"]).get(r["step_id"])
    if step and step["status"] in ("approved", "in_progress"):
        store.update_step(conn, r["goal_id"], r["step_id"], status="blocked",
                          result="You revoked access. The partner was told to stop and delete your data.")
    store.insert_event(conn, r["partner_id"], "revoked", f"Consent #{grant_id} revoked by the customer: partner "
                       "notified to stop processing and delete the data", customer_id=r["customer_id"],
                       goal_id=r["goal_id"], step_id=r["step_id"], verified=True)
    return _deletion_request(conn, r)


# ---- KBC ecosystem console ------------------------------------------------------------------------------------------

_detected_cache: tuple[dict[str, int], int, float] | None = None
_rule_stats: dict[str, dict] = {}     # playbook -> {"conf": sum of confidences, "rules": {rule: hits}}
_MONTHS = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"


def rule_label(evidence: str) -> str:
    """'You pay €850 rent a month' → 'You pay € rent a month': the rule, without the customer's numbers."""
    text = re.sub(r"\([^)]*\)", "", evidence)
    text = re.sub(_MONTHS, "", text)
    text = re.sub(r"[-+]?€?\s?[\d][\d.,]*\s?(×|%)?", "…", text)
    text = re.sub(r"(…\s*)+", "… ", text)
    return re.sub(r"\s+", " ", text).strip(" :,")[:90]


def _portfolio_detection() -> tuple[dict[str, int], int, float]:
    """Run intent detection over the whole synthetic portfolio once (cached): how often each goal is spotted."""
    global _detected_cache
    if _detected_cache:
        return _detected_cache
    counts = {pid: 0 for pid in registry().playbooks}
    started = time.perf_counter()
    _rule_stats.clear()
    with db.tx() as conn:
        ids = db.all_customer_ids(conn)
        for cid in ids:
            customer = db.get_customer(conn, cid)
            txs = db.get_transactions(conn, cid)
            if not customer or not txs:
                continue
            ctx = build_context(customer, txs, db.get_balance_today(conn, cid), DEMO_TODAY)
            for pid, (conf, evidence, _) in detect(ctx):
                counts[pid] += 1
                st = _rule_stats.setdefault(pid, {"conf": 0.0, "rules": {}})
                st["conf"] += conf
                for e in evidence:
                    label = rule_label(e)
                    st["rules"][label] = st["rules"].get(label, 0) + 1
    elapsed = (time.perf_counter() - started) * 1000
    _detected_cache = (counts, len(ids), elapsed)
    return _detected_cache


def warm_portfolio() -> None:
    try:
        _portfolio_detection()
    except Exception:  # noqa: BLE001 - warming is best-effort; the console computes it on first use instead
        pass


def overview(conn) -> EcosystemOverview:
    reg = registry()
    detected, n, ms = _portfolio_detection()
    n = max(n, 1)
    steps = store.all_steps_with_goals(conn)
    goals = conn.execute("SELECT playbook_id, status FROM eco_goals").fetchall()
    funnel = []
    projection = {"customers_with_a_goal": 0.0, "customer_eur": 0.0, "hours_saved": 0.0, "kbc_revenue_eur": 0.0,
                  "partner_fees_eur": 0.0}
    for pb in reg.playbooks.values():
        share = detected[pb.id] / n
        funnel.append(FunnelRow(
            playbook_id=pb.id, title=pb.title, icon=pb.icon, detected=detected[pb.id],
            started=sum(1 for g in goals if g["playbook_id"] == pb.id and g["status"] != "cancelled"),
            steps_done=sum(1 for s in steps if s["playbook_id"] == pb.id and s["status"] == "done"
                           and not s["already_held"]),
            completed=sum(1 for g in goals if g["playbook_id"] == pb.id and g["status"] == "completed"),
            projected_2_3m=round(share * PORTFOLIO_SIZE),
        ))
        journeys = share * PORTFOLIO_SIZE * ADOPTION
        pot = _potential(pb)
        projection["customers_with_a_goal"] += share * PORTFOLIO_SIZE
        projection["customer_eur"] += journeys * pot.customer_eur
        projection["hours_saved"] += journeys * pot.hours_saved
        projection["kbc_revenue_eur"] += journeys * pot.kbc_revenue_eur
        projection["partner_fees_eur"] += journeys * pot.partner_fees_eur
    ledger = store.ledger(conn)
    events = store.events(conn)
    all_calls = store.calls(conn)
    demoted = demoted_partners(conn)
    partner_rows = []
    for p in reg.partners.values():
        if p.kind != "partner":
            continue
        mine = [r for r in ledger if r["partner_id"] == p.id]
        sent = [s for s in steps if s["ref"].startswith(p.id.replace("_", "-") + "-")]
        durations = [(dt.datetime.fromisoformat(s["updated_at"]) - dt.datetime.fromisoformat(s["started_at"]))
                     .total_seconds() for s in sent if s["status"] == "done" and s["started_at"]]
        calls = [c for c in all_calls if c["partner_id"] == p.id]
        answered = [(dt.datetime.fromisoformat(c["first_answer_at"]) - dt.datetime.fromisoformat(c["sent_at"]))
                    .total_seconds() for c in calls if c["first_answer_at"] and not c["late"]]
        closed = [c for c in calls if c["outcome"]]
        response = answered or durations
        partner_rows.append(PartnerRow(
            partner_id=p.id, name=p.name, ecosystems=p.ecosystems, value_share=p.value_share, leads=len(sent),
            completed=sum(1 for s in sent if s["status"] == "done"),
            fees_eur=sum(r["value"] for r in mine if r["metric"] == "fee_eur"),
            avg_response_s=round(sum(response) / len(response), 1) if response else None,
            calls=len(calls), sla_misses=sum(1 for c in calls if c["outcome"] == "timeout"),
            rejections=sum(1 for c in calls if c["outcome"] == "rejected"),
            failures=sum(1 for c in calls if c["outcome"] == "failed"),
            late_answers=sum(1 for c in calls if c["late"]),
            outcome_rate_live=round(sum(1 for c in closed if c["outcome"] == "done") / len(closed), 2) if closed else None,
            sla_hours=p.sla_hours, demoted=p.id in demoted, sim_mode=behaviour_of(p.id),
        ))
    partner_rows.sort(key=lambda r: (-r.leads, r.name))
    shown = store.shown_counts(conn)
    learning, rules = [], []
    for row in funnel:
        st = _rule_stats.get(row.playbook_id, {"conf": 0.0, "rules": {}})
        n_shown = shown.get(row.playbook_id, 0)
        learning.append(LearningRow(
            playbook_id=row.playbook_id, title=row.title, icon=row.icon, detected=row.detected,
            hit_rate=round(row.detected / n, 4), avg_confidence=round(st["conf"] / row.detected, 2) if row.detected else 0,
            shown=n_shown, started=row.started, completed=row.completed,
            start_rate=round(min(1.0, row.started / n_shown), 2) if n_shown else None,
            completion_rate=round(row.completed / row.started, 2) if row.started else None,
        ))
        for label, hits in sorted(st["rules"].items(), key=lambda kv: -kv[1])[:4]:
            rules.append(RuleRow(playbook_id=row.playbook_id, rule=label, hits=hits, hit_rate=round(hits / n, 4)))
    return EcosystemOverview(
        learning=learning, rules=rules, outcomes=_outcome_summary(conn),
        catalogue_items=len(reg.catalogue), ecosystems=len({c.ecosystem for c in reg.catalogue.values()}),
        building_blocks_used=len(reg.used_building_blocks()),
        partners=sum(1 for p in reg.partners.values() if p.kind == "partner"),
        funnel=funnel, partner_rows=partner_rows,
        events=[EventRow(at=dt.datetime.fromisoformat(e["at"]), partner_id=e["partner_id"], kind=e["kind"],
                         summary=e["summary"], verified=bool(e["verified"])) for e in events],
        realised=_totals(ledger), projection={k: round(v) for k, v in projection.items()},
        assumptions=[
            f"Detection rates measured on {n} synthetic customers at {DEMO_TODAY.isoformat()}, scaled to 2.3M",
            f"{round(ADOPTION * 100)}% of customers with a detected goal start the journey and finish every step",
            "Per-step euro, hour, revenue and fee figures are illustrative estimates from the playbooks",
            "Partners and value-share terms are illustrative, not real contracts",
            f"Partners that miss their SLA {DEMOTE_AFTER}× are ranked below partners that answer (never by fee)",
        ],
        scoring_ms=round(ms, 1),
    )


def _outcome_summary(conn) -> OutcomeSummary:
    """Realised vs estimated across every running or completed goal, measured at DEMO_TODAY."""
    out = OutcomeSummary()
    for g in conn.execute("SELECT * FROM eco_goals WHERE status != 'cancelled'").fetchall():
        if g["playbook_id"] not in registry().playbooks:
            continue
        for m in goal_model(conn, g, max(DEMO_TODAY, dt.date.fromisoformat(g["created_on"]))).measured:
            if m.status == "verified":
                out.verified += 1
                if m.unit.startswith("€"):
                    out.verified_eur += m.measured_eur or 0
                    out.estimated_eur_for_verified += m.estimate_eur or 0
            elif m.status == "pending":
                out.pending += 1
            else:
                out.not_met += 1
    out.verified_eur = round(out.verified_eur)
    out.estimated_eur_for_verified = round(out.estimated_eur_for_verified)
    return out


# ---- households --------------------------------------------------------------------------------------------------


def invite_member(conn, customer_id: int, goal_id: int, username: str, as_of: dt.date) -> Goal:
    """The owner shares a goal with a household member (a KBC customer, by username). Owner only."""
    g = store.goal(conn, customer_id, goal_id)
    if not g or g["status"] == "cancelled":
        raise EcosystemError(404, "Goal not found")
    if g["playbook_id"] not in JOINT_PLAYBOOKS:
        raise EcosystemError(422, "This goal is personal and can't be shared")
    user = db.get_user(conn, username)
    if not user or user["role"] != "customer" or user["customer_id"] in (None, customer_id):
        raise EcosystemError(404, "No customer with that username")
    store.invite_member(conn, goal_id, user["customer_id"], as_of)
    return goal_model(conn, g, as_of, viewer=customer_id)


def answer_invitation(conn, customer_id: int, goal_id: int, accept: bool, as_of: dt.date) -> None:
    if not store.answer_invite(conn, goal_id, customer_id, accept, as_of):
        raise EcosystemError(404, "Invitation not found")


# ---- stalled journeys ----------------------------------------------------------------------------------------------


def answer_stall(conn, customer_id: int, goal_id: int, answer: str, as_of: dt.date) -> list[PendingSimulation]:
    g = store.goal_for(conn, customer_id, goal_id)
    if not g or g["status"] == "cancelled":
        raise EcosystemError(404, "Goal not found")
    if answer == "stop":
        if g["customer_id"] != customer_id:
            raise EcosystemError(403, "Only the person who started this goal can stop it")
        store.set_stall(conn, goal_id, answer="stop")
        return cancel_goal(conn, customer_id, goal_id, as_of) or []
    if answer == "pause":
        store.set_goal_pause(conn, goal_id, as_of)
    elif answer == "resume":
        store.set_goal_pause(conn, goal_id, None)
    if answer in ("keep", "pause"):
        store.set_stall(conn, goal_id, answer=answer)
    return []


# ---- demo: simulated partner behaviour --------------------------------------------------------------------------


def set_partner_sim(partner_id: str, mode: str) -> dict:
    p = registry().partners.get(partner_id)
    if not p or p.kind != "partner":
        raise EcosystemError(404, "Unknown partner")
    set_behaviour(partner_id, mode)
    return {"partner_id": partner_id, "mode": behaviour_of(partner_id)}


# ---- partner onboarding -------------------------------------------------------------------------------------------

_onboarded: dict[str, PartnerManifest] = {}     # in memory: a proof of concept, not persisted across restarts


def validate_manifest(m: PartnerManifest) -> ManifestResult:
    """The same rules as partners.json (partner_problems), plus onboarding checks. Never returns the key."""
    reg = registry()
    problems = partner_problems(reg, m)
    if m.id in reg.partners:
        problems.append(f"partner {m.id}: id already in the registry")
    known_eco = {c.ecosystem for c in reg.catalogue.values()}
    problems += [f"partner {m.id}: unknown ecosystem {e}" for e in m.ecosystems if e not in known_eco]
    if "done" not in m.webhook.events:
        problems.append(f"partner {m.id}: the webhook contract must at least send 'done'")
    warnings = []
    if "deleted" not in m.webhook.events:
        warnings.append("Add the 'deleted' event: partners must confirm deletion after a revoke or expiry")
    if m.value_share.model == "revenue_share" and not 0 <= m.value_share.pct <= 0.3:
        problems.append(f"partner {m.id}: revenue share must be between 0 and 30%")
    if m.value_share.amount_eur < 0 or m.value_share.amount_eur > 5000:
        problems.append(f"partner {m.id}: fee must be between €0 and €5,000")
    sensitive = [f for f in m.allowed_fields if f in reg.fields and reg.fields[f].sensitive]
    if sensitive:
        warnings.append(f"Sensitive fields need a DPIA before go-live: {', '.join(sensitive)}")
    if not problems:
        _onboarded[m.id] = m
    fingerprint = hashlib.sha256(secret_of(m.id)).hexdigest()[:12]
    return ManifestResult(
        valid=not problems, problems=problems, warnings=warnings,
        partner=None if problems else reg.provider("kbc").model_copy(update={
            "id": m.id, "name": m.name, "kind": "partner", "blurb": m.blurb, "vetting": m.vetting,
            "integration": m.integration}),
        signing=None if problems else SigningSetup(
            secret_env=f"PARTNER_WEBHOOK_SECRET_{m.id.upper()}", key_fingerprint=fingerprint,
            webhook_endpoint=f"/api/partners/{m.id}/webhook"),
    )


def onboarded() -> list[PartnerManifest]:
    return list(_onboarded.values())
