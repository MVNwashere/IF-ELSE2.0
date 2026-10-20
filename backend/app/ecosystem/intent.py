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
from .context import (
    CAR_LEASE, PROPERTY_SEARCH, TRAVEL_MERCHANTS, CustomerContext, freelance_estimate, invoice_growth, is_garage,
    is_inheritance, is_subcontractor, private_business_expenses,
)

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
        ev.append(f"First client payment on {fmt_date(invoices[0].date)}; {len(invoices)} invoice{'s' if len(invoices) != 1 else ''} from "
                  f"{clients} client{'s' if clients != 1 else ''} so far")
        ev.append("Business and private money arrive on the same account")
        stop = salary_stop(ctx, min_days=10)
        if stop and stop[1] <= invoices[0].date:
            score += 0.15
            ev.insert(0, f"Your salary from {stop[0]} stopped after {fmt_date(stop[1])}")
        fe = freelance_estimate(ctx.txs, ctx.as_of)
        if fe and fe.registration:
            score += 0.1
            ev.append(f"You registered your business at the enterprise counter on {fmt_date(fe.registration)}")
        work = private_business_expenses(ctx.txs, ctx.as_of, invoices[0].date - dt.timedelta(days=60))
        if work:
            ev.append(f"{fmt_eur(work[0].amount)} to {work[0].counterparty.split(' (')[0]} on {fmt_date(work[0].date)} "
                      "from your private account")
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


def _employer(cp: str) -> str:
    return cp.split(" (")[0].strip()


def salary_stop(ctx: CustomerContext, min_days: int = 25, max_days: int = 200) -> tuple[str, dt.date] | None:
    """(employer, last pay date) if a steady salary (3+ payments) stopped between min_days and max_days ago."""
    by: dict[str, list[dt.date]] = {}
    for t in ctx.txs:
        if t.category == "salary" and t.amount > 0:
            by.setdefault(_employer(t.counterparty), []).append(t.date)
    best = None
    for emp, dates in by.items():
        last = max(dates)
        if len(dates) >= 3 and min_days <= (ctx.as_of - last).days <= max_days and (best is None or last > best[1]):
            best = (emp, last)
    return best


def detect_job_change(ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> Detection | None:
    """A salary stops: a new employer starts paying (job change), or nothing replaces it (job loss).
    Conservative: a salary replaced by invoices is go_freelance, by a pension is retirement; both are left out."""
    stop = salary_stop(ctx, min_days=40, max_days=180)
    if not stop:
        return None
    emp, last = stop
    after = [t for t in ctx.txs if t.date > last and t.amount > 0]
    if any(t.category in ("invoice_income", "pension") for t in after):
        return None
    new = [t for t in after if t.category == "salary" and _employer(t.counterparty) != emp]
    if new:
        first = min(new, key=lambda t: t.date)
        if (ctx.as_of - first.date).days > 120:
            return None
        return 0.55, [f"Your last salary from {emp} was on {fmt_date(last)}",
                      f"A first salary from {_employer(first.counterparty)} on {fmt_date(first.date)}"], \
            "A new job: check your pension rights from the old one and set up the new budget."
    if any(t.category == "salary" for t in after):
        return None
    ev = [f"Your salary from {emp} stopped after {fmt_date(last)}", "No new salary or other work income since"]
    benefit = [t for t in after if t.category == "benefit"]
    if benefit:
        ev.append(f"A benefit payment from {_employer(benefit[0].counterparty)} on {fmt_date(benefit[0].date)}")
    return 0.6, ev, "Income changed: a buffer, a temporary budget and your rights in order, without stress."


def detect_mobility(ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> Detection | None:
    """An ageing car (rising garage bills) or a car lease that has ended."""
    year = _recent(ctx, 365)
    bills = sorted((t for t in year if is_garage(t) and t.amount <= -250), key=lambda t: t.date)
    score, ev = 0.0, []
    total = -sum(t.amount for t in bills)
    if len(bills) >= 2 and total >= 1200:
        score += 0.45
        ev.append(f"{len(bills)} garage bills of {fmt_eur(total)} in the last year, the latest "
                  f"{fmt_eur(bills[-1].amount)} on {fmt_date(bills[-1].date)}")
        if (ctx.as_of - bills[-1].date).days <= 90:
            score += 0.15
        if len(bills) >= 3 and -bills[-1].amount > -bills[0].amount * 1.3:
            score += 0.1
            ev.append("The repairs are getting more expensive: a sign of an ageing car")
    lease = [t for t in year if t.amount < 0 and any(k in t.counterparty.lower() for k in CAR_LEASE)]
    lease_end = [t for t in lease if "einde" in t.counterparty.lower() or "eindafrekening" in t.counterparty.lower()]
    if lease_end and (ctx.as_of - lease_end[-1].date).days <= 120:
        score += 0.6
        ev.append(f"Final settlement of your car lease with {lease_end[-1].counterparty.split(' (')[0]} on "
                  f"{fmt_date(lease_end[-1].date)}")
    renew = next((r for r in ctx.features.recurring_payments if r.category == "insurance_car"
                  and 0 <= (r.next_date - ctx.as_of).days <= 60), None)
    if score and renew:
        score += 0.05
        ev.append(f"Your car insurance renews around {fmt_date(renew.next_date)}")
    if score < THRESHOLD:
        return None
    return min(score, 1.0), ev, "Compare repairing, an electric car, a lease or sharing, with the numbers from your own payments."


def detect_first_employee(ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> Detection | None:
    """A freelance business that outgrows one person: fast-growing invoice income and/or paying subcontractors."""
    recent, prev, monthly = invoice_growth(ctx.txs, ctx.as_of)
    if prev <= 0 or recent <= 0:
        return None
    score, ev = 0.0, []
    if recent >= 1.4 * prev and monthly >= 5000:
        score += 0.45
        ev.append(f"Invoice income up {round((recent / prev - 1) * 100)}% in the last 4 months, to about "
                  f"{fmt_eur(round(monthly, -1))} a month")
        if monthly >= 8000:
            score += 0.1
    subs = [t for t in _recent(ctx, 120) if is_subcontractor(t)]
    if len(subs) >= 2:
        score += 0.25
        ev.append(f"{len(subs)} payments to subcontractors since {fmt_date(subs[0].date)}, "
                  f"{fmt_eur(-sum(t.amount for t in subs))} in total")
    clients = {t.counterparty for t in _recent(ctx, 180) if t.category == "invoice_income"}
    if subs and score and len(clients) >= 5:
        score += 0.1
        ev.append(f"{len(clients)} clients in the last 6 months")
    if score < THRESHOLD:
        return None
    return min(score, 1.0), ev, "More work than one person can do: try flexible help first, insured and paid correctly."


def detect_inheritance(ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> Detection | None:
    hits = [t for t in _recent(ctx, 180) if is_inheritance(t) and t.amount >= 20000]
    if not hits:
        return None
    t = hits[-1]
    return 0.8, [f"{fmt_eur(t.amount)} from {t.counterparty.split(' (')[0]}'s estate account on {fmt_date(t.date)}",
                 "That looks like an inheritance"], \
        "Take your time. KBC parks the money safely, keeps the papers and helps you decide."


def detect_study_start(ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> Detection | None:
    """A parent (38+) pays a university or college tuition fee: a child is starting or continuing higher education."""
    if ctx.features.age < 38:
        return None
    fees = [t for t in _recent(ctx, 120) if t.category == "tuition" and t.amount <= -250]
    if not fees:
        return None
    return 0.6, [f"{fmt_eur(fees[-1].amount)} tuition to {fees[-1].counterparty.split(' (')[0]} on "
                 f"{fmt_date(fees[-1].date)}"], \
        "Tuition, a student room and a first own account, organised in one go."


DETECTORS: dict[str, Callable[[CustomerContext, list[DeclaredSignalRow]], Detection | None]] = {
    "buy_home": detect_buy_home,
    "energy_upgrade": detect_energy_upgrade,
    "new_baby": detect_new_baby,
    "go_freelance": detect_go_freelance,
    "get_paid": detect_get_paid,
    "retire_well": detect_retire_well,
    "travel": detect_travel,
    "peace_of_mind": detect_peace_of_mind,
    "job_change": detect_job_change,
    "mobility": detect_mobility,
    "first_employee": detect_first_employee,
    "inheritance": detect_inheritance,
    "study_start": detect_study_start,
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
