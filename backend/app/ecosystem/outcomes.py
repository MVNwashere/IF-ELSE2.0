"""Journey step 5: measured outcomes. Did the goal deliver, judged by the customer's OWN later transactions?

Pure functions, no I/O:

    measure(goal, txs, as_of, balance_today=None) -> list[MeasuredOutcome]

The playbooks carry estimates; this module checks reality once the steps are done. Each outcome is
`verified` (we see it in the data), `pending` (too early, or no data yet: "we'll check on <date>") or `not_met`.
Time travel: steps carry a simulated completion date (`done_on`), so viewing the goal at a later `as_of` measures
what happened in the data after that date.
"""
from __future__ import annotations

import datetime as dt
import statistics
from typing import Callable, Iterable

from ..engine.features import fmt_date
from ..schemas import Transaction
from .context import TRAVEL_MERCHANTS
from .models import Goal, MeasuredOutcome, Step

DAY = dt.timedelta(days=1)
SAVINGS_RATE = 0.02          # illustrative KBC savings rate vs 0% on a current account
VAT = 21 / 121               # VAT share of an invoice amount incl. VAT
INCOME_TAX_RESERVE = 0.25    # the reserve rule in the go_freelance playbook


def _eur(x: float) -> str:
    return f"€{round(x):,}".replace(",", ".")


def _done(goal: Goal, ids: Iterable[str], include_held: bool = False) -> list[Step]:
    ids = set(ids)
    return [s for s in goal.steps if s.step_id in ids and s.status == "done" and (include_held or not s.already_held)]


def _anchor(goal: Goal, steps: list[Step]) -> dt.date:
    return max((s.done_on or goal.created_on) for s in steps)


def _estimate(steps: list[Step]) -> float | None:
    total = sum(s.estimates.customer_eur for s in steps)
    return round(total, 2) if total else None


def _monthly_spend(txs: list[Transaction], pred: Callable[[Transaction], bool], lo: dt.date, hi: dt.date) -> float:
    """Average monthly spend in (lo, hi], one-off settlement bills (> 2.5× the median) left out."""
    rows = [(t.date, -t.amount) for t in txs if pred(t) and lo < t.date <= hi and t.amount < 0]
    if not rows:
        return 0.0
    med = statistics.median(a for _, a in rows)
    kept = [(d, a) for d, a in rows if a <= 2.5 * med]
    months = {(d.year, d.month) for d, _ in kept}     # per billed month: robust to window edges
    return sum(a for _, a in kept) / max(1, len(months))


# ---- per goal ---------------------------------------------------------------------------------------------------


def _energy(goal: Goal, txs: list[Transaction], as_of: dt.date) -> list[MeasuredOutcome]:
    steps = _done(goal, ("advice", "quotes", "energy_loan", "group_purchase", "solar"))
    if not steps:
        return []
    anchor = _anchor(goal, steps)
    estimate = _estimate(steps)
    util = lambda t: t.category == "utilities"   # noqa: E731
    before = _monthly_spend(txs, util, anchor - 180 * DAY, anchor)
    start = anchor + 60 * DAY      # works and a new contract take a while
    check_on = start + 90 * DAY
    base = dict(metric="energy_spend", label="Energy bill", estimate_eur=estimate, unit="€ a year",
                step_id=steps[-1].step_id)
    ev = [f"Before: {_eur(before)} a month on energy (6 months up to {fmt_date(anchor)})"]
    if as_of < check_on or before <= 0:
        return [MeasuredOutcome(**base, status="pending", check_on=check_on, evidence=ev,
                                summary=f"We'll compare your energy bills on {fmt_date(check_on)}.")]
    after = _monthly_spend(txs, util, max(start, as_of - 120 * DAY), as_of)
    saving = (before - after) * 12
    ev.append(f"After: {_eur(after)} a month (last 4 months up to {fmt_date(as_of)})")
    if saving > 0.05 * before * 12:
        return [MeasuredOutcome(**base, status="verified", measured_eur=round(saving), evidence=ev,
                                summary=f"Your energy bills dropped by about {_eur(saving)} a year.")]
    if as_of < anchor + 365 * DAY:
        nxt = min(as_of + 60 * DAY, anchor + 365 * DAY)
        return [MeasuredOutcome(**base, status="pending", check_on=nxt, evidence=ev,
                                summary=f"No drop yet: works often take a few months. We'll look again on {fmt_date(nxt)}.")]
    return [MeasuredOutcome(**base, status="not_met", measured_eur=round(saving), evidence=ev,
                            summary="A year on, your energy bills have not gone down. Your advisor will call you.")]


def _late_client(txs: list[Transaction], at: dt.date) -> str | None:
    by: dict[str, list[dt.date]] = {}
    for t in txs:
        if t.category == "invoice_income" and t.amount > 0 and t.date <= at:
            by.setdefault(t.counterparty, []).append(t.date)
    best, ratio = None, 1.5
    for cp, dates in by.items():
        if len(dates) < 3:
            continue
        gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
        r = (at - dates[-1]).days / max(statistics.median(gaps), 1)
        if r >= ratio:
            best, ratio = cp, r
    return best


def _get_paid(goal: Goal, txs: list[Transaction], as_of: dt.date) -> list[MeasuredOutcome]:
    steps = _done(goal, ("reminders", "collection"))
    if not steps:
        return []
    anchor = _anchor(goal, steps)
    client = _late_client(txs, anchor)
    base = dict(metric="client_payments", label=f"Payments from {client or 'your late clients'}",
                estimate_eur=_estimate(steps), step_id=steps[-1].step_id)
    paid = [t for t in txs if t.category == "invoice_income" and t.amount > 0 and anchor < t.date <= as_of
            and (client is None or t.counterparty == client)]
    check_on = anchor + 30 * DAY
    if paid:
        total = sum(t.amount for t in paid)
        return [MeasuredOutcome(**base, status="verified", measured_eur=round(total, 2),
                                evidence=[f"{len(paid)} payment(s) since {fmt_date(anchor)}, first on {fmt_date(paid[0].date)}"],
                                summary=f"Payments resumed: {_eur(total)} received since the reminders.")]
    if as_of < anchor + 60 * DAY:
        return [MeasuredOutcome(**base, status="pending", check_on=max(check_on, as_of + DAY),
                                evidence=[f"No payment from {client or 'the client'} yet since {fmt_date(anchor)}"],
                                summary=f"We'll check your account for their payment on {fmt_date(max(check_on, as_of + DAY))}.")]
    return [MeasuredOutcome(**base, status="not_met", measured_eur=0.0,
                            evidence=[f"No payment from {client or 'the client'} in the 60 days since {fmt_date(anchor)}"],
                            summary="Still no payment. Next step: collection by a specialist.")]


def _quarter_due(d: dt.date) -> tuple[dt.date, dt.date]:
    """(quarter start, VAT return due date: the 20th of the month after the quarter) for the quarter of d."""
    q0 = dt.date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)
    end_month = q0.month + 3
    due = dt.date(d.year + (end_month > 12), (end_month - 1) % 12 + 1, 20)
    return q0, due


def _freelance(goal: Goal, txs: list[Transaction], as_of: dt.date) -> list[MeasuredOutcome]:
    out: list[MeasuredOutcome] = []
    invoices = [t for t in txs if t.category == "invoice_income" and t.amount > 0]
    reserve_steps = _done(goal, ("tax_reserve",))
    if reserve_steps:
        anchor = _anchor(goal, reserve_steps)
        q0, due = _quarter_due(anchor)
        in_q = [t for t in invoices if q0 <= t.date < dt.date(due.year, due.month, 1)]
        vat_due = sum(t.amount for t in in_q) * VAT
        reserved = sum(t.amount * (VAT + (1 - VAT) * INCOME_TAX_RESERVE) for t in in_q if t.date <= as_of)
        base = dict(metric="tax_reserve", label=f"VAT return due {fmt_date(due)}",
                    estimate_eur=_estimate(reserve_steps), step_id="tax_reserve")
        ev = [f"Reserve so far: {_eur(reserved)} from {len([t for t in in_q if t.date <= as_of])} paid invoice(s)",
              f"VAT due this quarter: {_eur(vat_due)}"]
        if as_of < due:
            out.append(MeasuredOutcome(**base, status="pending", check_on=due, evidence=ev,
                                       summary=f"We'll check the reserve covers your VAT on {fmt_date(due)}."))
        elif reserved >= vat_due:
            out.append(MeasuredOutcome(**base, status="verified", measured_eur=round(vat_due, 2), evidence=ev,
                                       summary=f"Your VAT of {_eur(vat_due)} was covered by the reserve: no surprise bill."))
        else:
            out.append(MeasuredOutcome(**base, status="not_met", measured_eur=round(reserved, 2), evidence=ev,
                                       summary=f"The reserve fell {_eur(vat_due - reserved)} short of the VAT due."))
    peppol = _done(goal, ("e_invoicing",))
    if peppol:
        anchor = _anchor(goal, peppol)
        paid = [t for t in invoices if anchor < t.date <= as_of]
        base = dict(metric="peppol_invoices", label="Invoices paid via Peppol", unit="invoices", step_id="e_invoicing")
        if paid:
            out.append(MeasuredOutcome(**base, status="verified", measured_eur=round(sum(t.amount for t in paid), 2),
                                       evidence=[f"{len(paid)} invoice(s) paid since {fmt_date(anchor)}"],
                                       summary=f"{len(paid)} Peppol invoice(s) paid, {_eur(sum(t.amount for t in paid))} in total."))
        else:
            check = max(anchor + 30 * DAY, as_of + DAY)
            out.append(MeasuredOutcome(**base, status="pending", check_on=check,
                                       evidence=[f"No invoice paid yet since {fmt_date(anchor)}"],
                                       summary=f"We'll count your paid Peppol invoices on {fmt_date(check)}."))
    return out


def _travel(goal: Goal, txs: list[Transaction], as_of: dt.date) -> list[MeasuredOutcome]:
    step = next((s for s in goal.steps if s.step_id == "insurance"), None)
    if not step:
        return []
    bookings = [t for t in txs if t.amount < -200 and t.date <= goal.created_on + 30 * DAY
                and any(m in t.counterparty.lower() for m in TRAVEL_MERCHANTS)]
    departure = (bookings[-1].date + 30 * DAY) if bookings else goal.created_on + 30 * DAY
    base = dict(metric="travel_cover", label="Insured before departure", unit="", step_id="insurance",
                estimate_eur=step.estimates.customer_eur or None)
    if step.status == "done":
        when = step.done_on or goal.created_on
        if when <= departure:
            return [MeasuredOutcome(**base, status="verified",
                                    evidence=[f"Cover active from {fmt_date(when)}", f"Departure around {fmt_date(departure)}"],
                                    summary=f"Insured {(departure - when).days} days before you leave.")]
        return [MeasuredOutcome(**base, status="not_met", evidence=[f"Cover only from {fmt_date(when)}"],
                                summary="The cover started after departure.")]
    if as_of >= departure:
        return [MeasuredOutcome(**base, status="not_met", evidence=[f"Departure around {fmt_date(departure)}"],
                                summary="You left without travel insurance through KBC.")]
    return [MeasuredOutcome(**base, status="pending", check_on=departure, evidence=[f"Departure around {fmt_date(departure)}"],
                            summary=f"Arrange the insurance before {fmt_date(departure)}: we'll check that day.")]


def _balance_at(txs: list[Transaction], balance_today: float | None, at: dt.date) -> float | None:
    if balance_today is None:
        return None
    return balance_today - sum(t.amount for t in txs if t.date > at)


def _peace(goal: Goal, txs: list[Transaction], as_of: dt.date, balance_today: float | None) -> list[MeasuredOutcome]:
    steps = _done(goal, ("savings",))
    if not steps:
        return []
    anchor = _anchor(goal, steps)
    bal = _balance_at(txs, balance_today, anchor)
    moved = max(1000.0, (bal or 6000.0) - 5000)
    yearly = moved * SAVINGS_RATE
    base = dict(metric="savings_working", label="Savings working for you", estimate_eur=_estimate(steps),
                unit="€ a year", step_id="savings")
    days = (as_of - anchor).days
    ev = [f"KBC moved {_eur(moved)} of idle money to savings on {fmt_date(anchor)}",
          f"Illustrative rate {SAVINGS_RATE:.0%} vs 0% on the current account"]
    if days < 30:
        check = anchor + 30 * DAY
        return [MeasuredOutcome(**base, status="pending", check_on=check, evidence=ev,
                                summary=f"First interest check on {fmt_date(check)}.")]
    return [MeasuredOutcome(**base, status="verified", measured_eur=round(yearly), evidence=ev,
                            summary=f"{_eur(moved)} now earns about {_eur(yearly)} a year ({_eur(yearly * days / 365)} so far).")]


def _retire(goal: Goal, txs: list[Transaction], as_of: dt.date, balance_today: float | None) -> list[MeasuredOutcome]:
    steps = _done(goal, ("invest", "pension_savings"))
    if not steps:
        return []
    anchor = _anchor(goal, steps)
    invested = 0.0
    ev = []
    if any(s.step_id == "invest" for s in steps):
        bal = _balance_at(txs, balance_today, anchor)
        spend = _monthly_spend(txs, lambda t: t.category not in ("savings_transfer",), anchor - 90 * DAY, anchor)
        invested = max(0.0, (bal or 0.0) - 6 * max(spend, 500))
        ev.append(f"Invested on {fmt_date(anchor)}: {_eur(invested)} (idle savings above a 6-month buffer)")
    pension = [t for t in txs if anchor < t.date <= as_of and t.amount < 0 and "pensioen" in t.counterparty.lower()]
    if pension:
        ev.append(f"Pension savings paid since then: {_eur(-sum(t.amount for t in pension))}")
    total = invested - sum(t.amount for t in pension)
    base = dict(metric="invested", label="Amount invested for retirement", estimate_eur=_estimate(steps),
                step_id=steps[-1].step_id)
    if total <= 0:
        check = max(anchor + 30 * DAY, as_of + DAY)
        return [MeasuredOutcome(**base, status="pending", check_on=check, evidence=ev or ["Nothing invested yet"],
                                summary=f"We'll check the first investment on {fmt_date(check)}.")]
    return [MeasuredOutcome(**base, status="verified", measured_eur=round(total), evidence=ev,
                            summary=f"{_eur(total)} is invested for your retirement.")]


def _home(goal: Goal, txs: list[Transaction], as_of: dt.date) -> list[MeasuredOutcome]:
    steps = _done(goal, ("mortgage", "insurance"), include_held=True)
    if not steps:
        return []
    anchor = min((s.done_on or goal.created_on) for s in steps)
    seen = [t for t in txs if t.date <= as_of]
    deed = next((t for t in seen if t.category == "notary" and t.date >= anchor - 200 * DAY), None)
    mortgage = next((t for t in seen if t.category == "mortgage" and t.date >= anchor - 200 * DAY), None)
    insurance = next((t for t in seen if t.category == "insurance_home" and t.date >= anchor - 200 * DAY), None)
    base = dict(metric="home_from_day_one", label="Mortgage and home insurance from signing day", unit="",
                step_id="mortgage", estimate_eur=_estimate([s for s in steps if not s.already_held]))
    if not deed or not mortgage:
        check = max(as_of + 30 * DAY, anchor + 30 * DAY)
        return [MeasuredOutcome(**base, status="pending", check_on=check, evidence=["No deed or mortgage payment yet"],
                                summary=f"We'll check on signing day (next look: {fmt_date(check)}).")]
    ev = [f"Deed signed {fmt_date(deed.date)}", f"First mortgage payment {fmt_date(mortgage.date)}"]
    if insurance and insurance.date <= mortgage.date + 31 * DAY:
        ev.append(f"Home insurance paid from {fmt_date(insurance.date)}")
        return [MeasuredOutcome(**base, status="verified", evidence=ev,
                                summary="Your mortgage runs and your home was insured from day one.")]
    return [MeasuredOutcome(**base, status="not_met", evidence=ev + ["No home insurance payment seen around signing"],
                            summary="The home insurance was not in place on signing day.")]


def _baby(goal: Goal, txs: list[Transaction], as_of: dt.date) -> list[MeasuredOutcome]:
    if not _done(goal, ("budget", "family_insurance", "hospitalisation"), include_held=True):
        return []
    anchor = goal.created_on
    paid = [t for t in txs if t.category == "child_benefit" and anchor < t.date <= as_of and t.amount > 0]
    base = dict(metric="child_benefit", label="Child benefit (Groeipakket) arriving", unit="€", step_id="budget")
    if paid:
        total = sum(t.amount for t in paid)
        return [MeasuredOutcome(**base, status="verified", measured_eur=round(total, 2),
                                evidence=[f"{len(paid)} payment(s) since {fmt_date(paid[0].date)}"],
                                summary=f"Child benefit is coming in: {_eur(total)} so far.")]
    check = max(anchor + 90 * DAY, as_of + DAY)
    return [MeasuredOutcome(**base, status="pending", check_on=check, evidence=["No child benefit seen yet"],
                            summary=f"We'll check the child benefit arrives by {fmt_date(check)}.")]


def measure(goal: Goal, txs: list[Transaction], as_of: dt.date,
            balance_today: float | None = None) -> list[MeasuredOutcome]:
    """Realised outcomes of a goal at `as_of`, from the customer's own transactions (only those up to as_of)."""
    seen = sorted((t for t in txs if t.date <= as_of), key=lambda t: t.date)
    pid = goal.playbook_id
    if pid == "energy_upgrade":
        return _energy(goal, seen, as_of)
    if pid == "get_paid":
        return _get_paid(goal, seen, as_of)
    if pid == "go_freelance":
        return _freelance(goal, seen, as_of)
    if pid == "travel":
        return _travel(goal, seen, as_of)
    if pid == "peace_of_mind":
        return _peace(goal, seen, as_of, _balance_shift(txs, balance_today, as_of))
    if pid == "retire_well":
        return _retire(goal, seen, as_of, _balance_shift(txs, balance_today, as_of))
    if pid == "buy_home":
        return _home(goal, seen, as_of)
    if pid == "new_baby":
        return _baby(goal, seen, as_of)
    return []


def _balance_shift(txs: list[Transaction], balance_today: float | None, as_of: dt.date) -> float | None:
    """The balance at as_of, so `_balance_at` on the as_of-filtered list stays correct."""
    return _balance_at(txs, balance_today, as_of)


def verified_eur(measured: list[MeasuredOutcome]) -> float:
    return sum(m.measured_eur or 0 for m in measured if m.status == "verified" and m.unit.startswith("€"))
