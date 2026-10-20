"""Journey step 1 and 2: recognise an emerging goal and understand why, from the customer's own signals.

Pure functions: CustomerContext (+ what the customer told Kate) → candidate goals with a confidence and
plain-language evidence. Transparent rules by design (like v1's persona scoring), so every candidate can answer
"why am I seeing this?". Nothing happens until the customer taps Start.
"""
from __future__ import annotations

import datetime as dt
from typing import Callable

from ..engine.cards import gen_late_client, gen_new_payee
from ..engine.features import fmt_date, fmt_eur
from ..schemas import DeclaredSignalRow
from .context import PROPERTY_SEARCH, TRAVEL_MERCHANTS, CustomerContext

THRESHOLD = 0.5
Detection = tuple[float, list[str], str]   # confidence, evidence, why now


def _recent(ctx: CustomerContext, days: int):
    lo = ctx.as_of - dt.timedelta(days=days)
    return [t for t in ctx.txs if t.date > lo]


def _declared(declared: list[DeclaredSignalRow], signal: str) -> DeclaredSignalRow | None:
    return next((d for d in declared if d.signal == signal), None)


def detect_buy_home(ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> Detection | None:
    f = ctx.features
    if "mortgage" in ctx.holdings or any(t.category in ("mortgage", "notary") for t in ctx.txs):
        return None   # already owns a home
    score, ev = 0.0, []
    rent = next((r for r in f.recurring_payments if r.category == "rent"), None)
    if rent and f.has_salary:
        score += 0.3
        ev.append(f"You pay {fmt_eur(rent.amount_eur)} rent a month and earn a steady salary")
    if 24 <= f.age <= 45:
        score += 0.1
    saving = [t for t in _recent(ctx, 120) if t.category == "savings_transfer" and t.amount < 0]
    if len(saving) >= 3:
        score += 0.15
        ev.append(f"You moved money to savings {len(saving)} times in the last 4 months")
    recent = _recent(ctx, 200)
    search = [t for t in recent if t.category == "property" and any(p in t.counterparty.lower() for p in PROPERTY_SEARCH)]
    if search:
        score += 0.35
        ev.append(f"A property search alert ({search[0].counterparty}) since {fmt_date(search[0].date)}")
    inspection = [t for t in recent if t.category == "property" and "expert" in t.counterparty.lower()]
    if inspection:
        score += 0.15
        ev.append(f"A building inspection on {fmt_date(inspection[-1].date)}")
    deposit = [t for t in recent if t.category == "property" and t.amount <= -5000]
    if deposit:
        score += 0.3
        ev.append(f"{fmt_eur(deposit[-1].amount)} to a notary's escrow account on {fmt_date(deposit[-1].date)}: "
                  "that looks like a purchase deposit")
    if score < THRESHOLD:
        return None
    why = ("You signed for a house. Let KBC line up the loan, insurance and paperwork before the deed."
           if deposit else "It looks like you're house hunting. KBC can line up every step, from budget to keys.")
    return score, ev, why


def detect_energy_upgrade(ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> Detection | None:
    f = ctx.features
    if "mortgage" not in ctx.holdings and not any(t.category == "notary" for t in ctx.txs):
        return None   # not a home owner
    score, ev = 0.0, []
    # a notary payment, not just the first mortgage instalment in the data: that's a purchase we can date
    deed = next((t for t in ctx.txs if t.category == "notary"), None)
    if deed and (ctx.as_of - deed.date).days <= 540:
        score += 0.35
        ev.append(f"You bought a house on {fmt_date(deed.date)}")
    if "mortgage" in ctx.holdings:
        score += 0.15
    util = [t for t in _recent(ctx, 400) if t.category == "utilities" and t.amount < 0]
    if util:
        amounts = sorted(-t.amount for t in util)
        median = amounts[len(amounts) // 2]
        spike = max(util, key=lambda t: -t.amount)
        if -spike.amount >= max(3 * median, 300) and (ctx.as_of - spike.date).days <= 150:
            score += 0.45
            ev.append(f"An energy bill of {fmt_eur(spike.amount)} from {spike.counterparty.split(' (')[0]} on "
                      f"{fmt_date(spike.date)}, about {round(-spike.amount / median)}× your usual bill")
    if score < THRESHOLD:
        return None
    return score, ev, "Lower bills and a better energy label, with the grants claimed and the works financed."


def detect_new_baby(ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> Detection | None:
    score, ev = 0.0, []
    baby = [t for t in _recent(ctx, 120) if t.category == "baby"]
    benefit = [t for t in ctx.txs if t.category == "child_benefit"]
    if len(baby) >= 2:
        score += 0.5
        ev.append(f"{len(baby)} baby purchases since {fmt_date(baby[0].date)}")
    if benefit and (ctx.as_of - benefit[0].date).days <= 180:
        score += 0.3
        ev.append(f"Child benefit started on {fmt_date(benefit[0].date)}")
    d = _declared(declared, "expecting_baby")
    if d:
        score += 0.6
        ev.insert(0, f"You told Kate on {fmt_date(d.created_at)} that you're expecting")
    if score >= THRESHOLD and "family_insurance" not in ctx.holdings:
        score += 0.1
        ev.append("No family insurance yet")
    if score < THRESHOLD:
        return None
    return min(score, 1.0), ev, "Get covered, budgeted and organised before the sleepless nights start."


def detect_go_freelance(ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> Detection | None:
    if "business_account" in ctx.holdings:
        return None
    score, ev = 0.0, []
    invoices = [t for t in ctx.txs if t.category == "invoice_income" and t.amount > 0]
    if invoices and (ctx.as_of - invoices[0].date).days <= 300:
        score += 0.6
        clients = len({t.counterparty for t in invoices})
        ev.append(f"First client payment on {fmt_date(invoices[0].date)}; {len(invoices)} invoices from "
                  f"{clients} client{'s' if clients != 1 else ''} so far")
        ev.append("Business and private money arrive on the same account")
    d = _declared(declared, "going_freelance")
    if d:
        score += 0.6
        ev.insert(0, f"You told Kate on {fmt_date(d.created_at)} that you're going freelance")
    if score < THRESHOLD:
        return None
    return min(score, 1.0), ev, "Set up everything a freelancer needs in one go, before the first VAT deadline."


def detect_get_paid(ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> Detection | None:
    late = gen_late_client(ctx.features, ctx.customer, ctx.txs, ctx.as_of)
    if not late:
        return None
    return 0.75, late[0].evidence[:2], f"About €{ctx.vars['open_total']} may be open. KBC and its partners can collect it for you."


def detect_retire_well(ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> Detection | None:
    f = ctx.features
    if not 50 <= f.age <= 64:
        return None
    score, ev = 0.3, [f"You're {f.age}: about {67 - f.age} years to your pension"]
    if f.has_salary:
        score += 0.15
    spend = max(f.monthly_spend_avg_90d, 500.0)
    if f.balance_eur >= 10 * spend:
        score += 0.35
        ev.append(f"{fmt_eur(round(f.balance_eur, -2))} on your current account, about {round(f.balance_eur / spend)} months "
                  "of spending, earning nothing")
    if "pension_savings" in ctx.holdings:
        ev.append("You already save for your pension at KBC")
    if score < THRESHOLD + 0.1:
        return None
    return score, ev, "Close your pension gap, put idle money to work and plan for the children, in one plan."


def detect_travel(ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> Detection | None:
    trips = [t for t in _recent(ctx, 45) if t.amount <= -250
             and any(m in t.counterparty.lower() for m in TRAVEL_MERCHANTS)]
    if not trips:
        return None
    total = -sum(t.amount for t in trips)
    ev = [f"{fmt_eur(t.amount)} to {t.counterparty} on {fmt_date(t.date)}" for t in trips[:2]]
    return 0.7 if total >= 800 else 0.55, ev, "Insured, connected abroad and through security fast."


def detect_peace_of_mind(ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> Detection | None:
    f = ctx.features
    if f.age < 65:
        return None
    score, ev = 0.2, []
    payee = gen_new_payee(f, ctx.customer, ctx.txs, ctx.as_of)
    if payee:
        score += 0.5
        ev.append(payee[0].evidence[0] + ", a first payment to this recipient")
    if f.idle_cash_eur >= 5000 and "savings" not in ctx.holdings:
        score += 0.35
        ev.append(f"{fmt_eur(round(f.balance_eur, -2))} on your current account and no savings account")
    if score < THRESHOLD:
        return None
    return min(score, 1.0), ev, "Protected against fraud, savings earning interest and your papers in one place."


DETECTORS: dict[str, Callable[[CustomerContext, list[DeclaredSignalRow]], Detection | None]] = {
    "buy_home": detect_buy_home,
    "energy_upgrade": detect_energy_upgrade,
    "new_baby": detect_new_baby,
    "go_freelance": detect_go_freelance,
    "get_paid": detect_get_paid,
    "retire_well": detect_retire_well,
    "travel": detect_travel,
    "peace_of_mind": detect_peace_of_mind,
}


def detect(ctx: CustomerContext, declared: list[DeclaredSignalRow] | None = None) -> list[tuple[str, Detection]]:
    """All playbooks whose rule fires, most confident first."""
    out = []
    for playbook_id, fn in DETECTORS.items():
        hit = fn(ctx, declared or [])
        if hit:
            out.append((playbook_id, (round(min(hit[0], 1.0), 2), hit[1], hit[2])))
    out.sort(key=lambda x: -x[1][0])
    return out
