"""Component registry + deterministic layout planner (DESIGN.md §6.6).

`plan_layout(features, persona_mix, prefs, customer, txs, as_of, cards) -> Layout`

Pure: no I/O, no date.today(). Every placed section gets a plain-English explanation.
Props follow docs/COMPONENT-PROPS.md exactly; every field is always present.

Tuning knobs live in the constants block at the top.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field
from statistics import median
from typing import Callable

from ..schemas import (
    Card,
    Customer,
    Features,
    GalleryItem,
    HERO_COMPONENTS,
    Layout,
    LayoutPrefRow,
    Persona,
    PersonaWeight,
    Prefs,
    Section,
    StylePrefs,
    Theme,
    TileSuggestion,
    Transaction,
)
from app.engine.features import fmt_date, fmt_eur

# ----------------------------------------------------------------------------------
# Tuning knobs
# ----------------------------------------------------------------------------------

DENSITY_BUDGET = {"compact": 6, "comfortable": 5, "large": 4}

THEME_BY_PERSONA: dict[str, dict] = {
    "student": {"density": "compact", "tone": "casual", "contrast": "normal"},
    "young_professional": {"density": "comfortable", "tone": "neutral", "contrast": "normal"},
    "young_family": {"density": "comfortable", "tone": "warm", "contrast": "normal"},
    "freelancer": {"density": "compact", "tone": "business", "contrast": "normal"},
    "retiree": {"density": "large", "tone": "formal", "contrast": "high"},
}
RETIREE_OVERRIDE_WEIGHT = 0.5

# signal boosts
BOOST_STRESS_ADVISOR = 0.65   # > 0.3 from the brief: must beat a young professional's SpendingByCategory (0.8) so a human surfaces under stress
BOOST_STRESS_RUNWAY = 0.7     # > 0.4 from the brief: must beat BalanceHero (0.9) so stress flips the hero for any persona
BOOST_INVOICE_TRACKER = 0.3
BOOST_TAX_HERO = 0.3
BOOST_FAMILY_HERO = 0.3
BOOST_UPCOMING_BILLS = 0.3
BOOST_SENIOR_SCAM = 0.4
BOOST_SENIOR_PENSION = 0.4
BOOST_IDLE_SAVINGS = 0.2
BOOST_SAVINGS_PRODUCT = 0.2

RUNWAY_STRESS_DAYS = 21
SENIOR_AGE = 65
VAT_RATE = 0.21
VAT_DUE_DAY = 20
UPCOMING_BILLS_DAYS = 14
UPCOMING_BILLS_MAX = 5
SPARKLINE_DAYS = 30

SHAREABLE_CATEGORIES = {"leisure", "groceries"}
ADVISOR_NAME = "Els Vermeulen"
ADVISOR_SLOTS = ["Tue 14:00", "Wed 10:30", "Thu 16:00"]
SCAM_TIPS = [
    "KBC never asks for your card code or PIN by phone, SMS or e-mail.",
    "Never install software because a caller asks you to.",
    "In doubt? Hang up and call your branch on the number on your card.",
]
SCAM_HOTLINE = "Card Stop 078 170 170"

# Affinity table: component -> persona -> 0..1
AFFINITY: dict[str, dict[str, float]] = {
    "BalanceHero":        {"student": 0.4, "young_professional": 0.9, "young_family": 0.5, "freelancer": 0.4, "retiree": 0.4},
    "RunwayHero":         {"student": 0.9, "young_professional": 0.3, "young_family": 0.3, "freelancer": 0.3, "retiree": 0.1},
    "FamilyBudgetHero":   {"student": 0.0, "young_professional": 0.2, "young_family": 0.9, "freelancer": 0.2, "retiree": 0.1},
    "TaxReserveHero":     {"student": 0.0, "young_professional": 0.1, "young_family": 0.1, "freelancer": 0.9, "retiree": 0.0},
    "PensionHero":        {"student": 0.0, "young_professional": 0.0, "young_family": 0.0, "freelancer": 0.0, "retiree": 0.9},
    "ForYouFeed":         {"student": 1.0, "young_professional": 1.0, "young_family": 1.0, "freelancer": 1.0, "retiree": 1.0},
    "QuickActions":       {"student": 0.7, "young_professional": 0.7, "young_family": 0.7, "freelancer": 0.7, "retiree": 0.6},
    "UpcomingBills":      {"student": 0.3, "young_professional": 0.4, "young_family": 0.8, "freelancer": 0.4, "retiree": 0.8},
    "SplitBills":         {"student": 0.8, "young_professional": 0.4, "young_family": 0.1, "freelancer": 0.1, "retiree": 0.0},
    "InvoiceTracker":     {"student": 0.0, "young_professional": 0.1, "young_family": 0.1, "freelancer": 0.9, "retiree": 0.0},
    "SavingsGoal":        {"student": 0.3, "young_professional": 0.7, "young_family": 0.7, "freelancer": 0.3, "retiree": 0.2},
    "ScamShield":         {"student": 0.1, "young_professional": 0.1, "young_family": 0.1, "freelancer": 0.1, "retiree": 0.8},
    "AdvisorContact":     {"student": 0.2, "young_professional": 0.2, "young_family": 0.3, "freelancer": 0.3, "retiree": 0.7},
    "SpendingByCategory": {"student": 0.5, "young_professional": 0.8, "young_family": 0.5, "freelancer": 0.4, "retiree": 0.3},
    "KateTile":           {"student": 0.5, "young_professional": 0.45, "young_family": 0.5, "freelancer": 0.45, "retiree": 0.5},
    "SubscriptionsTile":  {"student": 0.6, "young_professional": 0.6, "young_family": 0.4, "freelancer": 0.3, "retiree": 0.3},
}

SIZE: dict[str, str] = {c: "hero" for c in HERO_COMPONENTS}
SIZE.update({"ForYouFeed": "full", "QuickActions": "full", "KateTile": "full"})
for _c in AFFINITY:
    SIZE.setdefault(_c, "half")

BOOST_KATE_ACTIVE_CARD = 0.2      # Kate has something to talk about (a soon/urgent card)
BOOST_SUBSCRIPTIONS = 0.25        # 3+ subscriptions, or one just got more expensive
SUBSCRIPTIONS_MIN = 3
SUGGESTION_LOOKBACK_DAYS = 120    # a life event this recent can trigger a "add this tile?" suggestion
SUGGESTION_SNOOZE_DAYS = 90       # "Not now" hides a suggestion this long
HERO_SWITCH_MARGIN = 0.25         # a pinned hero is challenged only when another hero scores this much higher
MAX_SUGGESTIONS = 2

# Customer-facing names for the tile gallery and suggestions
TILE_LABEL: dict[str, tuple[str, str]] = {
    "BalanceHero": ("Balance", "Your balance with a 30-day trend"),
    "RunwayHero": ("Runway", "How far your money stretches until the next income"),
    "FamilyBudgetHero": ("Family budget", "This month's family income and spending"),
    "TaxReserveHero": ("Tax reserve", "VAT and social contributions to set aside"),
    "PensionHero": ("Pension overview", "Pension received and bills ahead"),
    "ForYouFeed": ("For you", "The few things worth your attention"),
    "QuickActions": ("Quick actions", "Shortcuts that fit how you bank"),
    "UpcomingBills": ("Upcoming bills", "Recurring payments in the next 14 days"),
    "SplitBills": ("Split bills", "Share costs with friends or roommates"),
    "InvoiceTracker": ("Invoices", "Client payments and income smoothing"),
    "SavingsGoal": ("Savings goal", "Progress towards what you're saving for"),
    "ScamShield": ("Scam shield", "Safety tips and a direct line to your bank"),
    "AdvisorContact": ("Your advisor", "A real person, one tap away"),
    "SpendingByCategory": ("Spending", "Where your money went this month"),
    "KateTile": ("Ask Kate", "Your assistant, ready with what matters now"),
    "SubscriptionsTile": ("Subscriptions", "Everything you pay for every month"),
}

# Kate's starter questions per card type (also used by engine/kate.py)
KATE_QUICK_REPLIES: dict[str, list[str]] = {
    "insurance_renewal": ["What's the difference in coverage?", "Remind me next week"],
    "vat_reserve": ["How did you calculate this?", "What if I don't set it aside?"],
    "price_increase": ["What else did I subscribe to?", "How much is that per year?"],
    "duplicate_charge": ["What should I do?", "Was I charged twice before?"],
    "runway": ["How can I stretch my money?", "When is my next income?"],
    "cashflow_squeeze": ["Where did my money go?", "How can I stretch my money?"],
    "idle_cash": ["What are my options?", "Why does this matter?"],
    "life_event": ["What should I sort out now?", "Why does my app look like this?"],
    "scam_awareness": ["How do I recognise a scam?", "Call my bank"],
    "pension_savings": ["How does the tax benefit work?", "Is this right for me?"],
    "late_client": ["How late are they usually?", "What should I do?"],
    "protection_gap": ["What does family insurance cover?", "Why am I seeing this?"],
    "new_payee": ["That wasn't me", "Why am I seeing this?"],
}
KATE_GENERAL_REPLIES = ["How am I doing this month?", "Why does my app look like this?"]

PERSONA_LABEL = {
    "student": "a student",
    "young_professional": "a young professional",
    "young_family": "a young family",
    "freelancer": "self-employed",
    "retiree": "retired",
}

QUICK_ACTIONS_BY_PERSONA: dict[str, list[dict]] = {
    "student": [
        {"label": "Split a bill", "action": "split_bill", "icon": "split"},
        {"label": "Send money", "action": "transfer", "icon": "transfer"},
        {"label": "Budget check", "action": "open_budget", "icon": "budget"},
        {"label": "Card settings", "action": "card_settings", "icon": "card"},
    ],
    "young_professional": [
        {"label": "Send money", "action": "transfer", "icon": "transfer"},
        {"label": "Save now", "action": "savings_transfer", "icon": "savings"},
        {"label": "Spending", "action": "open_budget", "icon": "budget"},
        {"label": "Card settings", "action": "card_settings", "icon": "card"},
    ],
    "young_family": [
        {"label": "Family budget", "action": "open_budget", "icon": "budget"},
        {"label": "Save for kids", "action": "savings_transfer", "icon": "savings"},
        {"label": "Send money", "action": "transfer", "icon": "transfer"},
        {"label": "Insurance", "action": "open_insurance", "icon": "insurance"},
    ],
    "freelancer": [
        {"label": "Send invoice", "action": "new_invoice", "icon": "invoice"},
        {"label": "Set aside VAT", "action": "vat_transfer", "icon": "savings"},
        {"label": "Scan receipt", "action": "scan", "icon": "scan"},
        {"label": "Call advisor", "action": "call_advisor", "icon": "call"},
    ],
    "retiree": [
        {"label": "Call my bank", "action": "call_advisor", "icon": "call"},
        {"label": "Pension", "action": "open_pension", "icon": "pension"},
        {"label": "Send money", "action": "transfer", "icon": "transfer"},
    ],
}


# ----------------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------------


def _r(x: float) -> float:
    return round(float(x), 2)


def _weights(persona_mix: list[PersonaWeight]) -> dict[str, float]:
    return {p.persona: p.weight for p in persona_mix}


def _dominant(persona_mix: list[PersonaWeight]) -> Persona:
    if not persona_mix:
        return "young_professional"
    return max(persona_mix, key=lambda p: p.weight).persona


def _pct(w: dict[str, float], persona: str) -> int:
    return int(round(100 * w.get(persona, 0.0)))


def _month_label(d: dt.date) -> str:
    return d.strftime("%B %Y")


def _quarter(d: dt.date) -> tuple[int, int]:
    return d.year, (d.month - 1) // 3 + 1


def _vat_due_date(as_of: dt.date) -> dt.date:
    """20th of the month after the current quarter ends."""
    year, q = _quarter(as_of)
    month = q * 3 + 1
    if month > 12:
        year, month = year + 1, 1
    return dt.date(year, month, VAT_DUE_DAY)


def _balance_series(features: Features, txs: list[Transaction], as_of: dt.date, days: int = SPARKLINE_DAYS) -> list[float]:
    """End-of-day balances for the last `days` days ending at as_of, walking back from features.balance_eur."""
    start = as_of - dt.timedelta(days=days - 1)
    per_day: dict[dt.date, float] = defaultdict(float)
    for t in txs:
        if start <= t.date <= as_of:
            per_day[t.date] += t.amount
    series: list[float] = []
    bal = features.balance_eur
    for i in range(days):
        day = as_of - dt.timedelta(days=i)
        series.append(_r(bal))
        bal -= per_day.get(day, 0.0)
    series.reverse()
    return series


def _has_card(cards: list[Card], *types: str) -> bool:
    return any(c.card_type in types for c in cards)


# ----------------------------------------------------------------------------------
# Props builders (docs/COMPONENT-PROPS.md)
# ----------------------------------------------------------------------------------

Ctx = dict  # {"features", "persona_mix", "customer", "txs", "as_of", "cards", "weights"}


def _props_balance_hero(c: Ctx) -> dict:
    f: Features = c["features"]
    series = _balance_series(f, c["txs"], c["as_of"])
    return {
        "balance_eur": _r(f.balance_eur),
        "monthly_income_eur": _r(f.monthly_income_avg_90d),
        "monthly_spend_eur": _r(f.monthly_spend_avg_90d),
        "trend_30d_eur": _r(series[-1] - series[0]) if series else 0.0,
        "sparkline": series,
    }


def _props_runway_hero(c: Ctx) -> dict:
    f: Features = c["features"]
    as_of: dt.date = c["as_of"]
    days_to_income = max(1, (f.next_income_date - as_of).days) if f.next_income_date else 30
    return {
        "balance_eur": _r(f.balance_eur),
        "runway_days": f.runway_days,
        "next_income_date": f.next_income_date.isoformat() if f.next_income_date else None,
        "next_income_eur": _r(f.next_income_eur) if f.next_income_eur is not None else None,
        "daily_budget_eur": _r(max(0.0, f.balance_eur) / days_to_income),
    }


CHILD_BENEFIT_LOOKBACK_DAYS = 45


def _latest_child_benefit(f: Features, txs: list[Transaction], as_of: dt.date) -> float:
    """Latest child_benefit transaction in the last 45 days (the real monthly amount), else the
    90-day feature average (which is diluted when the benefit only started recently)."""
    since = as_of - dt.timedelta(days=CHILD_BENEFIT_LOOKBACK_DAYS)
    recent = [t for t in txs if t.category == "child_benefit" and t.amount > 0 and since <= t.date <= as_of]
    if recent:
        return max(recent, key=lambda t: t.date).amount
    return f.child_benefit_monthly_eur


def _props_family_hero(c: Ctx) -> dict:
    f: Features = c["features"]
    as_of: dt.date = c["as_of"]
    income = 0.0
    spent_by_cat: dict[str, float] = defaultdict(float)
    for t in c["txs"]:
        if t.date.year == as_of.year and t.date.month == as_of.month and t.date <= as_of:
            if t.amount > 0:
                income += t.amount
            else:
                spent_by_cat[t.category] += -t.amount
    top = sorted(spent_by_cat.items(), key=lambda kv: kv[1], reverse=True)[:4]
    return {
        "month_label": _month_label(as_of),
        "month_income_eur": _r(income),
        "month_spent_eur": _r(sum(spent_by_cat.values())),
        "month_budget_eur": _r(f.monthly_income_avg_90d),
        "child_benefit_eur": _r(_latest_child_benefit(f, c["txs"], as_of)),
        "childcare_eur": _r(f.childcare_monthly_eur),
        "top_categories": [{"category": k, "eur": _r(v)} for k, v in top],
    }


def _props_tax_hero(c: Ctx) -> dict:
    """Uses the VAT reporting period from Features (most recently ended quarter while its return is
    still open, otherwise the running quarter). Falls back to the calendar quarter only if the
    features do not carry a period."""
    f: Features = c["features"]
    as_of: dt.date = c["as_of"]
    due = f.vat_due_date or _vat_due_date(as_of)
    year, q = _quarter(as_of)
    label = f.vat_period_label or f"Q{q} {year}"
    return {
        "quarter_label": label,
        "quarter_income_eur": _r(f.vat_period_invoice_income_eur),
        "reserve_eur": _r(f.vat_period_invoice_income_eur * VAT_RATE),
        "reserve_pct": int(round(VAT_RATE * 100)),
        "vat_due_date": due.isoformat(),
        "days_to_due": (due - as_of).days,
    }


def _props_pension_hero(c: Ctx) -> dict:
    f: Features = c["features"]
    as_of: dt.date = c["as_of"]
    pension_txs = sorted((t for t in c["txs"] if t.category == "pension" and t.date <= as_of), key=lambda t: t.date)
    last = pension_txs[-1] if pension_txs else None
    upcoming = _upcoming_bills(f, as_of)
    return {
        "balance_eur": _r(f.balance_eur),
        "pension_eur": _r(last.amount) if last else _r(f.income_by_category_180d.get("pension", 0.0) / 6),
        "pension_received_date": last.date.isoformat() if last else None,
        "next_pension_date": (last.date + dt.timedelta(days=30)).isoformat() if last else None,
        "upcoming_bills_eur": _r(sum(b["amount_eur"] for b in upcoming)),
        "upcoming_bills_count": len(upcoming),
    }


def _props_feed(c: Ctx) -> dict:
    return {}


def _props_quick_actions(c: Ctx) -> dict:
    dom = _dominant(c["persona_mix"])
    return {"actions": [dict(a) for a in QUICK_ACTIONS_BY_PERSONA[dom]]}


def _upcoming_bills(f: Features, as_of: dt.date) -> list[dict]:
    horizon = as_of + dt.timedelta(days=UPCOMING_BILLS_DAYS)
    bills = [
        {"counterparty": rp.counterparty, "amount_eur": _r(rp.amount_eur), "date": rp.next_date.isoformat(), "category": rp.category}
        for rp in f.recurring_payments
        if as_of <= rp.next_date <= horizon
    ]
    bills.sort(key=lambda b: b["date"])
    return bills[:UPCOMING_BILLS_MAX]


def _props_upcoming_bills(c: Ctx) -> dict:
    bills = _upcoming_bills(c["features"], c["as_of"])
    return {"bills": bills, "total_eur": _r(sum(b["amount_eur"] for b in bills))}


def _props_split_bills(c: Ctx) -> dict:
    as_of: dt.date = c["as_of"]
    recent = [
        t for t in c["txs"]
        if t.amount < 0 and t.category in SHAREABLE_CATEGORIES and as_of - dt.timedelta(days=14) <= t.date <= as_of
    ]
    recent.sort(key=lambda t: (t.date, -abs(t.amount)), reverse=True)
    items = [{"counterparty": t.counterparty, "amount_eur": _r(-t.amount), "date": t.date.isoformat()} for t in recent[:3]]
    hint = "Tap a spend to request your share from a friend." if items else "Shared a meal or groceries? Request your share here."
    return {"recent": items, "hint": hint}


def _props_invoice_tracker(c: Ctx) -> dict:
    """Clients = distinct invoice payers in the last 180 days.
    'Unpaid' heuristic: a client whose usual gap between invoices (median, or 45 days if only one
    invoice) has been exceeded by more than 25 % since their last payment is counted as an open invoice
    worth their average invoice amount."""
    f: Features = c["features"]
    as_of: dt.date = c["as_of"]
    since = as_of - dt.timedelta(days=180)
    by_client: dict[str, list[Transaction]] = defaultdict(list)
    for t in c["txs"]:
        if t.category == "invoice_income" and since <= t.date <= as_of:
            by_client[t.counterparty].append(t)
    clients = []
    unpaid = 0
    unpaid_eur = 0.0
    for name, ts in by_client.items():
        ts.sort(key=lambda t: t.date)
        total = sum(t.amount for t in ts)
        avg = total / len(ts)
        gaps = [(b.date - a.date).days for a, b in zip(ts, ts[1:])]
        usual_gap = median(gaps) if gaps else 45
        if (as_of - ts[-1].date).days > usual_gap * 1.25:
            unpaid += 1
            unpaid_eur += avg
        clients.append({"name": name, "eur": _r(total), "last_date": ts[-1].date.isoformat()})
    clients.sort(key=lambda x: x["eur"], reverse=True)
    return {
        "unpaid": unpaid,
        "unpaid_eur": _r(unpaid_eur),
        "paid_quarter_eur": _r(f.quarter_invoice_income_eur),
        "clients": clients[:4],
    }


def _props_savings_goal(c: Ctx) -> dict:
    f: Features = c["features"]
    as_of: dt.date = c["as_of"]
    since = as_of - dt.timedelta(days=365)
    transfers = [-t.amount for t in c["txs"] if t.category == "savings_transfer" and t.amount < 0 and since <= t.date <= as_of]
    saved = sum(transfers)
    monthly = saved / 12 if transfers else 0.0
    target = monthly * 12 if monthly > 0 else max(1000.0, round(f.monthly_spend_avg_90d * 3, -2))
    return {
        "goal_label": "Child savings" if f.has_child_signals else "Rainy-day fund",
        "saved_eur": _r(saved),
        "target_eur": _r(target),
        "monthly_eur": _r(monthly),
    }


def _props_scam_shield(c: Ctx) -> dict:
    return {"tips": list(SCAM_TIPS), "hotline": SCAM_HOTLINE}


def _stress_reason(f: Features, cards: list[Card]) -> str | None:
    if f.runway_days is not None and f.runway_days <= RUNWAY_STRESS_DAYS:
        return f"Your balance may run out in about {f.runway_days} days"
    if _has_card(cards, "cashflow_squeeze"):
        return "Your spending rose sharply this month"
    if _has_card(cards, "runway"):
        return "Your balance is heading below zero"
    return None


def _props_advisor_contact(c: Ctx) -> dict:
    f: Features = c["features"]
    reason = _stress_reason(f, c["cards"])
    if reason is None:
        dom = _dominant(c["persona_mix"])
        reason = {
            "retiree": "A yearly check-in on your pension and savings",
            "freelancer": "A check-in on your quarterly reserves",
            "young_family": "A chat about saving for your family",
        }.get(dom, "Talk to a person whenever you need to")
    return {"advisor_name": ADVISOR_NAME, "reason": reason, "slots": list(ADVISOR_SLOTS)}


def _props_kate_tile(c: Ctx) -> dict:
    cards: list[Card] = c["cards"]
    top = cards[0] if cards else None
    if top is None:
        return {"prompt": "Nothing needs your attention. Ask me anything about your money.",
                "card_key": None, "quick_replies": list(KATE_GENERAL_REPLIES)}
    return {
        "prompt": f"Shall we look at this together? “{top.title}”",
        "card_key": top.card_key,
        "quick_replies": list(KATE_QUICK_REPLIES.get(top.card_type, KATE_GENERAL_REPLIES))[:2],
    }


def _subscriptions(f: Features) -> list:
    return [r for r in f.recurring_payments if r.category == "subscription"]


def _props_subscriptions(c: Ctx) -> dict:
    subs = sorted(_subscriptions(c["features"]), key=lambda r: r.amount_eur * 30 / max(1, r.period_days), reverse=True)
    return {
        "monthly_total_eur": _r(sum(r.amount_eur * 30 / max(1, r.period_days) for r in subs)),
        "count": len(subs),
        "items": [{"counterparty": r.counterparty[:40], "amount_eur": _r(r.amount_eur), "period_days": r.period_days,
                   "previous_amount_eur": _r(r.previous_amount_eur) if r.previous_amount_eur is not None else None}
                  for r in subs[:6]],
    }


def _props_spending(c: Ctx) -> dict:
    f: Features = c["features"]
    top = sorted(f.spend_by_category_30d.items(), key=lambda kv: kv[1], reverse=True)[:6]
    return {
        "month_label": _month_label(c["as_of"]),
        "total_eur": _r(sum(f.spend_by_category_30d.values())),
        "categories": [{"category": k, "eur": _r(v)} for k, v in top],
    }


# ----------------------------------------------------------------------------------
# Registry
# ----------------------------------------------------------------------------------

REGISTRY: dict[str, dict] = {
    name: {"affinity": AFFINITY[name], "size": SIZE[name], "props": builder}
    for name, builder in {
        "BalanceHero": _props_balance_hero,
        "RunwayHero": _props_runway_hero,
        "FamilyBudgetHero": _props_family_hero,
        "TaxReserveHero": _props_tax_hero,
        "PensionHero": _props_pension_hero,
        "ForYouFeed": _props_feed,
        "QuickActions": _props_quick_actions,
        "UpcomingBills": _props_upcoming_bills,
        "SplitBills": _props_split_bills,
        "InvoiceTracker": _props_invoice_tracker,
        "SavingsGoal": _props_savings_goal,
        "ScamShield": _props_scam_shield,
        "AdvisorContact": _props_advisor_contact,
        "SpendingByCategory": _props_spending,
        "KateTile": _props_kate_tile,
        "SubscriptionsTile": _props_subscriptions,
    }.items()
}


# ----------------------------------------------------------------------------------
# Scoring
# ----------------------------------------------------------------------------------


def score_components(features: Features, persona_mix: list[PersonaWeight], cards: list[Card]) -> tuple[dict[str, float], dict[str, str]]:
    """Returns (score per component, boost reason per component)."""
    w = _weights(persona_mix)
    scores = {name: sum(w.get(p, 0.0) * a for p, a in entry["affinity"].items()) for name, entry in REGISTRY.items()}
    reasons: dict[str, str] = {}

    stress = _stress_reason(features, cards)
    if stress:
        scores["AdvisorContact"] += BOOST_STRESS_ADVISOR
        scores["RunwayHero"] += BOOST_STRESS_RUNWAY
        reasons["AdvisorContact"] = f"{stress.lower()}, so a human is one tap away."
        reasons["RunwayHero"] = f"{stress.lower()}, so we show how long your money lasts."
    if features.has_invoice_income:
        scores["InvoiceTracker"] += BOOST_INVOICE_TRACKER
        scores["TaxReserveHero"] += BOOST_TAX_HERO
        reasons["InvoiceTracker"] = f"you invoice {features.income_sources_180d} client(s)."
    if features.has_child_signals:
        scores["FamilyBudgetHero"] += BOOST_FAMILY_HERO
        scores["UpcomingBills"] += BOOST_UPCOMING_BILLS
        reasons["UpcomingBills"] = "family months are tight on timing, so upcoming bills stay in view."
    if features.age >= SENIOR_AGE:
        scores["ScamShield"] += BOOST_SENIOR_SCAM
        scores["PensionHero"] += BOOST_SENIOR_PENSION
        reasons["ScamShield"] = f"you're {features.age}, and scams increasingly target people your age."
    if features.idle_cash_eur > 0:
        scores["SavingsGoal"] += BOOST_IDLE_SAVINGS
        reasons["SavingsGoal"] = f"about {fmt_eur(features.idle_cash_eur)} is sitting idle on your account."
    if features.has_savings_product:
        scores["SavingsGoal"] += BOOST_SAVINGS_PRODUCT
        reasons.setdefault("SavingsGoal", "you transfer to a savings account regularly.")
    active = next((c for c in cards if c.stage in ("soon", "urgent")), None)
    if active is not None:
        scores["KateTile"] += BOOST_KATE_ACTIVE_CARD
        reasons["KateTile"] = "something needs your attention, and Kate can walk you through it."
    subs = _subscriptions(features)
    raised = [r for r in subs if r.previous_amount_eur is not None and r.amount_eur > r.previous_amount_eur]
    if len(subs) >= SUBSCRIPTIONS_MIN or raised:
        scores["SubscriptionsTile"] += BOOST_SUBSCRIPTIONS
        reasons["SubscriptionsTile"] = (f"{raised[0].counterparty[:40]} just got more expensive." if raised
                                        else f"you pay for {len(subs)} subscriptions.")
    return scores, reasons


# ----------------------------------------------------------------------------------
# Explanations
# ----------------------------------------------------------------------------------


def _persona_phrase(w: dict[str, float], persona_mix: list[PersonaWeight]) -> str:
    dom = _dominant(persona_mix)
    return f"you're mainly {PERSONA_LABEL[dom]} ({_pct(w, dom)}%)"


def _explain(component: str, ctx: Ctx, reasons: dict[str, str], pinned: bool) -> str:
    f: Features = ctx["features"]
    w: dict[str, float] = ctx["weights"]
    mix: list[PersonaWeight] = ctx["persona_mix"]
    who = _persona_phrase(w, mix)
    if pinned:
        return "Pinned by you."
    if component == "ForYouFeed":
        return "Always shown: the few things worth your attention right now."
    if component == "TaxReserveHero":
        days = ((f.vat_due_date or _vat_due_date(ctx["as_of"])) - ctx["as_of"]).days
        return f"Because {who}, and your VAT return is due in {days} days."
    if component == "RunwayHero":
        if "RunwayHero" in reasons:
            return f"Because {reasons['RunwayHero']}"
        return f"Because {who}: what matters is how far your balance stretches until the next income."
    if component == "FamilyBudgetHero":
        return f"Because {who}, with child benefit and childcare shaping the month."
    if component == "PensionHero":
        return f"Because {who}: pension received, bills ahead, calm overview."
    if component == "BalanceHero":
        return f"Because {who}, a plain balance with a trend is the most useful start."
    if component in reasons:
        return f"Because {reasons[component]}"
    fit = max(REGISTRY[component]["affinity"].items(), key=lambda kv: w.get(kv[0], 0.0) * kv[1])[0]
    return f"Fits {PERSONA_LABEL[fit]} ({_pct(w, fit)}% of your profile)."


def _theme_explanation(theme: dict, features: Features, persona_mix: list[PersonaWeight], w: dict[str, float]) -> str:
    dom = _dominant(persona_mix)
    if theme["contrast"] == "high":
        return f"Large text and high contrast because you're {features.age} and your main persona is retiree ({_pct(w, 'retiree')}%)."
    return f"{theme['density'].capitalize()} layout with a {theme['tone']} tone because your main persona is {PERSONA_LABEL[dom]} ({_pct(w, dom)}%)."


# ----------------------------------------------------------------------------------
# Planner
# ----------------------------------------------------------------------------------

STYLE_LABEL = {
    "density": {"compact": "compact text", "comfortable": "comfortable text", "large": "large text"},
    "contrast": {"normal": "normal contrast", "high": "high contrast"},
    "tone": {t: f"a {t} tone" for t in ("casual", "neutral", "warm", "business", "formal")},
    "appearance": {"light": "light mode", "dark": "dark mode"},
    "accent": {a: f"a {a} accent" for a in ("blue", "teal", "purple", "amber", "navy")},
}


def plan_theme(persona_mix: list[PersonaWeight]) -> dict:
    w = _weights(persona_mix)
    theme = dict(THEME_BY_PERSONA[_dominant(persona_mix)])
    if w.get("retiree", 0.0) >= RETIREE_OVERRIDE_WEIGHT:
        theme["density"] = "large"
        theme["contrast"] = "high"
    return theme


def apply_style(theme: dict, style: StylePrefs) -> tuple[dict, list[str]]:
    """Customer overrides win over the adaptive theme. Returns (theme, keys the customer set)."""
    out = dict(theme, appearance="light", accent=None, reduce_motion=style.reduce_motion, privacy=style.privacy)
    overrides: list[str] = []
    for key in ("density", "contrast", "tone", "appearance", "accent"):
        value = getattr(style, key)
        if value is not None:
            out[key] = value
            overrides.append(key)
    return out, overrides


def _style_phrase(theme: dict, overrides: list[str]) -> str:
    parts = [STYLE_LABEL[k][theme[k]] for k in overrides if theme.get(k) in STYLE_LABEL[k]]
    return "You chose " + ", ".join(parts) + "." if parts else ""


@dataclass
class Plan:
    layout: Layout
    suggestions: list[TileSuggestion] = field(default_factory=list)
    gallery: list[GalleryItem] = field(default_factory=list)


def _place(rest_slots: int, pinned: list[LayoutPrefRow], candidates: list[str]) -> list[str]:
    """Pinned tiles keep their slot; the adaptive tiles flow around them.
    position None = the first free slot (a freshly added tile shows up right under the feed)."""
    slots: list[str | None] = [None] * rest_slots
    for p in [p for p in pinned if p.position is not None]:
        free = [i for i in range(rest_slots) if slots[i] is None]
        if not free:
            break
        want = min(p.position, rest_slots - 1)
        slots[min(free, key=lambda i: (abs(i - want), i))] = p.component
    for p in [p for p in pinned if p.position is None]:
        free = [i for i in range(rest_slots) if slots[i] is None]
        if not free:
            break
        slots[free[0]] = p.component
    fill = iter(candidates)
    for i in range(rest_slots):
        if slots[i] is None:
            slots[i] = next(fill, None)
    return [s for s in slots if s is not None]


DECLARED_TRIGGERS: dict[str, tuple[str, str, list[str]]] = {
    "expecting_baby": ("You told Kate you're expecting",
                       "Let's get ready together: a savings goal and a family view.",
                       ["SavingsGoal", "FamilyBudgetHero"]),
    "going_freelance": ("You told Kate you're going freelance",
                        "Keep an eye on VAT and invoices from day one.",
                        ["TaxReserveHero", "InvoiceTracker"]),
    "retiring": ("You told Kate you're retiring",
                 "A calm overview of your pension and bills.",
                 ["PensionHero", "UpcomingBills"]),
    "studying": ("You told Kate you're studying",
                 "See how far your money stretches each month.",
                 ["RunwayHero", "SplitBills"]),
}


def _recent_triggers(features: Features, prefs: Prefs, as_of: dt.date) -> list[tuple[dt.date, str, str, list[str]]]:
    """(date, title, reason, components) for recent life events and things the customer told Kate."""
    out: list[tuple[dt.date, str, str, list[str]]] = []
    since = as_of - dt.timedelta(days=SUGGESTION_LOOKBACK_DAYS)
    for e in features.life_events:
        if not (since <= e.date <= as_of):
            continue
        when = fmt_date(e.date)
        if e.type == "first_invoice":
            out.append((e.date, "You've started invoicing clients",
                        f"Your first client payment arrived on {when}. Keep VAT and social contributions in view.",
                        ["TaxReserveHero", "InvoiceTracker"]))
        elif e.type == "baby":
            out.append((e.date, "Congratulations on your new arrival",
                        f"We noticed baby-related spending since {when}. A family view helps with the new costs.",
                        ["FamilyBudgetHero", "SavingsGoal", "UpcomingBills"]))
        elif e.type in ("pension_start", "first_pension"):
            out.append((e.date, "Your pension has started",
                        f"Your first pension payment arrived on {when}. A calm overview of pension and bills.",
                        ["PensionHero", "ScamShield"]))
        elif e.type == "first_salary":
            out.append((e.date, "Your first salary!",
                        f"Your first salary arrived on {when}. A savings goal makes it easy to put some aside.",
                        ["SavingsGoal", "SpendingByCategory"]))
        elif e.type == "moved_house":
            out.append((e.date, "New home, new bills",
                        f"Your mortgage started on {when}. Keep upcoming bills in view.",
                        ["UpcomingBills"]))
    for d in prefs.declared:
        if since <= d.created_at <= as_of:
            title, reason, comps = DECLARED_TRIGGERS[d.signal]
            out.append((d.created_at, title, reason, comps))
    out.sort(key=lambda t: t[0], reverse=True)
    return out


def plan_suggestions(features: Features, prefs: Prefs, as_of: dt.date, scores: dict[str, float],
                     reasons: dict[str, str], order: list[str], pinned_hero: str | None) -> list[TileSuggestion]:
    """The system proposes, the customer decides: tiles that fit a recent change but aren't on the home screen."""
    hidden = {p.component for p in prefs.layout_prefs if p.state == "hidden"}
    snoozed = {d.component for d in prefs.dismissed_suggestions
               if d.created_at <= as_of and (as_of - d.created_at).days < SUGGESTION_SNOOZE_DAYS}
    hero = order[0]
    out: list[TileSuggestion] = []

    def open_slot(comp: str) -> bool:
        if comp in hidden or comp in snoozed or any(s.component == comp for s in out):
            return False
        return comp != hero if comp in HERO_COMPONENTS else comp not in order

    # 1. life changed (observed in transactions, or told to Kate)
    for _, title, reason, comps in _recent_triggers(features, prefs, as_of):
        comp = next((c for c in comps if open_slot(c)), None)
        if comp:
            out.append(TileSuggestion(component=comp, title=title, reason=reason, as_hero=comp in HERO_COMPONENTS))
    # 2. the customer pinned a hero, but another one now fits much better
    if pinned_hero:
        best = max(HERO_COMPONENTS, key=lambda h: (scores[h], -HERO_COMPONENTS.index(h)))
        if best != pinned_hero and scores[best] - scores[pinned_hero] >= HERO_SWITCH_MARGIN and open_slot(best):
            why = reasons.get(best, "it fits your situation better now.")
            out.append(TileSuggestion(component=best, title=f"Switch your main tile to {TILE_LABEL[best][0]}?",
                                      reason=f"You pinned {TILE_LABEL[pinned_hero][0]}, but {why}", as_hero=True))
    return out[:MAX_SUGGESTIONS]


def plan_gallery(scores: dict[str, float], reasons: dict[str, str], order: list[str], hidden: set[str],
                 ctx: Ctx) -> list[GalleryItem]:
    items = []
    for comp in sorted(REGISTRY, key=lambda c: (-scores[c], c)):
        if comp == "ForYouFeed":
            continue
        state = "shown" if comp in order else "hidden" if comp in hidden else "available"
        label, desc = TILE_LABEL[comp]
        items.append(GalleryItem(component=comp, label=label, description=desc,
                                 reason=_explain(comp, ctx, reasons, False), score=round(scores[comp], 3),
                                 state=state, is_hero=comp in HERO_COMPONENTS))
    for item in [i for i in items if i.state == "available"][:3]:
        item.suggested = True
    return items


def plan_home_layout(
    features: Features,
    persona_mix: list[PersonaWeight],
    prefs: Prefs,
    customer: Customer,
    txs: list[Transaction],
    as_of: dt.date,
    cards: list[Card],
) -> Plan:
    if not persona_mix:
        persona_mix = [PersonaWeight(persona="young_professional", weight=1.0, evidence=["Default profile"])]
    w = _weights(persona_mix)
    ctx: Ctx = {
        "features": features, "persona_mix": persona_mix, "customer": customer,
        "txs": txs, "as_of": as_of, "cards": cards, "weights": w,
    }
    scores, reasons = score_components(features, persona_mix, cards)
    auto_theme = plan_theme(persona_mix)
    theme, overrides = apply_style(auto_theme, prefs.style)

    hidden = {p.component for p in prefs.layout_prefs if p.state == "hidden"}
    pins = [p for p in prefs.layout_prefs if p.state == "pinned" and p.component in REGISTRY]
    pinned_heroes = [p.component for p in pins if p.component in HERO_COMPONENTS]
    pinned_hero = pinned_heroes[-1] if pinned_heroes else None
    pinned_rest = [p for p in pins if p.component not in HERO_COMPONENTS and p.component != "ForYouFeed"
                   and p.component not in hidden]
    pinned_names = {p.component for p in pinned_rest}

    # 1. hero: the customer's pinned one, else the best-scoring
    hero = pinned_hero or max(HERO_COMPONENTS, key=lambda h: (scores[h], -HERO_COMPONENTS.index(h)))
    # 2. feed right after; pinned tiles keep their slots and the best of the rest fills the gaps
    budget = max(DENSITY_BUDGET[theme["density"]], 2 + len(pinned_rest))
    candidates = [
        c for c in sorted(REGISTRY, key=lambda c: (-scores[c], c))
        if c not in HERO_COMPONENTS and c != "ForYouFeed" and c not in hidden and c not in pinned_names
    ]
    order = [hero, "ForYouFeed"] + _place(budget - 2, pinned_rest, candidates)
    pinned_set = pinned_names | ({pinned_hero} if pinned_hero else set())

    sections = [Section(component=c, size=REGISTRY[c]["size"], props=REGISTRY[c]["props"](ctx), pinned=c in pinned_set)
                for c in order]
    explanations = {c: _explain(c, ctx, reasons, c in pinned_set) for c in order}
    auto_why = _theme_explanation(auto_theme, features, persona_mix, w)
    chose = _style_phrase(theme, overrides)
    explanations["theme"] = f"{chose} Otherwise: {auto_why}" if chose else auto_why

    layout = Layout(version=1, theme=Theme(**theme, overrides=overrides), sections=sections, explanations=explanations)
    return Plan(
        layout=layout,
        suggestions=plan_suggestions(features, prefs, as_of, scores, reasons, order, pinned_hero),
        gallery=plan_gallery(scores, reasons, order, hidden, ctx),
    )


def plan_layout(
    features: Features,
    persona_mix: list[PersonaWeight],
    prefs: Prefs,
    customer: Customer,
    txs: list[Transaction],
    as_of: dt.date,
    cards: list[Card],
) -> Layout:
    return plan_home_layout(features, persona_mix, prefs, customer, txs, as_of, cards).layout
