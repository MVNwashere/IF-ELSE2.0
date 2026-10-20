"""Journey step 1 and 2: recognise an emerging goal and understand why, from the customer's own signals.

Pure functions: CustomerContext (+ what the customer told Kate) → candidate goals with a confidence and
plain-language evidence. Transparent rules by design (like the persona scoring), so every candidate can answer
"why am I seeing this?". Nothing happens until the customer taps Start.
"""
from __future__ import annotations

import datetime as dt
from typing import Callable

from ..engine.cards import gen_late_client, gen_new_payee
from ..engine.features import fmt_date, fmt_eur
from ..schemas import DeclaredSignalRow
from .context import (
    BAILIFF, BONUS, BUSINESS_TRANSFER, CAR_LEASE, CARE, CARE_HOME, EV_CHARGING, FAILED_DEBIT, FARM_AUCTION,
    FARM_SUPPLIER, FUEL, INSURER_REFUND, JEWELLER, KBO_REGISTRATION, NEW_CONTRACT, PARTNER_CONTRIBUTION,
    PROPERTY_SEARCH, REMOVALS, RENT_DEPOSIT, SEPARATION, SIDE_JOB, TRAVEL_MERCHANTS, WEDDING, CustomerContext,
    foreign_country, freelance_estimate, has_any, invoice_growth, is_bnpl, is_garage, is_inheritance,
    is_subcontractor, landlord, private_business_expenses,
)

THRESHOLD = 0.5
IDLE_MONTHS = 8           # a current-account balance of 8+ months of spending: money left idle
SEARCH_STALE_DAYS = 90    # a property search alert that stopped this long ago is an abandoned (or paused) search
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
    if any(t.category == "rent" and t.amount > 0 for t in _recent(ctx, 365)):
        return None   # receives rent: a landlord who already owns property, even when browsing Immoweb
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
    # abandoned search: the alert stopped more than SEARCH_STALE_DAYS ago. We still ask once ("still looking?") at
    # the threshold, never more: detect() is pure, so "once" comes from the nudge rule (each topic once) and the
    # window ends when the search falls out of the 200-day look-back.
    stale = bool(search) and (ctx.as_of - search[-1].date).days > SEARCH_STALE_DAYS
    if search and not stale:
        score += 0.35
        ev.append(f"A property search alert ({search[0].counterparty}) since {fmt_date(search[0].date)}")
    elif stale:
        score += 0.1
        ev.append(f"Your property search alert ({search[-1].counterparty}) stopped after {fmt_date(search[-1].date)}")
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
    if not (search or inspection or deposit):
        return None   # rent, a salary and saving alone describe most savers: a house-specific signal is required
    if stale and not deposit:
        return THRESHOLD, ev, "Still looking for a house? If you are, KBC can line up every step; if not, we'll stop asking."
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
    spiked = False
    if util:
        amounts = sorted(-t.amount for t in util)
        median = amounts[len(amounts) // 2]
        spike = max(util, key=lambda t: -t.amount)
        if -spike.amount >= max(3 * median, 300) and (ctx.as_of - spike.date).days <= 150:
            score += 0.45
            spiked = True
            ev.append(f"An energy bill of {fmt_eur(spike.amount)} from {spike.counterparty.split(' (')[0]} on "
                      f"{fmt_date(spike.date)}, about {round(-spike.amount / median)}× your usual bill")
    if score < THRESHOLD or not spiked:
        return None   # owning a (new) home alone is not an energy intent: the bill shock is what makes it one
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
    d = _declared(declared, "going_freelance")
    if invoices and salary_continues(ctx, invoices[0].date) and not d:
        return None   # the salary still comes in after the first invoice: a side business (side_job), not a switch
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
    recent = _recent(ctx, 90)
    refunds = [t for t in recent if t.amount > 0 and any(m in t.counterparty.lower() for m in TRAVEL_MERCHANTS)]

    def refunded(trip) -> bool:   # a cancelled booking: the same merchant paid (most of) it back
        merchant = trip.counterparty.lower().split(" (")[0]
        return any(r.date >= trip.date and merchant in r.counterparty.lower() and r.amount >= -trip.amount * 0.8
                   for r in refunds)
    trips = [t for t in _recent(ctx, 45) if t.amount <= -250
             and any(m in t.counterparty.lower() for m in TRAVEL_MERCHANTS) and not refunded(t)]
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


def salary_continues(ctx: CustomerContext, since: dt.date) -> bool:
    """A salary was paid after `since` (e.g. after the first invoice): the job goes on."""
    return any(t.category == "salary" and t.amount > 0 and t.date > since for t in ctx.txs)


JOB_LOSS_EVIDENCE = "No new salary or other work income since"


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
    ev = [f"Your salary from {emp} stopped after {fmt_date(last)}", JOB_LOSS_EVIDENCE]
    benefit = [t for t in after if t.category == "benefit"]
    if benefit:
        ev.append(f"A benefit payment from {_employer(benefit[0].counterparty)} on {fmt_date(benefit[0].date)}")
    return 0.6, ev, "Income changed: a buffer, a temporary budget and your rights in order, without stress."


def detect_mobility(ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> Detection | None:
    """An ageing car (rising garage bills) or a car lease that has ended."""
    year = _recent(ctx, 365)
    refunds = [t for t in year if t.amount > 0 and (has_any(t, INSURER_REFUND) or t.category == "insurance_car")]

    def refunded(bill) -> bool:   # an accident repair the insurer paid back is not an ageing car
        return any(0 <= (r.date - bill.date).days <= 60 and r.amount >= -bill.amount * 0.5 for r in refunds)
    bills = sorted((t for t in year if is_garage(t) and t.amount <= -250 and not refunded(t)), key=lambda t: t.date)
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
    # growth alone is a good quarter, not a staffing need: it takes paying others for work as well
    score, ev = 0.0, []
    if recent >= 1.4 * prev and monthly >= 5000:
        score += 0.3
        ev.append(f"Invoice income up {round((recent / prev - 1) * 100)}% in the last 4 months, to about "
                  f"{fmt_eur(round(monthly, -1))} a month")
        if monthly >= 8000:
            score += 0.1
    elif monthly >= 5000:
        score += 0.15
        ev.append(f"Invoice income of about {fmt_eur(round(monthly, -1))} a month")
    subs = [t for t in _recent(ctx, 120) if is_subcontractor(t)]
    if len(subs) >= 2:
        score += 0.35
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


# ---- detectors for the life-event and business goals --------------------------------------------------------------


def _first(txs):
    return min(txs, key=lambda t: t.date)


def _last(txs):
    return max(txs, key=lambda t: t.date)


def _cp(t) -> str:
    return t.counterparty.split(" (")[0]


def detect_side_job(ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> Detection | None:
    """Invoices next to a salary that keeps coming, with the paperwork of a side business (bijberoep): a KBO
    registration or social contributions. One invoice without that paperwork is left alone (could be a one-off)."""
    invoices = sorted((t for t in ctx.txs if t.category == "invoice_income" and t.amount > 0), key=lambda t: t.date)
    if not invoices or (ctx.as_of - invoices[0].date).days > 365 or not salary_continues(ctx, invoices[0].date):
        return None
    first = invoices[0]
    lo = first.date - dt.timedelta(days=120)
    kbo = [t for t in ctx.txs if t.date >= lo and t.amount < 0 and has_any(t, KBO_REGISTRATION)]
    social = [t for t in ctx.txs if t.date >= lo and t.category == "social_contribution" and t.amount < 0]
    if not kbo and not social:
        return None
    clients = len({t.counterparty for t in invoices})
    score = 0.45
    ev = [f"First client payment on {fmt_date(first.date)}; {len(invoices)} invoice{'s' if len(invoices) != 1 else ''} "
          f"from {clients} client{'s' if clients != 1 else ''}, {fmt_eur(sum(t.amount for t in invoices))} in total",
          "Your salary keeps coming in next to it"]
    if kbo:
        score += 0.2
        ev.append(f"You registered at the enterprise counter on {fmt_date(kbo[0].date)}")
    if social:
        score += 0.2
        side = any(has_any(t, SIDE_JOB) for t in social)
        ev.append(f"Social contributions to {_cp(social[0])}" + (" for a side business" if side else "")
                  + f" since {fmt_date(social[0].date)}")
    return min(score, 1.0), ev, "A side business next to your job: keep it separate, invoice correctly and know what you'll owe."


def detect_go_international(ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> Detection | None:
    """Client payments from abroad (a country-tagged payer), new in the last year or a growing share of income."""
    year = [t for t in _recent(ctx, 365) if t.category == "invoice_income" and t.amount > 0]
    foreign = [(t, c) for t in year if (c := foreign_country(t))]
    recent = sorted(((t, c) for t, c in foreign if (ctx.as_of - t.date).days <= 180), key=lambda x: x[0].date)
    if not recent:
        return None
    score = 0.35 if len(recent) == 1 else 0.45
    countries = sorted({c for _, c in recent})
    latest = recent[-1][0]
    ev = [f"{len(recent)} payment{'s' if len(recent) != 1 else ''} from clients abroad ({', '.join(countries)}) in the "
          f"last 6 months, the latest {fmt_eur(latest.amount)} from {_cp(latest)} on {fmt_date(latest.date)}"]
    older = [t for t in ctx.txs if t.date <= ctx.as_of - dt.timedelta(days=365) and foreign_country(t)]
    if not older:
        score += 0.15
        ev.append("Your first foreign clients: new this year")
    total = sum(t.amount for t in year if (ctx.as_of - t.date).days <= 180)
    share = sum(t.amount for t, _ in recent) / total if total else 0.0
    if share >= 0.25:
        score += 0.15
        ev.append(f"{round(share * 100)}% of your client income in the last 6 months came from abroad")
    if len(countries) >= 2:
        score += 0.1
    if score < THRESHOLD:
        return None
    return min(score, 1.0), ev, "Clients abroad: invoice them right, get paid in their currency and avoid VAT surprises."


def detect_care_parent(ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> Detection | None:
    """A customer of 40–67 pays a care home or home care: an ageing parent who needs care."""
    if not 40 <= ctx.features.age <= 67:
        return None
    care = [t for t in _recent(ctx, 120) if t.amount < 0 and has_any(t, CARE)]
    if not care:
        return None
    score = 0.3 if len(care) == 1 else 0.5
    last = _last(care)
    ev = [f"{len(care)} payment{'s' if len(care) != 1 else ''} to {_cp(last)} since {fmt_date(_first(care).date)}, "
          f"the latest {fmt_eur(last.amount)} on {fmt_date(last.date)}"]
    if any(has_any(t, CARE_HOME) and t.amount <= -1000 for t in care):
        score += 0.2
        ev.append("That looks like a care home: a big monthly cost for the family")
    earliest = min(t.date for t in ctx.txs if t.amount < 0 and has_any(t, CARE))
    if (ctx.as_of - earliest).days <= 180:
        score += 0.15
        ev.append(f"New since {fmt_date(earliest)}")
    if score < THRESHOLD:
        return None
    return min(score, 1.0), ev, "Care for your parent organised and paid for, without draining your own savings."


def _rent_months(ctx: CustomerContext, days: int) -> dict[tuple[int, int], set[str]]:
    """(year, month) → landlords paid rent that month (deposits left out)."""
    by: dict[tuple[int, int], set[str]] = {}
    for t in _recent(ctx, days):
        if t.category == "rent" and t.amount <= -300 and not has_any(t, RENT_DEPOSIT):
            by.setdefault((t.date.year, t.date.month), set()).add(landlord(t))
    return by


def detect_move_house(ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> Detection | None:
    """A rent deposit, a removal company, two rents in one month or new utility contracts: moving house.
    A higher rent to the same landlord (indexation) is not a move."""
    recent = _recent(ctx, 120)
    score, ev = 0.0, []
    deposit = [t for t in recent if t.amount <= -500 and has_any(t, RENT_DEPOSIT)]
    if deposit:
        score += 0.45
        ev.append(f"A rent deposit of {fmt_eur(deposit[-1].amount)} ({_cp(deposit[-1])}) on {fmt_date(deposit[-1].date)}")
    removal = [t for t in recent if t.amount < 0 and has_any(t, REMOVALS)]
    if removal:
        score += 0.25
        ev.append(f"{fmt_eur(removal[-1].amount)} to {_cp(removal[-1])} on {fmt_date(removal[-1].date)}")
    double = sorted(m for m, lords in _rent_months(ctx, 120).items() if len(lords) >= 2)
    if double:
        y, m = double[-1]
        score += 0.25
        ev.append(f"Two rents in {dt.date(y, m, 1):%B %Y}: the old and the new home overlap")
    contracts = [t for t in recent if t.category == "utilities" and has_any(t, NEW_CONTRACT)]
    if contracts:
        score += 0.15
        ev.append(f"A new energy contract with {_cp(contracts[0])} on {fmt_date(contracts[0].date)}")
    if score < THRESHOLD:
        return None
    return min(score, 1.0), ev, "Moving: deposit, insurance, energy, address changes and your old deposit back, in one list."


def detect_sell_business(ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> Detection | None:
    """An established business owner of 55+ paying a business valuer or a transfer lawyer. "Established": invoices
    for at least a year (our window on older history can be short, so we don't demand more than we can see)."""
    if ctx.features.age < 55:
        return None
    invoices = [t for t in ctx.txs if t.category == "invoice_income" and t.amount > 0]
    if not invoices or (ctx.as_of - _first(invoices).date).days < 365 or \
            not any((ctx.as_of - t.date).days <= 180 for t in invoices):
        return None
    years = (ctx.as_of - _first(invoices).date).days // 365
    score, ev = 0.3, [f"You're {ctx.features.age} and have run your business for at least {years} "
                      f"year{'s' if years != 1 else ''}"]
    if ctx.features.age >= 60:
        score += 0.05
    advice = [t for t in _recent(ctx, 365) if t.amount < 0 and has_any(t, BUSINESS_TRANSFER)]
    if advice:
        score += 0.4
        ev.append(f"{fmt_eur(advice[-1].amount)} to {_cp(advice[-1])} on {fmt_date(advice[-1].date)}: "
                  "a valuation or transfer adviser")
    if _declared(declared, "retiring"):
        score += 0.2
        ev.insert(0, "You told Kate you're planning to retire")
    if score < THRESHOLD:
        return None
    return min(score, 1.0), ev, "Hand over your business at the right price, and turn the proceeds into your pension."


def detect_back_on_track(ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> Detection | None:
    """Money trouble building up: more buy-now-pay-later, failed direct debits, a bailiff. Help, not a sales pitch."""
    mid = ctx.as_of - dt.timedelta(days=90)
    now = [t for t in ctx.txs if t.date > mid]
    before = [t for t in ctx.txs if mid - dt.timedelta(days=90) < t.date <= mid]
    score, ev = 0.0, []
    bnpl = [t for t in now if is_bnpl(t)]
    bnpl_before = [t for t in before if is_bnpl(t)]
    if len(bnpl) >= 3:
        score += 0.25
        ev.append(f"{len(bnpl)} buy-now-pay-later instalments in 3 months ({fmt_eur(sum(t.amount for t in bnpl))})")
        if len(bnpl) >= 1.5 * max(len(bnpl_before), 1):
            score += 0.15
            ev.append(f"Up from {len(bnpl_before)} in the 3 months before")
    failed = [t for t in now if has_any(t, FAILED_DEBIT)]
    if failed:
        score += 0.35 if len(failed) >= 2 else 0.25
        ev.append(f"{len(failed)} direct debit{'s' if len(failed) != 1 else ''} bounced, the latest on "
                  f"{fmt_date(_last(failed).date)}")
    bailiff = [t for t in _recent(ctx, 120) if t.amount < 0 and has_any(t, BAILIFF)]
    if bailiff:
        score += 0.45
        ev.append(f"A payment to {_cp(bailiff[-1])} on {fmt_date(bailiff[-1].date)}")
    if score and ctx.features.balance_eur < 0:
        score += 0.15
        ev.append(f"Your account is {fmt_eur(ctx.features.balance_eur)} in the red")
    if score < THRESHOLD:
        return None
    return min(score, 1.0), ev, "A calm plan: what's due when, what can wait, and who can help. No judgement, no sales."


def detect_farm_growth(ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> Detection | None:
    """A farm: produce sold through an auction (veiling) plus farm-supplier spending; growing when spending rises."""
    year = _recent(ctx, 365)
    auction = [t for t in year if t.category == "invoice_income" and t.amount > 0 and has_any(t, FARM_AUCTION)]
    supply = [t for t in year if t.amount < 0 and has_any(t, FARM_SUPPLIER)]
    score, ev = 0.0, []
    if len(auction) >= 2:
        score += 0.4
        ev.append(f"{len(auction)} payments from {_cp(_last(auction))} in the last year "
                  f"({fmt_eur(sum(t.amount for t in auction))})")
    if len(supply) >= 3:
        score += 0.2
        ev.append(f"{len(supply)} payments to farm suppliers such as {_cp(_last(supply))}")
    if score and any("boerenbond" in t.counterparty.lower() for t in supply):
        score += 0.1
    mid = ctx.as_of - dt.timedelta(days=120)
    recent = -sum(t.amount for t in supply if t.date > mid)
    prev = -sum(t.amount for t in supply if mid - dt.timedelta(days=120) < t.date <= mid)
    big = sorted((t for t in supply if t.amount <= -5000), key=lambda t: t.date)
    if score and (big or (prev > 0 and recent >= 1.4 * prev)):
        score += 0.15
        ev.append(f"An investment of {fmt_eur(big[-1].amount)} on {fmt_date(big[-1].date)}" if big
                  else f"Supplier spending up {round((recent / prev - 1) * 100)}% in the last 4 months")
    if score < THRESHOLD:
        return None
    return min(score, 1.0), ev, "Grow the farm with financing for the season, insurance against the weather and less paperwork."


def detect_ev_switch(ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> Detection | None:
    """New public charging sessions (3+ in 4 months, none a year before) or a car lease ending while fuel costs
    are high. One charge on a holiday is not a switch."""
    charging = [t for t in ctx.txs if t.category == "transport" and t.amount < 0 and has_any(t, EV_CHARGING)]
    recent = [t for t in charging if (ctx.as_of - t.date).days <= 120]
    score, ev = 0.0, []
    if len(recent) >= 3 and (ctx.as_of - _first(charging).date).days <= 365:
        score += 0.5
        ev.append(f"{len(recent)} charging sessions since {fmt_date(_first(recent).date)} "
                  f"({', '.join(sorted({_cp(t) for t in recent}))})")
        if (ctx.as_of - _first(charging).date).days <= 120:
            score += 0.1
            ev.append("New: no charging before that")
    lease_end = [t for t in _recent(ctx, 120) if t.amount < 0 and any(k in t.counterparty.lower() for k in CAR_LEASE)
                 and ("einde" in t.counterparty.lower() or "eindafrekening" in t.counterparty.lower())]
    fuel = -sum(t.amount for t in _recent(ctx, 90) if t.amount < 0 and has_any(t, FUEL)) / 3
    if lease_end and fuel >= 150:
        score += 0.5
        ev.append(f"Your car lease ended on {fmt_date(lease_end[-1].date)} and fuel costs you about "
                  f"{fmt_eur(round(fuel, -1))} a month")
    if score < THRESHOLD:
        return None
    return min(score, 1.0), ev, "Switch to electric with the numbers: the car, a home charger, the energy contract and the insurance."


def detect_first_investment(ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> Detection | None:
    """A young earner with a growing cushion and no investments yet. Not when they're saving for a house."""
    f = ctx.features
    if not 24 <= f.age <= 38 or not f.has_salary or "investment_plan" in ctx.holdings:
        return None
    if any(t.category == "property" and any(p in t.counterparty.lower() for p in PROPERTY_SEARCH)
           for t in _recent(ctx, 200)):
        return None   # saving with a property search: that's buy_home
    if any(is_inheritance(t) for t in _recent(ctx, 180)):
        return None   # an inheritance: its own journey (take your time, then invest) covers this
    if any(t.amount >= 20000 and ("notari" in t.counterparty.lower() or "notaire" in t.counterparty.lower())
           for t in _recent(ctx, 180)):
        return None   # proceeds from a property sale: usually the next home, not a first portfolio
    spend = max(f.monthly_spend_avg_90d, 500.0)
    saved = -sum(t.amount for t in _recent(ctx, 365) if t.category == "savings_transfer" and t.amount < 0)
    cushion = saved + max(0.0, f.balance_eur - 2 * spend)
    months = cushion / spend
    if months < 6:
        return None
    score = 0.1 + (0.4 if months >= 10 else 0.3)
    ev = [f"About {fmt_eur(round(cushion, -2))} put aside, roughly {round(months)} months of spending"]
    bonus = [t for t in _recent(ctx, 365) if t.category == "salary" and t.amount > 0 and has_any(t, BONUS)]
    # idle money on top of a savings habit; without a savings account yet, the first step is saving, not investing
    idle = "savings" in ctx.holdings and f.balance_eur >= IDLE_MONTHS * spend
    if not bonus and not idle:
        return None   # a steady saving habit alone is not an intent: it takes a windfall or money left idle
    if bonus:
        score += 0.2
        ev.append(f"A bonus of {fmt_eur(bonus[-1].amount)} on {fmt_date(bonus[-1].date)}")
    if idle:
        score += 0.1
        ev.append(f"{fmt_eur(round(f.balance_eur, -2))} on your current account, earning nothing")
    ev.append("No investments yet: everything sits on savings and current accounts")
    if score < THRESHOLD:
        return None
    return min(score, 1.0), ev, "Keep a buffer, then let the rest grow: small, spread and at your own pace."


def detect_together(ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> Detection | None:
    """Moving in together (a partner chips in for the rent) or getting married (town hall, venue, rings).
    One jewellery purchase on its own is a present, not a wedding."""
    score, ev = 0.0, []
    chip_in = [t for t in _recent(ctx, 180) if t.amount > 0 and t.category == "other" and has_any(t, PARTNER_CONTRIBUTION)]
    if len(chip_in) >= 2:
        score += 0.45
        ev.append(f"{_cp(chip_in[-1])} has transferred {fmt_eur(sum(t.amount for t in chip_in))} towards the "
                  f"rent since {fmt_date(_first(chip_in).date)}")
        if not any(t.amount > 0 and has_any(t, PARTNER_CONTRIBUTION) and (ctx.as_of - t.date).days > 180
                   for t in ctx.txs):
            score += 0.15
    wedding = [t for t in _recent(ctx, 365) if t.amount < 0 and has_any(t, WEDDING)]
    if wedding:
        score += 0.4 if len(wedding) == 1 else 0.5
        ev.append(f"{fmt_eur(sum(t.amount for t in wedding))} on the wedding "
                  f"({', '.join(sorted({_cp(t) for t in wedding}))})")
    rings = [t for t in _recent(ctx, 365) if t.amount < 0 and has_any(t, JEWELLER)]
    if rings and score:
        score += 0.1
        ev.append(f"{fmt_eur(rings[-1].amount)} at {_cp(rings[-1])} on {fmt_date(rings[-1].date)}")
    if score < THRESHOLD:
        return None
    return min(score, 1.0), ev, "Sharing life and money: a joint account, the right insurance and who owns what, sorted."


def detect_separation(ctx: CustomerContext, declared: list[DeclaredSignalRow]) -> Detection | None:
    """A divorce lawyer or mediator, a second home while the first is still paid, a partner's inflow that stopped.
    A lawyer for something else (a traffic fine) doesn't count."""
    score, ev = 0.0, []
    legal = [t for t in _recent(ctx, 180) if t.amount < 0 and has_any(t, SEPARATION)]
    if legal:
        score += 0.45
        ev.append(f"{fmt_eur(legal[-1].amount)} to {_cp(legal[-1])} on {fmt_date(legal[-1].date)}")
    recent_lords = {lord for lords in _rent_months(ctx, 180).values() for lord in lords}
    old_lords = {lord for (y, m), lords in _rent_months(ctx, 540).items()
                 if (ctx.as_of - dt.date(y, m, 1)).days > 180 for lord in lords}
    new_lords = recent_lords - old_lords
    mortgage_paid = any(t.category == "mortgage" for t in _recent(ctx, 45))
    if new_lords and (mortgage_paid or old_lords & recent_lords):
        score += 0.3
        ev.append("A second home: a new rent while your current home is still being paid")
    chip_in = sorted((t for t in ctx.txs if t.amount > 0 and has_any(t, PARTNER_CONTRIBUTION)), key=lambda t: t.date)
    if len(chip_in) >= 3 and 45 <= (ctx.as_of - chip_in[-1].date).days <= 240:
        score += 0.25
        ev.append(f"The regular transfers from {_cp(chip_in[-1])} stopped after {fmt_date(chip_in[-1].date)}")
    if score < THRESHOLD:
        return None
    return min(score, 1.0), ev, "A difficult time. Split the accounts, the loan and the insurance fairly, step by step."


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
    "side_job": detect_side_job,
    "go_international": detect_go_international,
    "care_parent": detect_care_parent,
    "move_house": detect_move_house,
    "sell_business": detect_sell_business,
    "back_on_track": detect_back_on_track,
    "farm_growth": detect_farm_growth,
    "ev_switch": detect_ev_switch,
    "first_investment": detect_first_investment,
    "together": detect_together,
    "separation": detect_separation,
}

# Commercial goals are not proposed while the customer is in trouble (job loss, arrears); help goals stay.
COMMERCIAL = ("first_investment", "travel", "buy_home", "go_international", "ev_switch", "together")
Suppressed = tuple[str, str]   # playbook id, reason
STARTING_BUSINESS = ("go_freelance", "side_job")


def _trouble(hits: dict[str, Detection]) -> str | None:
    if "back_on_track" in hits:
        return "There are signs of money trouble (bounced debits, buy-now-pay-later or a bailiff)"
    job = hits.get("job_change")
    if job and JOB_LOSS_EVIDENCE in job[1]:
        return "Your salary stopped without a new income"
    return None


def detect_with_suppressed(ctx: CustomerContext, declared: list[DeclaredSignalRow] | None = None
                           ) -> tuple[list[tuple[str, Detection]], list[Suppressed]]:
    """(candidates, most confident first; goals that fired but are held back, with the reason)."""
    hits: dict[str, Detection] = {}
    for playbook_id, fn in DETECTORS.items():
        hit = fn(ctx, declared or [])
        if hit:
            hits[playbook_id] = (round(min(hit[0], 1.0), 2), hit[1], hit[2])
    suppressed: list[Suppressed] = []
    reason = _trouble(hits)
    if reason:
        for pid in COMMERCIAL:
            if hits.pop(pid, None):
                suppressed.append((pid, f"{reason}: not the moment for this, so KBC doesn't propose it now"))
    # a new business needs its buffer first: investing waits until the business runs (one goal at a time)
    starting = next((pid for pid in STARTING_BUSINESS if pid in hits), None)
    if starting and hits.pop("first_investment", None):
        suppressed.append(("first_investment", "You're starting a business: keep a buffer for it first, "
                                               "investing can wait"))
    return sorted(hits.items(), key=lambda x: -x[1][0]), suppressed


def detect(ctx: CustomerContext, declared: list[DeclaredSignalRow] | None = None) -> list[tuple[str, Detection]]:
    """All playbooks whose rule fires, most confident first. Commercial goals are suppressed in hard times
    (see detect_with_suppressed for what was held back and why)."""
    return detect_with_suppressed(ctx, declared)[0]
