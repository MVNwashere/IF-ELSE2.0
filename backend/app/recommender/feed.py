"""Nine soft personas, ten core cards and the 100-card content catalogue.

Only observed, non-sensitive signals may trigger a recommendation. The catalogue
contains concepts; an entry is shown only when its eligibility can be supported.
"""
from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

from ..customer_state.models import CustomerState
from ..schemas import Card, Customer, Feed, Prefs
from ..engine.features import fmt_eur

CATALOGUE = json.loads(Path(__file__).with_name("catalogue.json").read_text(encoding="utf-8"))
CATALOGUE_BY_ID = {item["id"]: item for item in CATALOGUE}
PERSONA_CODES = ("TEEN", "STU", "YPRO", "PAR", "HOME", "SELF", "INV", "PRE", "SEN")
PERSONA_NAMES = {"TEEN": "youth", "STU": "student", "YPRO": "young professional",
                 "PAR": "parent", "HOME": "household", "SELF": "self-employed",
                 "INV": "investor", "PRE": "pre-retirement", "SEN": "retiree"}
MAX_CARDS = 7
MAX_CORE_CARDS = 4
MAX_COMMERCIAL = 2
RECENT_DAYS = 45
SNOOZE_DAYS = 7
ACTIVE_SIGNAL_DAYS = 395


def _signals(state: CustomerState, category: str, *, days: int | None = None) -> list:
    return [s for s in state.signals if s.profile_allowed and s.currency == "EUR" and s.category == category
            and (days is None or 0 <= (state.as_of - s.date).days <= days)]


def _products(customer: Customer, state: CustomerState) -> set[str]:
    """Products are undated source data, so do not project today's holdings into time travel."""
    reference = state.freshness.get("balance_reference")
    return (set(customer.products) | set(state.observations.products)) if reference == state.as_of.isoformat() else set()


def infer_personas(customer: Customer, state: CustomerState, prefs: Prefs) -> list[dict]:
    """Return weighted persona scores and the observations behind each score."""
    age = state.as_of.year - customer.birth_year
    products = _products(customer, state)
    has = lambda category: bool(_signals(state, category, days=ACTIVE_SIGNAL_DAYS))
    raw: dict[str, tuple[float, list[str]]] = {}
    raw["TEEN"] = (1.0 if age < 18 or "youth" in products else 0.0, [f"Age {age}"])
    student_age = 18 <= age <= 25
    raw["STU"] = ((0.5 if student_age else 0) + (0.4 if student_age and (has("student_income") or has("tuition")) else 0)
                  + (0.2 if student_age and has("allowance_from_parents") else 0),
                  [f"Age {age}"] + (["Recent education-related payments"] if has("student_income") or has("tuition") else []))
    raw["YPRO"] = ((0.5 if 22 <= age <= 34 and has("salary") else 0)
                   + (0.2 if 22 <= age <= 34 and has("rent") else 0),
                   (["Recent salary income"] if has("salary") else []) + (["Recent rent payments"] if has("rent") else []))
    child = any(has(c) for c in ("child_benefit", "childcare", "baby", "school"))
    raw["PAR"] = ((0.7 if child else 0) + (0.2 if 28 <= age <= 45 and child else 0),
                  ["Child benefit, childcare or school payments"] if child else [])
    mortgage = has("mortgage")
    raw["HOME"] = ((0.6 if mortgage and 35 <= age <= 58 else 0) + (0.2 if mortgage and 35 <= age <= 58 and has("utilities") else 0),
                   ["Mortgage and household payments"] if mortgage else [])
    business = any(has(c) for c in ("invoice_income", "vat_payment", "social_contribution"))
    raw["SELF"] = ((0.7 if business else 0) + (0.2 if has("vat_payment") else 0),
                   ["Invoice income or business tax payments"] if business else [])
    investment = any("invest" in p or "broker" in p for p in products)
    raw["INV"] = (0.8 if investment else 0, ["Investment product held"] if investment else [])
    raw["PRE"] = ((0.55 if 55 <= age < 67 else 0) + (0.2 if 55 <= age < 67 and (mortgage or has("pension")) else 0),
                  [f"Age {age}; retirement planning period"] if 55 <= age < 67 else [])
    raw["SEN"] = (1.0 if age >= 67 or (has("pension") and not has("salary")) else 0,
                  ["Retirement age or pension as main income"] if age >= 67 or has("pension") else [])
    declared = {d.signal for d in prefs.declared if d.created_at <= state.as_of}
    for signal, code in (("studying", "STU"), ("expecting_baby", "PAR"),
                         ("going_freelance", "SELF"), ("retiring", "PRE")):
        if signal in declared:
            score, evidence = raw[code]
            raw[code] = (score + 0.5, [f"You told Kate: {signal.replace('_', ' ')}"] + evidence)
    if raw["TEEN"][0]:
        raw = {"TEEN": raw["TEEN"]}
    elif age >= 67:
        raw = {k: v for k, v in raw.items() if k not in ("STU", "YPRO")}
    total = sum(score for score, _ in raw.values())
    if total == 0:
        code = "STU" if age < 26 else "YPRO" if age < 35 else "HOME" if age < 55 else "PRE"
        raw = {code: (1.0, [f"Age {age}; no stronger banking signals yet"])}
        total = 1.0
    return [{"code": code, "weight": round(score / total, 4), "evidence": evidence}
            for code, (score, evidence) in sorted(raw.items(), key=lambda item: (-item[1][0], item[0])) if score > 0]


def _card(card_type: str, title: str, body: str, *, family: str = "forecast", stage: str = "info",
          evidence: list[str] | None = None, details: dict | None = None, commercial: bool = False,
          due: dt.date | None = None, impact: float = 0, confidence: float = 0.9) -> Card:
    return Card(card_key=card_type.replace("_", ":", 1), card_type=card_type, family=family, stage=stage,
                title=title, body=body, evidence=evidence or [], details=details or {},
                commercial=commercial, due_date=due, eur_impact=impact, confidence=confidence)


def _core_cards(customer: Customer, state: CustomerState, personas: list[dict]) -> list[Card]:
    age = state.as_of.year - customer.birth_year
    position, cash = state.financial_position, state.cash_flow
    products = _products(customer, state)
    out: list[Card] = []
    if position.current_balance is not None:
        available = age < 26 or age >= 67
        amount = position.current_balance if available else position.total_liquid_balance
        if amount is not None:
            label = "Available to spend" if age < 26 else "Your money"
            breakdown = [{"label": "Current accounts", "value": position.current_balance}]
            if position.known_savings is not None and age >= 18:
                breakdown.append({"label": "Savings", "value": position.known_savings})
            out.append(_card("core_money", label, f"{fmt_eur(amount)} across known accounts" if not available
                             else f"{fmt_eur(amount)} in your current account", family="opportunity",
                             evidence=["Known EUR account balances in Customer State"],
                             details={"kind": "core", "metrics": breakdown, "related": ["core_spending", "core_goals", "core_health"]}))
    month_signals = [s for s in state.signals if s.currency == "EUR" and s.date.year == state.as_of.year
                     and s.date.month == state.as_of.month and s.kind == "expense"]
    spent = round(-sum(s.amount for s in month_signals), 2)
    if month_signals:
        categories: dict[str, float] = defaultdict(float)
        for signal in month_signals:
            categories[signal.category] += -signal.amount
        top = sorted(categories.items(), key=lambda x: -x[1])[:4]
        out.append(_card("core_spending", "Spending this month", f"{fmt_eur(spent)} spent so far this month",
                         evidence=[f"{len(month_signals)} EUR expenses booked this month"],
                         details={"kind": "core", "metrics": [{"label": k.replace("_", " ").title(), "value": round(v, 2)} for k, v in top],
                                  "related": ["core_money", "core_coming_up", "core_health"]}))
    upcoming = sorted(cash.upcoming_outflows, key=lambda flow: flow.date)[:5]
    if upcoming:
        next_flow = upcoming[0]
        low = cash.lowest_projected_balance is not None and cash.lowest_projected_balance < 0
        out.append(_card("core_coming_up", "Coming up", f"Next expected payment: {fmt_eur(abs(next_flow.amount))} on {next_flow.date:%d %b}",
                         family="deadline", stage="urgent" if low else "soon" if (next_flow.date-state.as_of).days <= 3 else "info",
                         due=next_flow.date, evidence=["Projected from observed recurring payments; dates and amounts are estimates"],
                         details={"kind": "core", "metrics": [{"label": f.date.strftime("%d %b"), "value": abs(f.amount)} for f in upcoming],
                                  "related": ["core_money", "core_spending"]}))
    recent_changes = [c for c in state.changes + state.events if 0 <= (state.as_of-c.detected_at).days <= RECENT_DAYS]
    unusual = [c for c in recent_changes if c.type in ("SUBSCRIPTION_PRICE_CHANGED", "UNUSUALLY_LARGE_TRANSACTION",
                                                       "INCOME_DISAPPEARED", "SALARY_CHANGED", "FOREIGN_SPENDING_APPEARED")]
    high_risks = [r for r in state.risks if r.severity == "high"]
    if unusual or high_risks:
        event = unusual[-1] if unusual else None
        title = "Unusual activity" if event is None else event.type.replace("_", " ").title()
        body = "Your projected balance may fall below zero. Review upcoming payments." if high_risks else (
            f"A change involving {event.entity} was detected. Check the details." if event else "Review this change.")
        out.append(_card("core_unusual", title, body, family="anomaly", stage="urgent" if high_risks else "soon",
                         evidence=["A recent Customer State change or risk"] + ([event.id] if event else []),
                         details={"kind": "core", "related": ["core_coming_up", "core_spending"]}))
    insurance = [p for p in state.recurring_payments.items if "insurance" in p.category]
    if age >= 18 and (insurance or any("insurance" in p for p in products)):
        out.append(_card("core_insurance", "Insurance", f"{len(insurance)} recurring insurance payment{'s' if len(insurance) != 1 else ''} found",
                         family="protection", evidence=["Observed insurance payments and held products"],
                         details={"kind": "core", "metrics": [{"label": p.entity, "value": p.amount} for p in insurance[:5]],
                                  "related": ["core_coming_up", "core_money"]}))
    out.append(_card("core_goals", "Your goals", "Try a savings target and see how long it could take.",
                     family="opportunity", evidence=["An example target you can change in the planner"],
                     details={"kind": "core", "planner": {"kind": "savings", "target": 1000,
                                                         "current": 0, "monthly": 50},
                              "related": ["core_money", "core_health"]}, confidence=1))
    invested = any("invest" in p or "broker" in p for p in products)
    if age >= 18 and invested:
        out.append(_card("core_investments", "Investments", "See the investment products linked to your profile.",
                         family="opportunity", evidence=["Investment product held; valuation is not available in Customer State"],
                         details={"kind": "core", "related": ["core_money", "core_health"]}))
    if age >= 18 and position.known_debt is not None and position.known_debt > 0:
        out.append(_card("core_debt", "What you owe", f"{fmt_eur(position.known_debt)} outstanding on known loans and credit",
                         family="forecast", evidence=["Observed EUR loan and credit balances"],
                         details={"kind": "core", "metrics": [{"label": "Known debt", "value": position.known_debt}],
                                  "related": ["core_money", "core_health"]}))
    if any("card" in p for p in products):
        out.append(_card("core_cards", "Your cards", "Review the payment cards linked to your profile.",
                         family="protection", evidence=["Payment card product held"],
                         details={"kind": "core", "related": ["core_money", "core_unusual"]}))
    if age >= 18:
        factors = []
        if cash.cash_buffer_months is not None:
            factors.append(("Cash buffer", min(1, max(0, cash.cash_buffer_months / 3))))
        if cash.average_monthly_free_cash_flow is not None and state.income.estimated_monthly_income:
            factors.append(("Monthly cash flow", min(1, max(0, cash.average_monthly_free_cash_flow / state.income.estimated_monthly_income))))
        if state.savings.savings_rate is not None:
            factors.append(("Savings habit", min(1, max(0, state.savings.savings_rate / 0.2))))
        if state.debt.debt_service_ratio is not None:
            factors.append(("Debt payments", 1-min(1, max(0, state.debt.debt_service_ratio / 0.4))))
        if len(factors) >= 2:
            score = round(100 * sum(value for _, value in factors) / len(factors))
            out.append(_card("core_health", "Financial health", f"{score}/100 based on {len(factors)} available measures",
                             family="forecast", evidence=["Illustrative score from cash buffer, free cash flow, savings and debt payments"],
                             details={"kind": "core", "metrics": [{"label": name, "value": round(value*100)} for name, value in factors],
                                      "metric_unit": "%", "methodology": "Illustrative score: equally weighted cash buffer (3-month target), positive free cash flow, savings rate (20% target), and debt payments (under 40% of income). Only available measures count.",
                                      "related": ["core_money", "core_spending", "core_goals"]}, confidence=0.7))
    return out


def _eligible_catalogue(item: dict, customer: Customer, state: CustomerState, personas: list[dict],
                        prefs: Prefs, indexed: dict[str, list]) -> bool:
    code = item["id"]
    age = state.as_of.year - customer.birth_year
    weights = {p["code"]: p["weight"] for p in personas}
    if not any(weights.get(p, 0) >= 0.18 for p in item["fits"]):
        return False
    if age < 18 and "TEEN" not in item["fits"]:
        return False
    if age >= 67 and code in {"EC-08", "SV-04", "SV-07", "SV-08", "SV-10"}:
        return False
    if item["type"] == "Product" and not customer.consent_personalization:
        return False
    category = lambda name: any(0 <= (state.as_of-s.date).days <= ACTIVE_SIGNAL_DAYS for s in indexed.get(name, []))
    recent = lambda name: any(0 <= (state.as_of-s.date).days <= 35 for s in indexed.get(name, []))
    subscriptions = state.subscriptions.count
    products = _products(customer, state)
    invest = any("invest" in p or "broker" in p for p in products)
    mortgage = "mortgage" in products or category("mortgage")
    has_child = any(category(k) for k in ("child_benefit", "childcare", "baby", "school"))
    cash = state.cash_flow
    # These concepts require data, verified status, an explicit opt-in or a live external
    # source that this application does not yet have. Their definitions stay in the catalogue.
    unavailable = {"YS-04", "YS-05", "YS-07", "YS-08", "EC-04", "EC-05", "EC-06", "EC-09",
                   "EC-10", "FM-02", "FM-04", "FM-06", "FM-07", "FM-08", "FM-09", "FM-10", "HM-01", "HM-02", "HM-04", "HM-05", "HM-06", "HM-08", "HM-09",
                   "TR-01", "TR-02", "TR-03", "TR-04", "TR-05", "TR-06", "TR-08", "TR-09", "TR-10",
                   "SV-03", "SV-04", "SV-05", "SV-06", "SV-08", "SV-09", "SV-10", "BZ-03", "BZ-04", "BZ-05", "BZ-06", "BZ-07",
                   "RT-01", "RT-02", "RT-03", "RT-04", "RT-05", "RT-06", "RT-08", "RT-09", "EL-03", "EL-05", "EL-07",
                   "EL-08", "EL-09", "EL-10", "LE-01", "LE-03", "LE-04", "LE-05", "LE-08",
                   "LE-09", "LE-10", "LE-11"}
    if code in unavailable:
        return False
    conditions = {
        "YS-01": any(0 <= (state.as_of-s.date).days <= 7 for s in indexed.get("allowance_from_parents", [])),
        "YS-02": state.savings.balance in (None, 0),
        "YS-06": cash.liquidity_pressure in ("medium", "high"),
        "YS-09": subscriptions > 0,
        "YS-10": category("student_income") and state.as_of.month in (4, 5, 6),
        "EC-01": recent("salary") and len(_signals(state, "salary")) <= 2,
        "EC-02": category("salary") and (state.savings.average_monthly_savings or 0) <= 0,
        "EC-03": subscriptions >= 5,
        "EC-06": category("rent") and bool(indexed.get("rent") and
                                               (state.as_of-min(s.date for s in indexed["rent"])).days >= 365) and not mortgage,
        "EC-07": any(c.type == "SALARY_CHANGED" for c in state.changes) and state.spending.trend == "increasing",
        "EC-08": (state.savings.balance or 0) >= 1000 and not invest and cash.liquidity_pressure == "low",
        "FM-01": has_child and state.as_of.month in (7, 8, 9),
        "FM-03": recent("child_benefit"),
        "FM-04": has_child and state.as_of.month in (3, 4, 5, 6),
        "FM-05": category("childcare"),
        "FM-10": has_child,
        "HM-01": category("rent") and not mortgage,
        "HM-03": category("rent") and not mortgage,
        "HM-07": any(c.type == "CATEGORY_SPENDING_INCREASED" and c.entity == "utilities" for c in state.changes),
        "HM-10": "car_insurance" in products or "car_loan" in products,
        "TR-07": state.as_of.month in (5, 6, 7, 8),
        "SV-01": cash.cash_buffer_months is not None and cash.cash_buffer_months < 3 and state.expenses.average_monthly_expenses is not None,
        "SV-02": len({(s.date.year, s.date.month) for s in indexed.get("savings_transfer", [])
                      if s.amount < 0 and 0 <= (state.as_of-s.date).days <= 95}) >= 3,
        "SV-04": has_child and cash.liquidity_pressure == "low",
        "SV-08": mortgage and (state.savings.balance or 0) > 0,
        "BZ-01": category("invoice_income") and state.income.income_stability is not None and state.income.income_stability < 0.8,
        "BZ-02": category("invoice_income"),
        "BZ-08": category("invoice_income") and "pension_savings" not in products and cash.liquidity_pressure == "low",
        "RT-07": (state.savings.balance or 0) > 10000,
        "RT-09": has_child,
        "EL-01": any(s.date == state.as_of for s in indexed.get("pension", [])),
        "EL-02": age >= 55,
        "EL-04": False,  # healthcare is deliberately suppressed from profile signals
        "EL-06": bool(cash.upcoming_outflows),
        "LE-02": any(d.signal == "expecting_baby" and d.created_at <= state.as_of for d in prefs.declared),
        "LE-06": False,  # no personal price-index comparison source
        "LE-12": state.as_of.month in (12, 1) and len(state.cash_flow.monthly) >= 3,
    }
    if code in conditions:
        return bool(conditions[code])
    # Evergreen education and self-service guidance can be shown from a persona match.
    return item["type"] == "Editorial"


def _catalogue_cards(customer: Customer, state: CustomerState, personas: list[dict], prefs: Prefs) -> list[Card]:
    out = []
    indexed: dict[str, list] = defaultdict(list)
    for signal in state.signals:
        if signal.profile_allowed and signal.currency == "EUR":
            indexed[signal.category].append(signal)
    for item in CATALOGUE:
        if not _eligible_catalogue(item, customer, state, personas, prefs, indexed):
            continue
        card_type = "catalog_" + item["id"].lower().replace("-", "_")
        family = {"Action": "deadline", "Insight": "forecast", "Product": "opportunity",
                  "Editorial": "milestone", "Tool": "opportunity"}[item["type"]]
        body, metrics, stage, observed = _personal_copy(item["id"], state)
        title = "Scam safety reminder" if item["id"] == "EL-02" else item["title"]
        matched = max((p for p in personas if p["code"] in item["fits"]), key=lambda p: p["weight"])
        card = _card(card_type, title, body or item["summary"], family=family, stage=stage,
                         commercial=item["type"] == "Product", confidence=0.9 if observed else 0.7,
                         evidence=([f"Calculated from Customer State as of {state.as_of.isoformat()}"] if observed else [])
                                  + [f"This topic fits your {PERSONA_NAMES[matched['code']]} profile"],
                         details={"kind": item["type"].lower(), "catalogue_id": item["id"],
                                  "description": item["summary"], "metrics": metrics,
                                  "metric_unit": "months" if item["id"] == "SV-01" else "EUR",
                                  "related": ["catalog_" + r.lower().replace("-", "_") for r in item["related"]]
                                             + item["related_core"]})
        if item["id"] == "SV-01":
            card.details["planner"] = {"kind": "savings",
                                       "target": round(3 * state.expenses.average_monthly_expenses, 2),
                                       "current": max(0, state.financial_position.total_liquid_balance or 0),
                                       "monthly": 100}
        if item["id"] == "EL-02":
            card.card_key += f"-{state.as_of:%Y-%m}"
        out.append(card)
    return out


def _personal_copy(code: str, state: CustomerState) -> tuple[str | None, list[dict], str, bool]:
    """Use a measured value where the state supports one; never reuse example figures from the spec."""
    balance = state.financial_position.current_balance
    cash = state.cash_flow
    metrics: list[dict] = []
    body: str | None = None
    stage = "info"
    if code in ("YS-01", "YS-06") and balance is not None:
        due = state.income.next_expected_income_date
        if due and due > state.as_of:
            days = (due-state.as_of).days
            body = f"{fmt_eur(balance)} available for the next {days} days, about {fmt_eur(balance/days)} per day."
            metrics = [{"label": "Available", "value": balance}, {"label": "Per day", "value": round(balance/days, 2)}]
        else:
            body = f"{fmt_eur(balance)} available in your current account."
            metrics = [{"label": "Available", "value": balance}]
        if code == "YS-06" and cash.liquidity_pressure == "high":
            stage = "urgent"
    elif code == "EC-03":
        monthly = state.subscriptions.monthly_total
        body = f"{fmt_eur(monthly)} a month across {state.subscriptions.count} detected subscriptions."
        metrics = [{"label": "Monthly", "value": monthly}, {"label": "Estimated yearly", "value": round(monthly*12, 2)}]
    elif code == "FM-05":
        childcare = [p for p in state.recurring_payments.items if p.category == "childcare"]
        if childcare:
            monthly = sum(p.monthly_amount for p in childcare)
            body = f"About {fmt_eur(monthly)} a month in detected childcare payments."
            metrics = [{"label": "Monthly childcare", "value": round(monthly, 2)}]
    elif code == "BZ-01":
        income = state.income.estimated_monthly_income
        if income is not None:
            body = f"Observed monthly income averages {fmt_eur(income)}; it varies between months."
            metrics = [{"label": "Monthly average", "value": income}]
    elif code == "BZ-02":
        invoices = [s for s in _signals(state, "invoice_income") if s.date.year == state.as_of.year
                    and s.date.month == state.as_of.month and s.amount > 0]
        if invoices:
            amount = sum(s.amount for s in invoices)
            body = f"{fmt_eur(amount)} in invoice income this month. Review how much to reserve for taxes."
            metrics = [{"label": "Invoice income this month", "value": round(amount, 2)}]
    elif code == "EL-01":
        pension = _signals(state, "pension", days=0)
        if pension:
            amount = sum(s.amount for s in pension)
            body = f"Your pension of {fmt_eur(amount)} arrived today."
            metrics = [{"label": "Received today", "value": round(amount, 2)}]
    elif code == "EL-02":
        body = "If someone asks for your PIN or security codes, stop and contact your bank through the app or a trusted number."
    elif code == "EL-06":
        week = [f for f in cash.upcoming_outflows if 0 <= (f.date-state.as_of).days <= 7]
        if week:
            amount = sum(abs(f.amount) for f in week)
            body = f"{len(week)} expected bill{'s' if len(week) != 1 else ''} this week, about {fmt_eur(amount)} in total."
            metrics = [{"label": "Expected this week", "value": round(amount, 2)}]
    elif code == "SV-01" and cash.cash_buffer_months is not None:
        body = f"Your known cash buffer covers about {cash.cash_buffer_months:.1f} months of typical expenses."
        metrics = [{"label": "Known cash buffer", "value": round(cash.cash_buffer_months, 1)}]
    elif code == "LE-12":
        year = state.as_of.year - (1 if state.as_of.month == 1 else 0)
        spent = [s for s in state.signals if s.currency == "EUR" and s.kind == "expense" and s.date.year == year]
        if spent:
            amount = -sum(s.amount for s in spent)
            body = f"In {year}, {fmt_eur(amount)} went toward your recorded expenses."
            metrics = [{"label": f"{year} expenses", "value": round(amount, 2)}]
    return body, metrics, stage, bool(body) and code != "EL-02"


def recommend(customer: Customer, state: CustomerState, prefs: Prefs) -> tuple[Feed, list[dict]]:
    personas = infer_personas(customer, state, prefs)
    candidates = _core_cards(customer, state, personas) + _catalogue_cards(customer, state, personas, prefs)
    by_type = {card.card_type: card for card in candidates}
    for card in candidates:
        related_cards = []
        for card_type in card.details.get("related", []):
            other = by_type.get(card_type)
            if other:
                related_cards.append({"card_key": other.card_key, "card_type": card_type,
                                      "title": other.title, "body": other.body,
                                      "evidence": other.evidence,
                                      "details": {key: value for key, value in other.details.items()
                                                  if key in ("kind", "metrics", "metric_unit", "planner", "methodology")}})
        card.details["related_cards"] = related_cards
    feedback = [f for f in prefs.feedback if f.created_at <= state.as_of]
    profile = {p["code"]: p["weight"] for p in personas}
    selected = []
    for card in candidates:
        own = [f for f in feedback if f.card_key == card.card_key]
        if own and own[-1].decision in ("dismiss", "accept"):
            continue
        if own and own[-1].decision == "snooze" and (state.as_of-own[-1].created_at).days < SNOOZE_DAYS:
            continue
        if not customer.consent_personalization and card.commercial:
            continue
        fit = 1.0 if card.card_type.startswith("core_") else sum(
            p["weight"] for p in personas if p["code"] in CATALOGUE_BY_ID[card.details["catalogue_id"]]["fits"])
        fatigue = 0.35 if any(f.card_type == card.card_type and f.decision == "less" for f in feedback) else 1
        priority = 1.0 if card.card_type == "core_money" else 0.82 if card.card_type in ("core_spending", "core_coming_up") else 0.48
        if card.card_type == "core_goals" and sum(profile.get(p, 0) for p in ("TEEN", "STU", "YPRO")) >= 0.5:
            priority = 0.68
        elif card.card_type == "core_insurance" and sum(profile.get(p, 0) for p in ("PAR", "HOME", "SELF")) >= 0.5:
            priority = 0.62
        elif card.card_type == "core_cards" and profile.get("SEN", 0) >= 0.5:
            priority = 0.7
        score = round((priority if card.card_type.startswith("core_") else 0.22 + 0.38*fit) * fatigue, 4)
        if card.stage == "urgent":
            score += 1.2
        elif card.stage == "soon":
            score += 0.12
        selected.append(card.model_copy(update={"score": score,
                                         "rank_explanation": " · ".join(card.evidence[:2])}))
    selected.sort(key=lambda c: (-c.score, c.card_key))
    shown: list[Card] = []
    commercial = 0
    core_count = 0
    for card in selected:
        if len(shown) >= MAX_CARDS:
            break
        if card.card_type.startswith("core_") and core_count >= MAX_CORE_CARDS:
            continue
        if card.commercial and (commercial >= MAX_COMMERCIAL or commercial + 1 > (len(shown) + 3) // 3):
            continue
        shown.append(card)
        commercial += card.commercial
        core_count += card.card_type.startswith("core_")
    return Feed(cards=shown, caught_up=True, hidden_count=len(selected)-len(shown)), personas
