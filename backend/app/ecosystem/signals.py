"""Time-based and freelance signals derived from a CustomerContext: deadlines and forecasts.

Contract (consumed by nudges.py and the journeys; owned by the signals work):

    upcoming_deadlines(ctx, horizon_days=45) -> list[Deadline]   # sorted by date
    forecasts(ctx) -> list[Forecast]                             # e.g. the social-contribution regularisation gap

Pure functions, no I/O. Amounts are illustrative estimates from the customer's own data. Belgian rules and dates
below are encoded as we understand them and are marked "verify": they must be checked before going on a slide.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from ..engine.features import VAT_DUE_DAY, fmt_date, fmt_eur
from .context import (
    ADVANCE_TAX_DATES, STARTER_PROVISIONAL_QUARTER, TRAVEL_MERCHANTS, VAT_RATE, CustomerContext, freelance_estimate,
    private_business_expenses,
)

PENSION_SAVINGS_CEILING = 1050.0     # tax-advantaged yearly pension-savings ceiling (2025 basic amount; verify 2026)
PENSION_SAVINGS_SEASON = (11, 12)    # only remind in November and December
CLIENT_CONCENTRATION = 0.70          # one client above 70% of invoice income
TRIP_LEAD_DAYS = 30                  # departure estimated a month after the booking (no itinerary data)
INSURANCE_PLAYBOOK = {"insurance_car": "mobility", "insurance_family": "new_baby", "insurance_home": None}


@dataclass
class Deadline:
    kind: str                 # "vat_return" | "advance_tax" | "social_contribution" | "insurance_renewal" | "pension_savings" | "trip"
    date: dt.date
    title: str                # "Q3 VAT return"
    amount_eur: float | None = None
    shortfall_eur: float | None = None   # money missing for this deadline, if any (drives urgency)
    evidence: list[str] = field(default_factory=list)
    playbook_id: str | None = None       # the goal that takes care of it, if any
    verify: bool = False                 # rule or amount still to be verified before it goes on a slide


@dataclass
class Forecast:
    kind: str                 # "social_contribution_regularisation" | "client_concentration" | "private_business_expenses"
    title: str
    amount_eur: float | None = None
    due: dt.date | None = None
    evidence: list[str] = field(default_factory=list)
    playbook_id: str | None = None
    illustrative: bool = True            # an estimate from the customer's own data, labelled as such


# ---- helpers ---------------------------------------------------------------------------------------------------------


def _quarter_bounds(year: int, q: int) -> tuple[dt.date, dt.date, dt.date]:
    """(start, end, VAT due date) of quarter q (1–4)."""
    start = dt.date(year, 3 * (q - 1) + 1, 1)
    end = dt.date(year + (q == 4), 1 if q == 4 else 3 * q + 1, 1) - dt.timedelta(days=1)
    due_month_start = end + dt.timedelta(days=1)
    return start, end, dt.date(due_month_start.year, due_month_start.month, VAT_DUE_DAY)


def _freelance_playbook(ctx: CustomerContext) -> str:
    return "get_paid" if "business_account" in ctx.holdings else "go_freelance"


def _spare_cash(ctx: CustomerContext) -> float:
    """Balance above one month of spending: what could cover a bill without touching the monthly budget."""
    return max(0.0, ctx.features.balance_eur - max(ctx.features.monthly_spend_avg_90d, 500.0))


# ---- deadlines -------------------------------------------------------------------------------------------------------


def _vat_deadlines(ctx: CustomerContext) -> list[Deadline]:
    """Quarterly VAT returns (20th of the month after the quarter; verify) with VAT not yet paid over."""
    as_of, txs = ctx.as_of, ctx.txs
    if not any(t.category == "invoice_income" for t in txs if (as_of - t.date).days <= 400):
        return []
    q_now = (as_of.month - 1) // 3 + 1
    prev = (as_of.year - (q_now == 1), 4 if q_now == 1 else q_now - 1)
    out = []
    for year, q in (prev, (as_of.year, q_now)):
        start, end, due = _quarter_bounds(year, q)
        if due < as_of:
            continue
        invoiced = sum(t.amount for t in txs if t.category == "invoice_income" and start <= t.date <= min(end, as_of))
        if invoiced <= 0:
            continue
        paid = any(t.category == "vat_payment" and end < t.date <= as_of for t in txs)
        if paid:
            continue
        vat = round(invoiced * VAT_RATE, 2)   # same convention as the v1 VAT-reserve card
        running = end >= as_of
        ev = [f"{fmt_eur(invoiced)} invoiced in Q{q} {year}{' so far' if running else ''}",
              f"About {fmt_eur(vat)} VAT to declare and pay by {fmt_date(due)}"]
        shortfall = round(max(0.0, vat - _spare_cash(ctx)), 2)
        if shortfall:
            ev.append(f"Only {fmt_eur(_spare_cash(ctx))} spare on your account after a month of spending")
        out.append(Deadline(kind="vat_return", date=due, title=f"Q{q} {year} VAT return", amount_eur=vat,
                            shortfall_eur=shortfall, evidence=ev, playbook_id=_freelance_playbook(ctx), verify=True))
    return out


def _advance_tax_deadlines(ctx: CustomerContext) -> list[Deadline]:
    """Advance tax payments for the self-employed (10 Apr, 10 Jul, 10 Oct, 20 Dec; verify the yearly calendar).

    Starters may be exempt from the surcharge for not paying in advance in their first three years (verify), but an
    advance payment still spreads the bill. Suggested amount: a quarter of the illustrative yearly income tax."""
    fe = freelance_estimate(ctx.txs, ctx.as_of)
    if not fe or (ctx.as_of - max(t.date for t in ctx.txs if t.category == "invoice_income")).days > 180:
        return []
    out = []
    for year in (ctx.as_of.year, ctx.as_of.year + 1):
        for m, d in ADVANCE_TAX_DATES:
            due = dt.date(year, m, d)
            if due < ctx.as_of:
                continue
            amount = round(fe.income_tax_year_eur / 4, -1)
            ev = [f"Invoices paid in so far point to about {fmt_eur(fe.income_tax_year_eur)} income tax a year "
                  "(illustrative estimate)",
                  "Without advance payments the self-employed usually pay a tax surcharge"
                  + (" (starters may be exempt in their first three years; verify)" if fe.starter else "")]
            out.append(Deadline(kind="advance_tax", date=due, title=f"Advance tax payment {fmt_date(due)}",
                                amount_eur=amount, evidence=ev, playbook_id=_freelance_playbook(ctx), verify=True))
    return out


def _social_contribution_deadlines(ctx: CustomerContext) -> list[Deadline]:
    """A starter's provisional social contribution, due by the end of each quarter (verify)."""
    fe = freelance_estimate(ctx.txs, ctx.as_of)
    if not fe or not fe.starter:
        return []
    paid = [t for t in ctx.txs if t.category == "social_contribution"]
    if paid and (ctx.as_of - paid[-1].date).days <= 100:
        amount = -paid[-1].amount
        source = f"your last contribution to {paid[-1].counterparty} was {fmt_eur(amount)}"
    else:
        amount = STARTER_PROVISIONAL_QUARTER
        source = f"the provisional minimum for a starter is about {fmt_eur(amount)} a quarter (verify)"
    q = (ctx.as_of.month - 1) // 3 + 1
    _, end, _ = _quarter_bounds(ctx.as_of.year, q)
    ev = [f"You started invoicing on {fmt_date(fe.first_invoice)}",
          f"Provisional social contributions are due each quarter: {source}"]
    return [Deadline(kind="social_contribution", date=end, title=f"Q{q} {ctx.as_of.year} provisional social contribution",
                     amount_eur=round(amount, 2), shortfall_eur=round(max(0.0, amount - _spare_cash(ctx)), 2),
                     evidence=ev, playbook_id=_freelance_playbook(ctx), verify=True)]


def _insurance_deadlines(ctx: CustomerContext) -> list[Deadline]:
    out = []
    for r in ctx.features.recurring_payments:
        if r.period_days != 365 or not r.category.startswith("insurance_"):
            continue
        kind = r.category.removeprefix("insurance_")
        out.append(Deadline(
            kind="insurance_renewal", date=r.next_date, title=f"{kind.capitalize()} insurance renews",
            amount_eur=r.amount_eur,
            evidence=[f"You paid {fmt_eur(r.amount_eur)} to {r.counterparty} on {fmt_date(r.last_date)}",
                      "It looks like a yearly premium, so it renews around the same date"],
            playbook_id=INSURANCE_PLAYBOOK.get(r.category)))
    return out


def _pension_savings_deadlines(ctx: CustomerContext) -> list[Deadline]:
    f = ctx.features
    if ctx.as_of.month not in PENSION_SAVINGS_SEASON or not 18 <= f.age <= 64:
        return []
    deposits = [t for t in ctx.txs if t.date.year == ctx.as_of.year and t.amount < 0
                and ("pensioensparen" in t.counterparty.lower() or "pensioenspaar" in t.counterparty.lower())]
    saver = "pension_savings" in ctx.holdings
    if not saver and not (f.has_salary or f.has_invoice_income):
        return []
    done = -sum(t.amount for t in deposits)
    missing = round(max(0.0, PENSION_SAVINGS_CEILING - done), 2)
    if missing <= 0:
        return []
    ev = [f"{fmt_eur(done)} deposited this year" if saver else "You earn an income but don't save for your pension yet",
          f"Deposits up to about {fmt_eur(PENSION_SAVINGS_CEILING)} a year give a tax reduction (verify the 2026 ceiling)"]
    return [Deadline(kind="pension_savings", date=dt.date(ctx.as_of.year, 12, 31),
                     title="Pension-savings deposit for this tax year", amount_eur=missing,
                     shortfall_eur=missing, evidence=ev, playbook_id="retire_well", verify=True)]


def _trip_deadlines(ctx: CustomerContext) -> list[Deadline]:
    out = []
    for t in ctx.txs:
        if t.amount > -200 or not any(m in t.counterparty.lower() for m in TRAVEL_MERCHANTS):
            continue
        dep = t.date + dt.timedelta(days=TRIP_LEAD_DAYS)
        if dep < ctx.as_of:
            continue
        out.append(Deadline(kind="trip", date=dep, title=f"Trip booked with {t.counterparty.split(' (')[0]}",
                            amount_eur=-t.amount,
                            evidence=[f"{fmt_eur(t.amount)} to {t.counterparty} on {fmt_date(t.date)}",
                                      f"Departure estimated around {fmt_date(dep)} (no itinerary data)"],
                            playbook_id="travel"))
    return out


def upcoming_deadlines(ctx: CustomerContext, horizon_days: int = 45) -> list[Deadline]:
    """Everything with a date between as_of and as_of + horizon_days, soonest first."""
    hi = ctx.as_of + dt.timedelta(days=horizon_days)
    out: list[Deadline] = []
    for gen in (_vat_deadlines, _advance_tax_deadlines, _social_contribution_deadlines, _insurance_deadlines,
                _pension_savings_deadlines, _trip_deadlines):
        out += [d for d in gen(ctx) if ctx.as_of <= d.date <= hi]
    out.sort(key=lambda d: (d.date, d.kind))
    return out


# ---- forecasts -------------------------------------------------------------------------------------------------------


def _regularisation(ctx: CustomerContext) -> Forecast | None:
    fe = freelance_estimate(ctx.txs, ctx.as_of)
    if not fe or not fe.starter or fe.regularisation_gap_eur < 250:
        return None
    return Forecast(
        kind="social_contribution_regularisation",
        title=f"Social-contribution regularisation of about {fmt_eur(round(fe.regularisation_gap_eur, -1))} a year",
        amount_eur=fe.regularisation_gap_eur, due=fe.regularisation_due,
        evidence=[
            f"Invoices paid in so far: {fmt_eur(fe.invoiced_eur)} ({fe.invoices} since {fmt_date(fe.first_invoice)}), "
            f"a run rate of about {fmt_eur(round(fe.monthly_gross_eur, -1))} a month incl. VAT",
            f"Starters pay provisional contributions of about {fmt_eur(fe.provisional_year_eur)} a year; on this "
            f"income about {fmt_eur(round(fe.social_due_year_eur, -1))} would be due (~20.5% of net taxable income, "
            "illustrative; verify)",
            f"The difference is charged about two years later, around {fe.regularisation_due.strftime('%b %Y')}",
        ],
        playbook_id=_freelance_playbook(ctx))


def _client_concentration(ctx: CustomerContext) -> Forecast | None:
    fe = freelance_estimate(ctx.txs, ctx.as_of)
    if not fe or fe.top_client_share <= CLIENT_CONCENTRATION:
        return None
    share = round(fe.top_client_share * 100)
    ev = [f"{share}% of your invoice income in the last year came from {fe.top_client}"]
    if fe.invoices == 1:
        ev.append("So far one client has paid you")
    ev.append("If that client stops or pays late, most of your income stops with it")
    return Forecast(kind="client_concentration", title=f"{share}% of your income depends on one client",
                    amount_eur=round(fe.invoiced_eur * fe.top_client_share, 2), evidence=ev,
                    playbook_id=_freelance_playbook(ctx), illustrative=False)


def _private_expenses(ctx: CustomerContext) -> Forecast | None:
    if "business_account" in ctx.holdings:
        return None
    fe = freelance_estimate(ctx.txs, ctx.as_of)
    if not fe:
        return None
    items = private_business_expenses(ctx.txs, ctx.as_of, fe.first_invoice - dt.timedelta(days=60))
    if not items:
        return None
    total = -sum(t.amount for t in items)
    ev = [f"{fmt_eur(t.amount)} to {t.counterparty} on {fmt_date(t.date)}" for t in items[:3]]
    ev.append("Paid from your private account: keep the invoice so your accountant can deduct it as a business cost")
    return Forecast(kind="private_business_expenses", title="Business purchases on your private account",
                    amount_eur=round(total, 2), evidence=ev, playbook_id="go_freelance", illustrative=False)


def forecasts(ctx: CustomerContext) -> list[Forecast]:
    out = [f for f in (_regularisation(ctx), _client_concentration(ctx), _private_expenses(ctx)) if f]
    return out
