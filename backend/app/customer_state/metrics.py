"""Pure financial calculations. Amounts retain ledger sign until aggregated; no FX guesses."""
from __future__ import annotations

import calendar
import datetime as dt
import statistics as stats
from collections import defaultdict

from .models import (CashFlow, Debt, Evidence, Expenses, ExpectedFlow, Income, Observations,
                     Pattern, Position, Recurring, Savings, Signal, Spending)
from .normalization import DEBT
from .patterns import advance, change, evidence, month_add


def ratio(a, b):
    return round(a / b, 4) if a is not None and b is not None and b > 0 else None


def trend(values):
    if len(values) < 2:
        return "unknown"
    old, new = stats.mean(values[:-1]), values[-1]
    delta = (new - old) / max(abs(old), 1)
    return "increasing" if delta >= .1 else "decreasing" if delta <= -.1 else "stable"


def average(values):
    return round(stats.mean(values), 2) if values else None


def complete_months(signals, as_of):
    if not signals:
        return []
    first = min(s.date for s in signals)
    start = first.replace(day=1) if first.day == 1 else month_add(first.replace(day=1), 1)
    end = as_of.replace(day=1)
    if as_of.day != calendar.monthrange(as_of.year, as_of.month)[1]:
        end = month_add(end, -1)
    months = []
    while start <= end:
        months.append(start)
        start = month_add(start, 1)
    return months


def position(raw: Observations, signals: list[Signal], as_of: dt.date):
    latest = {}
    for account in sorted(raw.accounts, key=lambda a: (a.observed_at, a.id)):
        if account.currency == "EUR" and account.observed_at <= as_of:
            latest[account.account_id] = account
    totals = defaultdict(float)
    counts = defaultdict(int)
    for account in latest.values():
        balance = account.balance
        # Debt principal cannot be reconstructed from repayments that also include interest.
        if account.kind in {"current", "savings"}:
            balance += sum(s.amount for s in signals if s.account_id == account.account_id
                           and account.observed_at < s.date <= as_of)
        totals[account.kind] += balance
        counts[account.kind] += 1
    current = round(totals["current"], 2) if counts["current"] else None
    savings = round(totals["savings"], 2) if counts["savings"] else None
    debt = round(totals["loan"] + totals["credit"], 2) if counts["loan"] + counts["credit"] else None
    liquid = round((current or 0) + (savings or 0), 2) if current is not None or savings is not None else None
    return Position(current_balance=current, known_savings=savings, known_debt=debt,
                    total_liquid_balance=liquid, overdraft=max(0, -current) if current is not None else None)


def calculate(raw: Observations, signals: list[Signal], patterns: list[Pattern], as_of: dt.date):
    months = complete_months(signals, as_of)
    grouped = defaultdict(list)
    for s in signals:
        grouped[s.date.replace(day=1)].append(s)
    recurring_ids = {tid for p in patterns if p.type == "RECURRING_PAYMENT" for tid in p.evidence.transaction_ids}
    current_accounts = {a.account_id for a in raw.accounts if a.kind == "current"} or {"current"}
    monthly = []
    categories = defaultdict(dict)
    for month in months:
        items = grouped[month]
        income = sum(s.amount for s in items if s.kind == "income")
        expense = -sum(s.amount for s in items if s.kind in {"expense", "refund"})
        saved = -sum(s.amount for s in items if s.kind == "savings")
        fixed = -sum(s.amount for s in items if s.kind == "expense" and s.transaction_id in recurring_ids)
        discretionary = -sum(s.amount for s in items if s.kind == "expense" and s.discretionary)
        essential = -sum(s.amount for s in items if s.kind == "expense" and s.essential)
        debt_service = -sum(s.amount for s in items if s.kind == "expense" and s.category in DEBT)
        monthly.append(dict(month=month.isoformat(), income=round(income, 2), expenses=round(expense, 2),
                            inflow=round(sum(s.amount for s in items if s.account_id in current_accounts and s.amount > 0), 2),
                            outflow=round(-sum(s.amount for s in items if s.account_id in current_accounts and s.amount < 0), 2),
                            fixed=round(fixed, 2), variable=round(expense-fixed, 2),
                            discretionary=round(discretionary, 2), essential=round(essential, 2),
                            savings=round(saved, 2), debt_service=round(debt_service, 2),
                            free_cash_flow=round(income-expense, 2), net_current_cash_flow=round(income-expense-saved, 2)))
        for s in items:
            if s.kind in {"expense", "refund"}:
                categories[s.category][month] = categories[s.category].get(month, 0) - s.amount
    window = monthly[-6:]
    window_months = set(months[-6:])
    window_items = [s for s in signals if s.date.replace(day=1) in window_months]
    def series(key):
        return [m[key] for m in window]
    def avg(key):
        return average(series(key))
    pos = position(raw, signals, as_of)
    active = [p for p in patterns if p.active]
    next_income = sorted([p for p in active if p.kind == "income" and p.next_date and p.next_date > as_of],
                         key=lambda p: (p.next_date, -p.amount))
    mean_inc = avg("income")
    income = Income(estimated_monthly_income=mean_inc,
                    income_stability=round(max(0, 1-stats.pstdev(series("income"))/mean_inc), 4)
                    if len(window) >= 3 and mean_inc and mean_inc > 0 else None,
                    income_trend=trend(series("income")),
                    income_sources=len({s.entity for s in signals if s.kind == "income" and s.profile_allowed
                                        and (as_of-s.date).days < 180}),
                    next_expected_income_date=next_income[0].next_date if next_income else None,
                    next_expected_income_amount=next_income[0].amount if next_income else None)
    expenses = Expenses(average_monthly_expenses=avg("expenses"), average_fixed_expenses=avg("fixed"),
                        average_variable_expenses=avg("variable"), average_discretionary_expenses=avg("discretionary"),
                        average_essential_expenses=avg("essential"),
                        average_unclassified_expenses=average([m["expenses"]-m["discretionary"]-m["essential"]
                                                               for m in window]))
    savings = Savings(balance=pos.known_savings,
                      transfers_to_savings=round(-sum(s.amount for s in window_items if s.kind == "savings" and s.amount < 0), 2),
                      withdrawals_from_savings=round(sum(s.amount for s in window_items if s.kind == "savings" and s.amount > 0), 2),
                      average_monthly_savings=avg("savings"), savings_rate=ratio(avg("savings"), mean_inc),
                      trend=trend(series("savings")))
    debt_accounts = {a.account_id for a in raw.accounts if a.kind in {"loan", "credit"} and a.currency == "EUR"}
    # Compare matching account sets; opening a new loan must not masquerade as repayment.
    debt_totals = defaultdict(dict)
    for a in raw.accounts:
        if a.account_id in debt_accounts and a.currency == "EUR":
            debt_totals[a.observed_at][a.account_id] = a.balance
    debt_values = [sum(v.values()) for _, v in sorted(debt_totals.items()) if set(v) == debt_accounts]
    debt_trend = "unknown"
    if len(debt_values) >= 2:
        debt_trend = "decreasing" if debt_values[-1] < debt_values[-2] else "increasing" if debt_values[-1] > debt_values[-2] else "stable"
    debt = Debt(total_known_debt=pos.known_debt, monthly_debt_service=avg("debt_service"),
                debt_service_ratio=ratio(avg("debt_service"), mean_inc), trend=debt_trend)
    payments = [p for p in active if p.type == "RECURRING_PAYMENT"]
    subs = [p for p in payments if p.category == "subscription"]
    def recurring(items):
        return Recurring(count=len(items), monthly_total=round(sum(p.monthly_amount for p in items), 2), items=items)
    by_id = {s.transaction_id: s for s in signals}
    flows = []
    for p in active:
        if p.type == "RECURRING_MERCHANT" or not p.next_date:
            continue
        if by_id[p.evidence.transaction_ids[-1]].account_id not in current_accounts:
            continue
        due = p.next_date
        # Still within grace: include a missed expected charge tomorrow, clearly a projection.
        if due <= as_of:
            due = as_of + dt.timedelta(days=1)
        while due <= as_of + dt.timedelta(days=30):
            flows.append(ExpectedFlow(date=due, amount=p.amount, pattern_id=p.id))
            due = advance(due, p.cadence, p.usual_day)
    flows.sort(key=lambda f: (f.date, f.pattern_id))
    scheduled_ids = {tid for p in patterns if p.type != "RECURRING_MERCHANT" for tid in p.evidence.transaction_ids}
    # Forecast only the current account; avoid double-counting scheduled bills and savings sweeps.
    variable = -sum(s.amount for s in window_items if s.kind in {"expense", "refund"}
                    and s.transaction_id not in scheduled_ids and s.account_id in current_accounts)
    days = sum(calendar.monthrange(m.year, m.month)[1] for m in months[-6:])
    daily = max(0, variable / days) if days else None
    projections = []
    if pos.current_balance is not None and daily is not None:
        balance = pos.current_balance
        for i in range(1, 31):
            day = as_of + dt.timedelta(days=i)
            balance += sum(f.amount for f in flows if f.date == day) - daily
            projections.append(round(balance, 2))
    lowest = min([pos.current_balance] + projections) if projections else None
    pressure = ("unknown" if lowest is None else "high" if lowest < 0 else "medium"
                if lowest < max(100, (avg("expenses") or 0) * .2) else "low")
    cash = CashFlow(monthly=monthly, average_monthly_free_cash_flow=avg("free_cash_flow"),
                    cash_buffer_months=ratio(pos.total_liquid_balance, avg("expenses")),
                    upcoming_inflows=[f for f in flows if f.amount > 0],
                    upcoming_outflows=[f for f in flows if f.amount < 0],
                    expected_7_day_balance=projections[6] if projections else None,
                    expected_30_day_balance=projections[29] if projections else None,
                    lowest_projected_balance=lowest, liquidity_pressure=pressure)
    category_metrics = {}
    total = sum(series("expenses"))
    for category, values in sorted(categories.items()):
        vals = [round(values.get(m, 0), 2) for m in months[-6:]]
        category_metrics[category] = dict(total=round(sum(vals), 2), monthly_average=average(vals),
                                          share=ratio(sum(vals), total), trend=trend(vals),
                                          month_over_month_change=ratio(vals[-1]-vals[-2], vals[-2]) if len(vals)>1 else None)
    merchants = defaultdict(float)
    for s in window_items:
        if s.kind in {"expense", "refund"} and s.profile_allowed:
            merchants[s.entity] -= s.amount
    spending = Spending(trend=trend(series("expenses")),
                        volatility=ratio(stats.pstdev(series("expenses")), avg("expenses")) if len(window)>=2 else None,
                        month_over_month_change=ratio(window[-1]["expenses"]-window[-2]["expenses"], window[-2]["expenses"])
                        if len(window)>=2 else None,
                        top_categories=[dict(category=k, **v) for k, v in sorted(category_metrics.items(), key=lambda kv: -kv[1]["total"])[:10]],
                        top_merchants=[dict(merchant=k, total=round(v, 2), share=ratio(v, total)) for k, v in sorted(merchants.items(), key=lambda kv: -kv[1])[:10]],
                        category_metrics=category_metrics)
    changes = []
    for i in range(3, len(months)):
        month = months[i]
        period_items = [s for s in signals if months[i-3] <= s.date < month_add(month, 1)]
        detected = month_add(month, 1) - dt.timedelta(days=1)
        for category, values in categories.items():
            old = stats.mean(values.get(m, 0) for m in months[i-3:i])
            new = values.get(month, 0)
            # The coarse sensitive bucket contributes to totals, never generates profile changes.
            category_items = [s for s in period_items if s.category == category and s.profile_allowed]
            if category == "other" or not category_items:
                continue
            if old >= 50 and abs(new-old) >= max(50, old*.3):
                changes.append(change("CATEGORY_SPENDING_INCREASED" if new>old else "CATEGORY_SPENDING_DECREASED",
                                      category, detected, category_items, round(old, 2), round(new, 2)))
        for key, typ in [("savings", "SAVINGS_BEHAVIOR_CHANGED"), ("free_cash_flow", "MONTHLY_CASH_FLOW_CHANGED")]:
            old = stats.mean(m[key] for m in monthly[i-3:i])
            new = monthly[i][key]
            if abs(new-old) >= max(100, abs(old)*.3):
                changes.append(change(typ, key, detected, period_items, round(old, 2), new))
    # Compare observed liquid balances using the same spending denominator. Do not infer
    # past savings balances by subtracting transfer history from an unknown opening balance.
    liquid_observations = defaultdict(dict)
    for a in raw.accounts:
        if a.kind in {"current", "savings"} and a.currency == "EUR" and a.source != "legacy_ledger_reconstruction":
            liquid_observations[a.observed_at][a.account_id] = a
    dated = sorted(liquid_observations.items())
    for (old_date, old_accounts), (new_date, new_accounts) in zip(dated, dated[1:]):
        if set(old_accounts) != set(new_accounts) or (new_date-old_date).days < 20:
            continue
        prior_expenses = [m["expenses"] for m in monthly if m["month"] < new_date.replace(day=1).isoformat()][-3:]
        denominator = average(prior_expenses)
        if not denominator or denominator <= 0:
            continue
        old = sum(a.balance for a in old_accounts.values()) / denominator
        new = sum(a.balance for a in new_accounts.values()) / denominator
        if abs(new-old) >= max(.25, abs(old)*.1):
            c = change("CASH_BUFFER_CHANGED", "liquid_accounts", new_date, [], round(old, 4), round(new, 4),
                       1, "observed_liquid_balances_over_same_prior_three_month_expenses")
            c.evidence.account_observation_ids = [a.id for a in list(old_accounts.values())+list(new_accounts.values())]
            c.evidence.transaction_ids = [s.transaction_id for s in signals if month_add(new_date.replace(day=1), -3) <= s.date < new_date.replace(day=1)]
            changes.append(c)
    prov = evidence(window_items, "mean_last_six_complete_calendar_months_zero_months_included")
    prov.period_from = months[-6] if len(months)>=6 else months[0] if months else None
    prov.period_to = month_add(months[-1], 1)-dt.timedelta(days=1) if months else None
    provenance = {name: prov for name in ["income", "expenses", "savings", "spending", "debt.monthly_debt_service", "cash_flow.monthly"]}
    provenance["financial_position"] = Evidence(account_observation_ids=[a.id for a in raw.accounts],
                                                 transaction_ids=[s.transaction_id for s in signals],
                                                 period_to=as_of, method="latest_account_observation_plus_post_snapshot_ledger_movements")
    provenance["cash_flow.projection"] = Evidence(transaction_ids=prov.transaction_ids,
                                                   pattern_ids=[p.id for p in active], period_to=as_of,
                                                   method="scheduled_flows_plus_unscheduled_daily_burn_no_irregular_income")
    return dict(financial_position=pos, income=income, expenses=expenses, cash_flow=cash, savings=savings,
                debt=debt, recurring_payments=recurring(payments), subscriptions=recurring(subs),
                spending=spending, provenance=provenance), changes
