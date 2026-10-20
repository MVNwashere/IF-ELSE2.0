"""Deterministic cadence and change detectors, with stable evidence-based IDs."""
from __future__ import annotations

import calendar
import datetime as dt
import hashlib
import statistics as stats
from collections import defaultdict

from .models import Change, Evidence, Pattern, Signal
from .normalization import BILLS, DEBT


def stable_id(*parts) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:24]


def month_add(date: dt.date, months: int, day: int | None = None) -> dt.date:
    offset = date.year * 12 + date.month - 1 + months
    year, month = divmod(offset, 12)
    month += 1
    return dt.date(year, month, min(day or date.day, calendar.monthrange(year, month)[1]))


def advance(date: dt.date, cadence: str, day: int) -> dt.date:
    return (date + dt.timedelta(days=7) if cadence == "weekly"
            else month_add(date, {"monthly": 1, "quarterly": 3, "yearly": 12}[cadence], day))


def evidence(items: list[Signal], method: str) -> Evidence:
    return Evidence(transaction_ids=[s.transaction_id for s in items],
                    period_from=min((s.date for s in items), default=None),
                    period_to=max((s.date for s in items), default=None), method=method)


def change(kind, entity, date, items, previous=None, current=None, confidence=.85, method="historical_comparison"):
    return Change(id=stable_id(kind, entity, date, *(s.transaction_id for s in items)), type=kind, entity=entity,
                  previous_value=previous, current_value=current,
                  change_pct=round((current - previous) / abs(previous), 4)
                  if previous not in (None, 0) and current is not None else None,
                  detected_at=date, confidence=confidence, evidence=evidence(items, method))


def detect(signals: list[Signal], as_of: dt.date) -> tuple[list[Pattern], list[Change]]:
    groups = defaultdict(list)
    for s in signals:
        if s.profile_allowed and s.amount != 0 and s.kind != "refund" and s.date <= as_of:
            groups[(s.entity, s.category, s.kind, s.account_id, s.amount > 0)].append(s)
    patterns, changes = [], []
    history_start = min((s.date for s in signals), default=as_of)
    for (entity, category, kind, account, positive), items in sorted(groups.items()):
        items.sort(key=lambda s: (s.date, s.transaction_id))
        # Collapse same-day charges for cadence only; retain all original evidence.
        dates = sorted({s.date for s in items})
        if len(dates) < 2:
            continue
        gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
        med = stats.median(gaps)
        cadence = next((name for name, lo, hi in
                        [("weekly", 5, 9), ("monthly", 24, 38), ("quarterly", 80, 100), ("yearly", 350, 380)]
                        if lo <= med <= hi), None)
        if cadence is None or (len(dates) < 3 and cadence != "yearly"):
            continue
        tolerance = {"weekly": 2, "monthly": 7, "quarterly": 12, "yearly": 16}[cadence]
        regularity = sum(abs(g - med) <= tolerance for g in gaps) / len(gaps)
        if regularity < .75:
            continue
        is_bill = category in BILLS or all(s.payment_method in {"direct_debit", "standing_order"} for s in items)
        is_flow = kind in {"income", "savings", "transfer"} or is_bill
        typ = ("RECURRING_INCOME" if kind == "income" else "RECURRING_TRANSFER"
               if kind in {"savings", "transfer"} else "RECURRING_PAYMENT" if is_bill else "RECURRING_MERCHANT")
        # Large variability reduces confidence, but salary changes and variable utilities retain cadence.
        amounts = [abs(s.amount) for s in items]
        variability = stats.pstdev(amounts) / stats.mean(amounts)
        confidence = round(max(.5, min(.97, .65 + .3 * regularity - min(.2, variability * .15))), 3)
        day = int(stats.median(d.day for d in dates[-6:]) + .5)
        nxt = advance(dates[-1], cadence, day)
        active = as_of <= nxt + dt.timedelta(days=tolerance)
        # Overdue occurrences remain overdue; never silently roll a missing salary forward.
        next_date = nxt if active else None
        amount = items[-1].amount if is_flow else stats.mean(s.amount for s in items[-3:])
        factor = {"weekly": 52 / 12, "monthly": 1, "quarterly": 1 / 3, "yearly": 1 / 12}[cadence]
        p = Pattern(id=stable_id(entity, category, kind, account, positive), type=typ, entity=entity,
                    category=category, kind=kind, cadence=cadence, amount=round(amount, 2),
                    monthly_amount=round(abs(amount) * factor, 2), usual_day=day,
                    first_date=dates[0], last_date=dates[-1], next_date=next_date, active=active,
                    confidence=confidence, evidence=evidence(items, "cadence_with_date_tolerance"))
        patterns.append(p)
        if not is_flow:
            continue
        if kind == "income":
            appeared, disappeared = "NEW_INCOME_SOURCE", "INCOME_DISAPPEARED"
        elif category == "subscription":
            appeared, disappeared = "SUBSCRIPTION_APPEARED", "SUBSCRIPTION_DISAPPEARED"
        else:
            appeared, disappeared = "RECURRING_BILL_APPEARED", "RECURRING_BILL_DISAPPEARED"
        if kind not in {"savings", "transfer"}:
            if (dates[0] - history_start).days >= 60:
                count = 2 if cadence == "yearly" else 3
                confirmation = dates[count-1]
                changes.append(change(appeared, entity, confirmation, [s for s in items if s.date <= confirmation],
                                      current=abs(amount), confidence=confidence))
            for i in range(1 if cadence == "yearly" else 2, len(dates)-1):
                historical_day = int(stats.median(d.day for d in dates[max(0, i-5):i+1]) + .5)
                missed = advance(dates[i], cadence, historical_day)+dt.timedelta(days=tolerance+1)
                if missed < dates[i+1]:
                    prefix = [s for s in items if s.date <= dates[i]]
                    changes.append(change(disappeared, entity, missed, prefix,
                                          previous=abs(prefix[-1].amount), current=0, confidence=.7))
            if not active:
                changes.append(change(disappeared, entity, nxt + dt.timedelta(days=tolerance + 1), items,
                                      previous=abs(amount), current=0, confidence=.7))
        price_kind = ("SALARY_CHANGED" if category == "salary" else "SUBSCRIPTION_PRICE_CHANGED"
                      if category == "subscription" else "DEBT_PAYMENT_CHANGED" if category in DEBT else None)
        if price_kind:
            for i in range(2, len(items)):
                previous = stats.median(abs(s.amount) for s in items[max(0, i-3):i])
                current = abs(items[i].amount)
                # Compare adjacent charges too: emit once at each change, not every month of a new regime.
                adjacent = abs(items[i-1].amount)
                if previous and abs(current - previous) / previous >= .05 and abs(current - adjacent) / adjacent >= .05:
                    changes.append(change(price_kind, entity, items[i].date, items[max(0, i-3):i+1],
                                          previous, current, .9))
    return patterns, changes


def transaction_events(signals: list[Signal]) -> list[Change]:
    result = []
    seen_merchants, seen_categories, foreign_seen = set(), set(), False
    start = min((s.date for s in signals), default=None)
    prior_expenses = []
    for s in sorted(signals, key=lambda s: (s.date, s.transaction_id)):
        if s.kind != "expense":
            continue
        established = start is not None and (s.date - start).days >= 60
        if s.profile_allowed and established:
            if s.entity not in seen_merchants:
                result.append(change("NEW_MERCHANT", s.entity, s.date, [s], current=abs(s.amount), confidence=.95))
            if s.category not in seen_categories:
                result.append(change("NEW_CATEGORY", s.category, s.date, [s], current=abs(s.amount), confidence=.95))
            baseline = [x for x in prior_expenses if 0 < (s.date - x.date).days <= 180]
            if len(baseline) >= 10:
                median = stats.median(abs(x.amount) for x in baseline)
                if abs(s.amount) >= max(500, median * 4):
                    result.append(change("UNUSUALLY_LARGE_TRANSACTION", s.entity, s.date, baseline + [s],
                                          median, abs(s.amount), .8, "four_times_personal_median_min_500"))
        if s.profile_allowed:
            if s.country and s.country != "BE" and not foreign_seen:
                result.append(change("FOREIGN_SPENDING_APPEARED", s.entity, s.date, [s],
                                      current=abs(s.amount), confidence=.95, method="explicit_country_not_BE"))
                foreign_seen = True
            seen_merchants.add(s.entity)
            seen_categories.add(s.category)
            prior_expenses.append(s)
    return result
