"""The ecosystem engine: intent → goal → journey → consent → provider → outcome.

Step state machine:  proposed ─approve─► in_progress ─partner webhook─► done
                         │                    │  (KBC steps complete immediately)
                         └─decline─► declined └─grant revoked─► blocked ─approve─► in_progress
Every transition is caused by the customer (approve/decline/revoke) or by a verified partner event.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import secrets
import time
from dataclasses import dataclass

from .. import db
from ..schemas import DeclaredSignalRow
from . import store
from .context import CustomerContext, build_context
from .intent import detect
from .models import (
    ConsentGrant, ConsentsResponse, DataField, EcosystemOverview, EventRow, FunnelRow, Goal, GoalCandidate,
    GoalsResponse, PartnerRow, PartnerWebhook, PlaybookSummary, Progress, ProductRef, Step, WinTotals,
)
from .registry import Playbook, PlaybookStep, registry
from .webhooks import WebhookError, simulate_partner, verify

PORTFOLIO_SIZE = 2_300_000
ADOPTION = 0.15            # assumed share of customers with a detected goal who start the journey
DEMO_TODAY = dt.date.fromisoformat(os.environ.get("DEMO_TODAY", "2026-10-20"))
OPEN = ("proposed", "approved", "in_progress", "blocked")


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


# ---- context -------------------------------------------------------------------------------------------------------


def context_for(conn, customer_id: int, as_of: dt.date) -> CustomerContext:
    customer = db.get_customer(conn, customer_id)
    if not customer:
        raise EcosystemError(404, "Customer not found")
    return build_context(customer, db.get_transactions(conn, customer_id), db.get_balance_today(conn, customer_id),
                         as_of)


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
        t.partner_leads += 1 if registry().partners[s.provider].kind == "partner" else 0
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
    if reg.partners[step.provider].kind == "kbc":
        return [], ["Nothing leaves KBC"]
    shared = [reg.fields[f] for f in step.fields]
    labels = {f.label for f in shared}
    return shared, [label for label in reg.never_shared_default if label not in labels]


def _step_model(pb: Playbook, s: PlaybookStep, order: int, row) -> Step:
    reg = registry()
    shared, not_shared = _data_shared(s)
    return Step(
        step_id=s.id, order=order, title=s.title, description=s.description, provider=reg.provider(s.provider),
        why_this_provider=s.why, products=[reg.product(p) for p in s.products], status=row["status"],
        data_shared=shared, data_not_shared=not_shared, consent_days=s.consent_days, win=s.win,
        estimates=s.estimates, result=row["result"], ref=row["ref"], grant_id=row["grant_id"],
        updated_at=dt.datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        already_held=bool(row["already_held"]),
    )


def goal_model(conn, row) -> Goal:
    pb = registry().playbooks[row["playbook_id"]]
    rows = store.steps(conn, row["id"])
    steps = [_step_model(pb, s, i + 1, rows[s.id]) for i, s in enumerate(pb.steps) if s.id in rows]
    done = sum(1 for s in steps if s.status == "done")
    return Goal(
        goal_id=row["id"], playbook_id=pb.id, title=pb.title, icon=pb.icon, tagline=pb.tagline,
        ecosystems=pb.ecosystems, status=row["status"], created_on=dt.date.fromisoformat(row["created_on"]),
        target_date=dt.date.fromisoformat(row["target_date"]) if row["target_date"] else None,
        origin=row["origin"], evidence=json.loads(row["evidence"]),
        progress=Progress(done=done, total=len(steps)), steps=steps,
        outcome=_totals(store.ledger(conn, row["id"])), potential=_potential(pb), next_goal=pb.next_goal,
    )


def playbook_summaries() -> list[PlaybookSummary]:
    return [PlaybookSummary(playbook_id=p.id, title=p.title, icon=p.icon, tagline=p.tagline, ecosystems=p.ecosystems,
                            steps=len(p.steps)) for p in registry().playbooks.values()]


def candidates(conn, ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> list[GoalCandidate]:
    reg = registry()
    taken = {g["playbook_id"] for g in store.goals(conn, ctx.customer.id) if g["status"] != "cancelled"}
    out = []
    for playbook_id, (confidence, evidence, why) in detect(ctx, declared):
        if playbook_id in taken:
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
    goals = [goal_model(conn, g) for g in store.goals(conn, customer_id, as_of) if g["status"] != "cancelled"]
    return GoalsResponse(as_of=as_of, candidates=candidates(conn, ctx, declared), goals=goals,
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
        return goal_model(conn, existing)
    ctx = context_for(conn, customer_id, as_of)
    hit = next((d for pid, d in detect(ctx, declared) if pid == playbook_id), None)
    origin, evidence = ("detected", hit[1]) if hit else ("stated", ["You set this goal yourself"])
    steps = []
    for s in pb.steps:
        held = bool(set(s.held_if) & ctx.holdings)
        steps.append((s.id, "done" if held else "proposed", held, "Already arranged with KBC: nothing to do." if held else ""))
    goal_id = store.insert_goal(conn, customer_id, pb.id, origin, evidence, as_of,
                                as_of + dt.timedelta(days=pb.target_days), steps)
    return goal_model(conn, store.goal(conn, customer_id, goal_id))


def payload_for(step: PlaybookStep, grant_fields: list[str], ctx: CustomerContext) -> dict[str, str]:
    """Data minimisation in code: only fields in the active grant AND in the partner's allowed list leave KBC."""
    allowed = set(registry().partners[step.provider].allowed_fields)
    return {f: ctx.values[f] for f in grant_fields if f in allowed and f in ctx.values}


def _complete_step(conn, customer_id: int, goal_id: int, s: PlaybookStep, result: str) -> None:
    store.update_step(conn, goal_id, s.id, status="done", result=result)
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
                as_of: dt.date) -> tuple[Goal, list[PendingSimulation]]:
    g = store.goal(conn, customer_id, goal_id)
    if not g or g["status"] == "cancelled":
        raise EcosystemError(404, "Goal not found")
    reg = registry()
    s = reg.step(g["playbook_id"], step_id)
    row = store.steps(conn, goal_id).get(step_id)
    if not s or not row:
        raise EcosystemError(404, "Step not found")
    pending: list[PendingSimulation] = []
    partner = reg.partners[s.provider]

    if decision == "decline":
        if row["status"] not in ("proposed", "blocked"):
            raise EcosystemError(409, "Only an open step can be declined")
        store.update_step(conn, goal_id, step_id, status="declined")
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
        ctx = context_for(conn, customer_id, as_of)
        if g["status"] == "completed":
            store.set_goal_status(conn, goal_id, "active")
        if partner.kind == "kbc":
            _complete_step(conn, customer_id, goal_id, s, ctx.fill(s.result))
        else:
            purpose = f"{s.title} ({reg.playbooks[g['playbook_id']].title})"
            grant_id = store.insert_grant(conn, customer_id, goal_id, step_id, partner.id, s.fields, purpose, as_of,
                                          as_of + dt.timedelta(days=s.consent_days))
            payload = payload_for(s, s.fields, ctx)
            ref = f"{partner.id.replace('_', '-')}-{secrets.token_hex(6)}"
            store.update_step(conn, goal_id, step_id, status="in_progress", ref=ref, grant_id=grant_id,
                              started_at=store.now())
            labels = ", ".join(reg.fields[f].label.lower() for f in payload)
            store.insert_event(conn, partner.id, "outbound", f"KBC → {partner.name}: {s.title}. Shared under grant "
                               f"#{grant_id}: {labels}", customer_id=customer_id, goal_id=goal_id, step_id=step_id,
                               verified=True)
            pending.append(PendingSimulation(partner.id, ref, ctx.fill(s.result)))
    return goal_model(conn, store.goal(conn, customer_id, goal_id)), pending


def run_simulations(pending: list[PendingSimulation]) -> None:
    for p in pending:
        simulate_partner(p.partner_id, p.ref, p.result, handle_webhook)


def cancel_goal(conn, customer_id: int, goal_id: int, as_of: dt.date) -> None:
    g = store.goal(conn, customer_id, goal_id)
    if not g:
        raise EcosystemError(404, "Goal not found")
    store.set_goal_status(conn, goal_id, "cancelled")
    for grant in store.grants(conn, customer_id):
        if grant["goal_id"] == goal_id and grant["status"] == "active":
            store.revoke_grant(conn, grant["id"], as_of)


# ---- partner webhooks -----------------------------------------------------------------------------------------------


def handle_webhook(partner_id: str, body: bytes, headers: dict[str, str]) -> dict:
    """Verify, then apply. Opens its own transaction (it is called by partners, not by a customer request)."""
    reg = registry()
    if partner_id not in reg.partners or reg.partners[partner_id].kind != "partner":
        raise WebhookError(404, "Unknown partner")
    lower = {k.lower(): v for k, v in headers.items()}
    event: PartnerWebhook = verify(partner_id, lower.get("x-kbc-timestamp"), lower.get("x-kbc-signature"), body)
    with db.tx() as conn:
        row = store.step_by_ref(conn, event.ref)
        if not row or reg.step(row["playbook_id"], row["step_id"]).provider != partner_id:
            raise WebhookError(404, "Unknown reference")
        if not store.insert_event(conn, partner_id, event.status, event.result or event.status, event_id=event.event_id,
                                  customer_id=row["customer_id"], goal_id=row["goal_id"], step_id=row["step_id"],
                                  verified=True):
            return {"ok": True, "duplicate": True}
        grant = store.grant(conn, row["grant_id"]) if row["grant_id"] else None
        if not grant or grant["status"] != "active":
            raise WebhookError(409, "Consent was revoked")
        if row["status"] != "in_progress":
            raise WebhookError(409, "Step is not in progress")
        s = reg.step(row["playbook_id"], row["step_id"])
        if event.status == "done":
            _complete_step(conn, row["customer_id"], row["goal_id"], s, event.result)
        elif event.status == "failed":
            store.update_step(conn, row["goal_id"], row["step_id"], status="blocked",
                              result=event.result or "The partner could not complete this step.")
    return {"ok": True}


# ---- consent passport ---------------------------------------------------------------------------------------------


def consents(conn, customer_id: int, as_of: dt.date) -> ConsentsResponse:
    reg = registry()
    out = []
    for r in store.grants(conn, customer_id):
        g = store.goal(conn, customer_id, r["goal_id"])
        if not g:
            continue
        step = reg.step(g["playbook_id"], r["step_id"])
        expires = dt.date.fromisoformat(r["expires_on"])
        status = r["status"] if r["status"] == "revoked" else ("expired" if expires < as_of else "active")
        out.append(ConsentGrant(
            grant_id=r["id"], partner_id=r["partner_id"], partner_name=reg.partners[r["partner_id"]].name,
            goal_id=g["id"], goal_title=reg.playbooks[g["playbook_id"]].title, step_id=r["step_id"],
            step_title=step.title if step else r["step_id"],
            fields=[reg.fields[f] for f in json.loads(r["fields"]) if f in reg.fields], purpose=r["purpose"],
            granted_on=dt.date.fromisoformat(r["granted_on"]), expires_on=expires, status=status,
            revoked_on=dt.date.fromisoformat(r["revoked_on"]) if r["revoked_on"] else None,
        ))
    active = [c for c in out if c.status == "active"]
    return ConsentsResponse(grants=out, partners_with_access=len({c.partner_id for c in active}),
                            fields_shared=sum(len(c.fields) for c in active))


def revoke(conn, customer_id: int, grant_id: int, as_of: dt.date) -> None:
    r = store.grant(conn, grant_id, customer_id)
    if not r:
        raise EcosystemError(404, "Consent not found")
    if r["status"] != "active":
        return
    store.revoke_grant(conn, grant_id, as_of)
    step = store.steps(conn, r["goal_id"]).get(r["step_id"])
    if step and step["status"] in ("approved", "in_progress"):
        store.update_step(conn, r["goal_id"], r["step_id"], status="blocked",
                          result="You revoked access. The partner was told to stop and delete your data.")
    store.insert_event(conn, r["partner_id"], "revoked", f"Consent #{grant_id} revoked by the customer: partner "
                       "notified to stop processing and delete the data", customer_id=customer_id,
                       goal_id=r["goal_id"], step_id=r["step_id"], verified=True)


# ---- KBC ecosystem console ------------------------------------------------------------------------------------------

_detected_cache: tuple[dict[str, int], int, float] | None = None


def _portfolio_detection() -> tuple[dict[str, int], int, float]:
    """Run intent detection over the whole synthetic portfolio once (cached): how often each goal is spotted."""
    global _detected_cache
    if _detected_cache:
        return _detected_cache
    counts = {pid: 0 for pid in registry().playbooks}
    started = time.perf_counter()
    with db.tx() as conn:
        ids = db.all_customer_ids(conn)
        for cid in ids:
            customer = db.get_customer(conn, cid)
            txs = db.get_transactions(conn, cid)
            if not customer or not txs:
                continue
            ctx = build_context(customer, txs, db.get_balance_today(conn, cid), DEMO_TODAY)
            for pid, _ in detect(ctx):
                counts[pid] += 1
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
    partner_rows = []
    for p in reg.partners.values():
        if p.kind != "partner":
            continue
        mine = [r for r in ledger if r["partner_id"] == p.id]
        sent = [s for s in steps if s["ref"].startswith(p.id.replace("_", "-") + "-")]
        durations = [(dt.datetime.fromisoformat(s["updated_at"]) - dt.datetime.fromisoformat(s["started_at"]))
                     .total_seconds() for s in sent if s["status"] == "done" and s["started_at"]]
        partner_rows.append(PartnerRow(
            partner_id=p.id, name=p.name, ecosystems=p.ecosystems, value_share=p.value_share, leads=len(sent),
            completed=sum(1 for s in sent if s["status"] == "done"),
            fees_eur=sum(r["value"] for r in mine if r["metric"] == "fee_eur"),
            avg_response_s=round(sum(durations) / len(durations), 1) if durations else None,
        ))
    partner_rows.sort(key=lambda r: (-r.leads, r.name))
    return EcosystemOverview(
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
        ],
        scoring_ms=round(ms, 1),
    )
