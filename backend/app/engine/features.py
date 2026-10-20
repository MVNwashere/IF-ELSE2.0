"""Transactions → Features. Pure, deterministic, `as_of`-aware.

Only transactions with `date <= as_of` are used. Balance at `as_of` is reconstructed from
`balance_today` by undoing everything that happened after `as_of`.
"""
from __future__ import annotations

import datetime as dt
import statistics
from collections import defaultdict

from ..schemas import Customer, Features, LifeEvent, RecurringPayment, Transaction, INCOME_CATEGORIES

# ---- tuning knobs -----------------------------------------------------------------
MONTHLY_PERIOD = (25, 35)          # days between occurrences to count as monthly
YEARLY_PERIOD = (330, 400)         # days between occurrences to count as yearly
MONTHLY_MIN_OCCURRENCES = 3
YEARLY_MIN_OCCURRENCES = 2
PRICE_CHANGE_THRESHOLD = 0.05      # >5 % change vs the previous price sets previous_amount_eur
PRICE_CHANGE_LOOKBACK_DAYS = 60    # only when the new price started within this window
# Only fixed-amount categories count as recurring bills (groceries and leisure recur too, but vary in amount).
BILL_CATEGORIES = frozenset({
    "rent", "mortgage", "utilities", "telecom", "subscription", "insurance_car", "insurance_home",
    "insurance_family", "childcare", "school", "tuition", "savings_transfer", "social_contribution",
})
FIXED_PRICE_CATEGORIES = frozenset({   # only these can raise a price_increase (utilities vary with usage)
    "subscription", "telecom", "rent", "mortgage", "insurance_car", "insurance_home", "insurance_family",
    "childcare", "school",
})
SINGLE_PAYMENT_YEARLY = frozenset({"insurance_car", "insurance_home"})  # one payment in 400 days = a yearly premium
SINGLE_PAYMENT_LOOKBACK_DAYS = 400
IDLE_CASH_MULTIPLE = 6             # balance above 6× monthly spend counts as idle
VARIABLE_CATEGORIES = frozenset({"groceries", "leisure", "transport", "other", "healthcare", "baby"})
ONE_OFF_CATEGORIES = frozenset({"notary", "furniture", "tuition", "tax", "savings_transfer"})  # excluded from forecasts
SQUEEZE_MIN_HISTORY_DAYS = 120     # no spending-change signal without a prior baseline
RUNWAY_MAX_DAYS = 365              # beyond a year, "runway" is meaningless → None
REGULAR_INCOME_CATEGORIES = ("salary", "pension", "child_benefit", "allowance_from_parents", "student_income", "benefit")
CHILD_CATEGORIES = frozenset({"childcare", "baby", "school", "child_benefit"})
STUDENT_CATEGORIES = frozenset({"student_income", "allowance_from_parents", "tuition"})
WINDOW_90 = 90
WINDOW_180 = 180
WINDOW_30 = 30
WINDOW_365 = 365
VAT_DUE_DAY = 20                   # quarterly VAT return due on the 20th after quarter end (confirm before prod)


def fmt_date(d: dt.date) -> str:
    """'12 Oct 2025' (no leading zero). Shared by all engine modules for evidence strings."""
    return f"{d.day} {d.strftime('%b %Y')}"


def fmt_eur(x: float) -> str:
    """Belgian style: '€1.840', '€13,75', '€612' (no decimals for whole amounts)."""
    x = abs(x)
    whole = abs(x - round(x)) < 0.005
    us = f"{x:,.0f}" if whole else f"{x:,.2f}"
    return "€" + us.replace(",", "|").replace(".", ",").replace("|", ".")


def _in_window(t: Transaction, as_of: dt.date, days: int) -> bool:
    return as_of - dt.timedelta(days=days) < t.date <= as_of


def balance_at(txs: list[Transaction], balance_today: float, as_of: dt.date) -> float:
    return balance_today - sum(t.amount for t in txs if t.date > as_of)


def balance_series(customer: Customer, txs: list[Transaction], balance_today: float,
                   as_of: dt.date, days: int = 30) -> list[float]:
    """Daily end-of-day balances for the `days` days ending at `as_of` (inclusive)."""
    end_balance = balance_at(txs, balance_today, as_of)
    start = as_of - dt.timedelta(days=days - 1)
    per_day: dict[dt.date, float] = defaultdict(float)
    for t in txs:
        if start <= t.date <= as_of:
            per_day[t.date] += t.amount
    # walk backwards from as_of
    series = [0.0] * days
    bal = end_balance
    for i in range(days - 1, -1, -1):
        day = start + dt.timedelta(days=i)
        series[i] = round(bal, 2)
        bal -= per_day.get(day, 0.0)
    return series


def _recurring(spend: list[Transaction], as_of: dt.date) -> list[RecurringPayment]:
    groups: dict[tuple[str, str], list[Transaction]] = defaultdict(list)
    for t in spend:
        if t.category not in BILL_CATEGORIES:
            continue
        groups[(t.counterparty, t.category)].append(t)
    out: list[RecurringPayment] = []
    for (cp, cat), items in groups.items():
        items.sort(key=lambda t: (t.date, t.id))
        if len(items) == 1 and cat in SINGLE_PAYMENT_YEARLY and (as_of - items[0].date).days <= SINGLE_PAYMENT_LOOKBACK_DAYS:
            t = items[0]
            out.append(RecurringPayment(counterparty=cp, category=cat, amount_eur=round(abs(t.amount), 2),
                                        previous_amount_eur=None, period_days=365, last_date=t.date,
                                        next_date=t.date + dt.timedelta(days=365)))
            continue
        if len(items) < YEARLY_MIN_OCCURRENCES:
            continue
        gaps = [(b.date - a.date).days for a, b in zip(items, items[1:])]
        gaps = [g for g in gaps if g > 0]
        if not gaps:
            continue
        med = statistics.median(gaps)
        if MONTHLY_PERIOD[0] <= med <= MONTHLY_PERIOD[1] and len(items) >= MONTHLY_MIN_OCCURRENCES:
            period = 30
        elif YEARLY_PERIOD[0] <= med <= YEARLY_PERIOD[1] and len(items) >= YEARLY_MIN_OCCURRENCES:
            period = 365
        else:
            continue
        last = items[-1]
        # only consider it live if the last payment is within ~1.5 periods
        if (as_of - last.date).days > period * 1.5:
            continue
        amount = abs(last.amount)
        prev_amount = None
        if cat in FIXED_PRICE_CATEGORIES:
            # walk back over payments at the current amount to find the previous price and when it changed
            change_idx = len(items) - 1
            while change_idx > 0 and abs(abs(items[change_idx - 1].amount) - amount) <= PRICE_CHANGE_THRESHOLD * amount:
                change_idx -= 1
            if change_idx > 0 and (as_of - items[change_idx].date).days <= PRICE_CHANGE_LOOKBACK_DAYS:
                prev_amount = round(abs(items[change_idx - 1].amount), 2)
        out.append(RecurringPayment(
            counterparty=cp, category=cat, amount_eur=round(amount, 2), previous_amount_eur=prev_amount,
            period_days=period, last_date=last.date, next_date=last.date + dt.timedelta(days=period),
        ))
    out.sort(key=lambda r: r.next_date)
    return out


def _monthly_income_series(income: list[Transaction], as_of: dt.date, months: int = 3) -> list[float]:
    buckets = [0.0] * months
    for t in income:
        age = (as_of - t.date).days
        if 0 <= age < months * 30:
            buckets[age // 30] += t.amount
    return buckets


def _life_events(txs: list[Transaction]) -> list[LifeEvent]:
    events: list[LifeEvent] = []
    firsts: dict[str, Transaction] = {}
    for t in txs:  # txs sorted by date
        key = None
        if t.category == "salary":
            key = "first_salary"
        elif t.category == "invoice_income":
            key = "first_invoice"
        elif t.category in ("baby", "child_benefit"):
            key = "baby"
        elif t.category == "pension":
            key = "pension_start"
        elif t.category in ("notary", "mortgage"):
            key = "moved_house"
        if key and key not in firsts:
            firsts[key] = t
    labels = {
        "first_salary": "First salary of €{amt} from {cp} on {d}",
        "first_invoice": "First invoice paid: €{amt} from {cp} on {d}",
        "baby": "First family-related transaction ({cat}) on {d}",
        "pension_start": "First pension payment of €{amt} from {cp} on {d}",
        "moved_house": "{cat} payment to {cp} on {d}",
    }
    for key, t in firsts.items():
        events.append(LifeEvent(
            type=key, date=t.date,
            evidence=labels[key].format(amt=f"{abs(t.amount):,.0f}", cp=t.counterparty, d=fmt_date(t.date),
                                        cat=t.category.replace("_", " ")),
        ))
    events.sort(key=lambda e: e.date)
    return events


def _add_period(d: dt.date, period_days: int) -> dt.date:
    """Monthly-ish periods advance by calendar month (25 Sep → 25 Oct); others by days."""
    if MONTHLY_PERIOD[0] <= period_days <= MONTHLY_PERIOD[1]:
        y, m = (d.year, d.month + 1) if d.month < 12 else (d.year + 1, 1)
        return dt.date(y, m, min(d.day, 28))
    return d + dt.timedelta(days=period_days)


def vat_period(as_of: dt.date) -> tuple[dt.date, dt.date, dt.date, str]:
    """(period_start, period_end, due_date, label) of the VAT reporting period relevant at `as_of`.

    If as_of is on or before the due date (VAT_DUE_DAY of the month after the quarter end) of the most
    recently ended quarter, that ended quarter is the period. Otherwise it's the running quarter.
    """
    q = (as_of.month - 1) // 3  # 0-based running quarter
    # most recently ended quarter
    if q == 0:
        prev_start, prev_end = dt.date(as_of.year - 1, 10, 1), dt.date(as_of.year - 1, 12, 31)
        prev_due = dt.date(as_of.year, 1, VAT_DUE_DAY)
    else:
        prev_start = dt.date(as_of.year, 3 * (q - 1) + 1, 1)
        prev_end = dt.date(as_of.year, 3 * q + 1, 1) - dt.timedelta(days=1)
        prev_due = dt.date(as_of.year, 3 * q + 1, VAT_DUE_DAY)
    if as_of <= prev_due:
        start, end, due = prev_start, prev_end, prev_due
    else:
        start = dt.date(as_of.year, 3 * q + 1, 1)
        if q == 3:
            end, due = dt.date(as_of.year, 12, 31), dt.date(as_of.year + 1, 1, VAT_DUE_DAY)
        else:
            end = dt.date(as_of.year, 3 * q + 4, 1) - dt.timedelta(days=1)
            due = dt.date(as_of.year, 3 * q + 4, VAT_DUE_DAY)
    label = f"Q{(start.month - 1) // 3 + 1} {start.year}"
    return start, end, due, label


def _next_income(income: list[Transaction], as_of: dt.date) -> tuple[dt.date | None, float | None]:
    # Regular payers first: same (counterparty, category) with ≥2 occurrences in the last 120 days.
    groups: dict[tuple[str, str], list[Transaction]] = defaultdict(list)
    for t in income:
        if _in_window(t, as_of, 120) and t.category in REGULAR_INCOME_CATEGORIES:
            groups[(t.counterparty, t.category)].append(t)
    best: tuple[dt.date, float] | None = None
    for items in groups.values():
        if len(items) < 2:
            continue
        items.sort(key=lambda t: t.date)
        gaps = [(b.date - a.date).days for a, b in zip(items, items[1:])]
        period = max(1, int(statistics.median(gaps)))
        nxt = _add_period(items[-1].date, period)
        while nxt <= as_of:
            nxt = _add_period(nxt, period)
        if best is None or nxt < best[0] or (nxt == best[0] and items[-1].amount > best[1]):
            best = (nxt, items[-1].amount)
    if best:
        return best[0], round(best[1], 2)
    invoices = sorted([t for t in income if t.category == "invoice_income" and _in_window(t, as_of, WINDOW_180)],
                      key=lambda t: t.date)
    if len(invoices) >= 2:
        gaps = [(b.date - a.date).days for a, b in zip(invoices, invoices[1:])]
        gaps = [g for g in gaps if g > 0] or [30]
        period = max(1, int(statistics.median(gaps)))
        nxt = invoices[-1].date + dt.timedelta(days=period)
        while nxt <= as_of:
            nxt += dt.timedelta(days=period)
        avg = statistics.mean(t.amount for t in invoices)
        return nxt, round(avg, 2)
    return None, None


def compute_features(customer: Customer, txs: list[Transaction], balance_today: float, as_of: dt.date) -> Features:
    balance = balance_at(txs, balance_today, as_of)
    past = sorted([t for t in txs if t.date <= as_of], key=lambda t: (t.date, t.id))
    income = [t for t in past if t.amount > 0 and t.category in INCOME_CATEGORIES]
    spend = [t for t in past if t.amount < 0]

    inc_90 = _monthly_income_series(income, as_of, 3)
    monthly_income = sum(inc_90) / 3
    mean_inc = statistics.mean(inc_90)
    regularity = (statistics.pstdev(inc_90) / mean_inc) if mean_inc > 0 else 1.0

    # monthly spend = regular burn: one-offs (notary, furniture, tuition, tax, savings transfers) are excluded
    # so that a single big purchase neither inflates forecasts nor hides idle cash
    spend_90 = sum(-t.amount for t in spend if _in_window(t, as_of, WINDOW_90) and t.category not in ONE_OFF_CATEGORIES)
    monthly_spend = spend_90 / 3
    monthly_spend_regular = monthly_spend

    income_180 = [t for t in income if _in_window(t, as_of, WINDOW_180)]
    income_by_cat: dict[str, float] = defaultdict(float)
    for t in income_180:
        income_by_cat[t.category] += t.amount
    sources = len({t.counterparty for t in income_180})

    spend_by_cat: dict[str, float] = defaultdict(float)
    for t in spend:
        if _in_window(t, as_of, WINDOW_30):
            spend_by_cat[t.category] += -t.amount

    var_30 = sum(-t.amount for t in spend if t.category in VARIABLE_CATEGORIES and _in_window(t, as_of, WINDOW_30))
    prev_start = as_of - dt.timedelta(days=WINDOW_30)
    var_prev = sum(-t.amount for t in spend if t.category in VARIABLE_CATEGORIES
                   and prev_start - dt.timedelta(days=WINDOW_90) < t.date <= prev_start) / 3
    var_change = (var_30 - var_prev) / var_prev if var_prev > 0 else 0.0
    if past and (as_of - past[0].date).days < SQUEEZE_MIN_HISTORY_DAYS:
        var_change = 0.0

    net_burn = (monthly_spend_regular - monthly_income) / 30
    runway = int(balance / net_burn) if net_burn > 0 and balance > 0 else (0 if net_burn > 0 else None)
    if runway is not None and runway > RUNWAY_MAX_DAYS:
        runway = None

    has_savings = "savings" in customer.products
    idle = max(0.0, balance - IDLE_CASH_MULTIPLE * monthly_spend) if (not has_savings and monthly_spend > 0) else 0.0

    q_start = dt.date(as_of.year, 3 * ((as_of.month - 1) // 3) + 1, 1)
    q_income = sum(t.amount for t in income if q_start <= t.date <= as_of)
    q_invoice = sum(t.amount for t in income if q_start <= t.date <= as_of and t.category == "invoice_income")
    vp_start, vp_end, vp_due, vp_label = vat_period(as_of)
    vp_invoice = sum(t.amount for t in income if vp_start <= t.date <= min(vp_end, as_of) and t.category == "invoice_income")

    cats_365 = {t.category for t in past if _in_window(t, as_of, WINDOW_365)}
    cats_180 = {t.category for t in past if _in_window(t, as_of, WINDOW_180)}
    cats_120 = {t.category for t in past if _in_window(t, as_of, 120)}

    child_benefit = sum(t.amount for t in income if t.category == "child_benefit" and _in_window(t, as_of, WINDOW_90)) / 3
    childcare = sum(-t.amount for t in spend if t.category == "childcare" and _in_window(t, as_of, WINDOW_90)) / 3

    next_date, next_eur = _next_income(income, as_of)
    has_invoice = "invoice_income" in cats_180
    has_vat = "vat_payment" in cats_365
    age = as_of.year - customer.birth_year

    return Features(
        as_of=as_of,
        age=age,
        balance_eur=round(balance, 2),
        monthly_income_avg_90d=round(monthly_income, 2),
        income_regularity=round(regularity, 3),
        income_sources_180d=sources,
        income_by_category_180d={k: round(v, 2) for k, v in income_by_cat.items()},
        next_income_date=next_date,
        next_income_eur=next_eur,
        quarter_income_eur=round(q_income, 2),
        quarter_invoice_income_eur=round(q_invoice, 2),
        vat_period_label=vp_label,
        vat_period_invoice_income_eur=round(vp_invoice, 2),
        vat_due_date=vp_due if (has_invoice or has_vat) else None,
        monthly_spend_avg_90d=round(monthly_spend, 2),
        spend_by_category_30d={k: round(v, 2) for k, v in spend_by_cat.items()},
        variable_spend_change_30d=round(var_change, 3),
        runway_days=runway,
        idle_cash_eur=round(idle, 2),
        has_salary="salary" in cats_120,
        has_invoice_income=has_invoice,
        has_pension="pension" in cats_120,
        has_student_signals=bool(cats_365 & STUDENT_CATEGORIES),
        has_child_signals=bool(cats_180 & CHILD_CATEGORIES),
        has_vat_payments=has_vat,
        has_social_contributions="social_contribution" in cats_365,
        has_mortgage="mortgage" in cats_120 or "mortgage" in customer.products,
        has_rent="rent" in cats_120,
        has_savings_product=has_savings,
        child_benefit_monthly_eur=round(child_benefit, 2),
        childcare_monthly_eur=round(childcare, 2),
        recurring_payments=_recurring(spend, as_of),
        life_events=_life_events(past),
        first_tx_date=past[0].date if past else None,
        last_tx_date=past[-1].date if past else None,
    )
