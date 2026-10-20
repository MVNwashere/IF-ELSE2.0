"""Card generators. Each proposes cards; none of them rank.

Every card carries plain-English evidence. Comparison cards list coverage differences honestly and
never claim the competitor's policy terms. KBC prices are illustrative placeholders.
"""
from __future__ import annotations

import datetime as dt
import re
import statistics
from collections import defaultdict

from ..schemas import Card, Cta, Customer, Features, Stage, Transaction
from .features import fmt_date, fmt_eur

# ---- tuning knobs -----------------------------------------------------------------
from .features import FIXED_PRICE_CATEGORIES, VAT_DUE_DAY  # noqa: E402  (20th of the month after quarter end)
VAT_RESERVE_RATE = 0.21
SOON_DAYS = 14
URGENT_DAYS = 3
RUNWAY_MAX_DAYS = 21
SQUEEZE_MIN_CHANGE = 0.5
DUPLICATE_WINDOW_HOURS = 48
DUPLICATE_LOOKBACK_DAYS = 14
PRICE_INCREASE_LOOKBACK_DAYS = 60
LIFE_EVENT_LOOKBACK_DAYS = 45
IDLE_CASH_MIN_EUR = 2000
IDLE_CASH_MONTHS_LOOKBACK = 4
INSURANCE_KBC_DISCOUNT = 0.27          # illustrative: "same coverage at KBC" ≈ 27 % cheaper
INSURANCE_WINDOW_DAYS = 45             # show the renewal card from 45 days before renewal
SCAM_MIN_AGE = 60                      # below this the card is noise, not protection
SCAM_CONFIDENCE_BASE = 0.5
SCAM_CONFIDENCE_SENIOR = 0.75
SCAM_SENIOR_AGE = 65
KBC_NAMES = ("kbc", "cbc")
# pension savings (pensioensparen): tax reduction season runs from September to the 31 Dec deposit deadline
PENSION_SEASON_START_MONTH = 9
PENSION_MIN_AGE, PENSION_MAX_AGE = 18, 64
PENSION_MAX_DEPOSIT_EUR = 1050         # yearly ceiling for the 30 % tax reduction (confirm the year's figure)
PENSION_TAX_RATE = 0.30
PENSION_NAMES = ("pensioen", "pension")
# late client: a steady payer who is clearly later than usual, and later than ever before
LATE_CLIENT_MIN_PAYMENTS = 4
LATE_CLIENT_GAP_MULTIPLE = 1.5         # late = more than 1.5x the median gap ...
LATE_CLIENT_STEADY_SPREAD = 1.5        # ... and only for steady payers: 80th-percentile gap <= 1.5x the median
LATE_CLIENT_MIN_DAYS = 45
LATE_CLIENT_MAX_DAYS = 365             # silent for longer than a year = a former client, not a late one
# protection gap: child signals but no family liability insurance
PROTECTION_CHILD_LOOKBACK_DAYS = 365
PROTECTION_INSURANCE_LOOKBACK_DAYS = 395   # 13 months: a yearly premium may shift by a few weeks
PROTECTION_CHILD_CATEGORIES = frozenset({"child_benefit", "childcare", "baby"})
# new payee: a first, large payment to someone never paid before
NEW_PAYEE_MIN_EUR = 500
NEW_PAYEE_LOOKBACK_DAYS = 7
NEW_PAYEE_URGENT_DAYS = 2
NEW_PAYEE_MIN_HISTORY_DAYS = 90        # without history every payee looks new
NEW_PAYEE_MAX_CARDS = 2
NEW_PAYEE_EXPECTED = frozenset({       # large first payments that are normal life admin, not a scam signal
    "mortgage", "notary", "furniture", "tax", "vat_payment", "social_contribution", "savings_transfer",
    "rent", "tuition", "childcare",
})
NAME_MAX = 40


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:40] or "x"


def _name(s: str) -> str:
    """Counterparty names come from transaction data (attacker-controllable): strip control characters,
    collapse whitespace and cap the length before putting them in customer-facing text."""
    s = "".join(ch if ch.isprintable() else " " for ch in s)
    s = re.sub(r"\s+", " ", s).strip()
    return (s[:NAME_MAX - 1].rstrip() + "…") if len(s) > NAME_MAX else (s or "an unknown payee")


def stage_for(due_date: dt.date | None, as_of: dt.date) -> Stage | None:
    """Lifecycle stage; None means expired (don't show)."""
    if due_date is None:
        return "info"
    days = (due_date - as_of).days
    if days < 0:
        return None
    if days <= URGENT_DAYS:
        return "urgent"
    if days <= SOON_DAYS:
        return "soon"
    return "early"


def _days_phrase(due: dt.date, as_of: dt.date) -> str:
    d = (due - as_of).days
    return "today" if d == 0 else ("tomorrow" if d == 1 else f"in {d} days")


def _past(txs: list[Transaction], as_of: dt.date, days: int | None = None) -> list[Transaction]:
    lo = as_of - dt.timedelta(days=days) if days else None
    return [t for t in txs if t.date <= as_of and (lo is None or t.date > lo)]


# ---- generators -------------------------------------------------------------------


def gen_insurance_renewal(f: Features, c: Customer, txs: list[Transaction], as_of: dt.date) -> list[Card]:
    if "car_insurance" in c.products:
        return []
    out = []
    for r in f.recurring_payments:
        if r.category != "insurance_car" or r.period_days != 365:
            continue
        if any(k in r.counterparty.lower() for k in KBC_NAMES):
            continue
        due = r.next_date
        if (due - as_of).days > INSURANCE_WINDOW_DAYS:
            continue
        stage = stage_for(due, as_of)
        if stage is None:
            continue
        kbc_yearly = round(r.amount_eur * (1 - INSURANCE_KBC_DISCOUNT))
        saving = round(r.amount_eur - kbc_yearly)
        out.append(Card(
            card_key=f"insurance_renewal:{_slug(r.counterparty)}-car",
            card_type="insurance_renewal", family="deadline", stage=stage,
            title=f"Your car insurance renews {_days_phrase(due, as_of)}",
            body=(f"You paid {fmt_eur(r.amount_eur)} to {r.counterparty} last year. Comparable coverage at KBC is "
                  f"estimated at about {fmt_eur(saving / 12)}/month less (illustrative). Here's what differs, "
                  f"compared to what you pay now."),
            eur_impact=saving, due_date=due, confidence=0.85, commercial=True,
            evidence=[f"Yearly payment of {fmt_eur(r.amount_eur)} to {r.counterparty} on {fmt_date(r.last_date)}",
                      f"Renewal expected on {fmt_date(due)} (one year after the last payment)",
                      "No car insurance with KBC"],
            cta=Cta(label="Compare coverage", action="open_compare"),
            details={"comparison": [
                {"item": "Yearly premium", "current": fmt_eur(r.amount_eur), "kbc": f"{fmt_eur(kbc_yearly)} (illustrative)"},
                {"item": "Civil liability (mandatory)", "current": "included", "kbc": "included"},
                {"item": "Legal assistance", "current": "check your policy", "kbc": "included"},
                {"item": "Roadside assistance abroad", "current": "check your policy", "kbc": "optional, +€48/yr"},
                {"item": "Own damage (omnium)", "current": "check your policy", "kbc": "optional"},
            ], "note": "We only know what you pay, not your current policy's terms. Check them before switching."},
        ))
    return out


def gen_vat_reserve(f: Features, c: Customer, txs: list[Transaction], as_of: dt.date) -> list[Card]:
    if f.vat_due_date is None or f.vat_period_invoice_income_eur <= 0:
        return []
    due = f.vat_due_date
    stage = stage_for(due, as_of)
    if stage is None:
        return []
    reserve = round(f.vat_period_invoice_income_eur * VAT_RESERVE_RATE)
    q_label = f.vat_period_label  # "Q3 2026"
    q_num, q_year = int(q_label[1]), int(q_label.split()[1])
    period_start = dt.date(q_year, (q_num - 1) * 3 + 1, 1)
    invoices = [t for t in _past(txs, as_of) if t.category == "invoice_income" and t.date >= period_start]
    last_vat = [t for t in _past(txs, as_of) if t.category == "vat_payment"]
    ev = [f"{len(invoices)} invoices received since {fmt_date(period_start)}"]
    if last_vat:
        lv = last_vat[-1]
        ev.append(f"Previous VAT payment {fmt_eur(lv.amount)} on {fmt_date(lv.date)}")
    return [Card(
        card_key=f"vat_reserve:{q_year}q{q_num}", card_type="vat_reserve", family="deadline", stage=stage,
        title=f"VAT return due {fmt_date(due)}",
        body=f"Based on {fmt_eur(f.vat_period_invoice_income_eur)} invoiced in {q_label}, set aside about {fmt_eur(reserve)}.",
        eur_impact=reserve, due_date=due, confidence=0.9, commercial=False, evidence=ev,
        cta=Cta(label="Set aside now", action="vat_transfer"),
        details={"quarter": q_label, "rate": VAT_RESERVE_RATE},
    )]


def gen_price_increase(f: Features, c: Customer, txs: list[Transaction], as_of: dt.date) -> list[Card]:
    out = []
    for r in f.recurring_payments:
        if r.previous_amount_eur is None or r.amount_eur <= r.previous_amount_eur:
            continue
        if r.category not in FIXED_PRICE_CATEGORIES:
            continue
        if (as_of - r.last_date).days > PRICE_INCREASE_LOOKBACK_DAYS:
            continue
        per_year = (r.amount_eur - r.previous_amount_eur) * (12 if r.period_days == 30 else 1)
        out.append(Card(
            card_key=f"price_increase:{_slug(r.counterparty)}", card_type="price_increase", family="anomaly",
            stage="info",
            title=f"{r.counterparty} went from {fmt_eur(r.previous_amount_eur)} to {fmt_eur(r.amount_eur)}",
            body=f"That's {fmt_eur(per_year)} more per year. Still worth it?",
            eur_impact=round(per_year, 2), due_date=None, confidence=0.95, commercial=False,
            evidence=[f"Payment to {r.counterparty} was {fmt_eur(r.previous_amount_eur)} before",
                      f"{fmt_eur(r.amount_eur)} charged on {fmt_date(r.last_date)}"],
            cta=Cta(label="Review subscriptions", action="open_subscriptions"),
        ))
    return out


def gen_duplicate_charge(f: Features, c: Customer, txs: list[Transaction], as_of: dt.date) -> list[Card]:
    recent = [t for t in _past(txs, as_of, DUPLICATE_LOOKBACK_DAYS) if t.amount < 0]
    groups: dict[tuple[str, float], list[Transaction]] = defaultdict(list)
    for t in recent:
        groups[(t.counterparty, round(t.amount, 2))].append(t)
    out = []
    for (cp, amt), items in groups.items():
        items.sort(key=lambda t: (t.date, t.id))
        for a, b in zip(items, items[1:]):
            if (b.date - a.date).days * 24 <= DUPLICATE_WINDOW_HOURS:
                out.append(Card(
                    card_key=f"duplicate_charge:{_slug(cp)}-{b.date.isoformat()}", card_type="duplicate_charge",
                    family="anomaly", stage="info",
                    title=f"Two identical charges of {fmt_eur(amt)} at {cp}",
                    body=(f"Both on {fmt_date(a.date)}" if a.date == b.date else
                          f"On {fmt_date(a.date)} and {fmt_date(b.date)}") + ". If you only bought once, we can help you get it back.",
                    eur_impact=abs(amt), due_date=None, confidence=0.8, commercial=False,
                    evidence=[f"{fmt_eur(amt)} to {cp} on {fmt_date(a.date)}", f"{fmt_eur(amt)} to {cp} on {fmt_date(b.date)}"],
                    cta=Cta(label="Dispute charge", action="dispute_charge"),
                ))
                break
    return out


def gen_runway(f: Features, c: Customer, txs: list[Transaction], as_of: dt.date) -> list[Card]:
    if f.runway_days is None or f.runway_days > RUNWAY_MAX_DAYS:
        return []
    zero_day = as_of + dt.timedelta(days=f.runway_days)
    due = zero_day
    stage = stage_for(due, as_of) or "urgent"
    if f.next_income_date and f.next_income_date <= zero_day:
        body = (f"At this pace you'd hit €0 on {fmt_date(zero_day)}, but your next income "
                f"({fmt_eur(f.next_income_eur or 0)}) is expected {fmt_date(f.next_income_date)}. Tight, but OK.")
        conf = 0.6
    else:
        body = f"At this pace you'll be at €0 on {fmt_date(zero_day)}. Let's look at what can wait."
        conf = 0.8
    # projected shortfall by the next income (or over 30 days if unknown), at the current daily burn
    daily_burn = f.balance_eur / f.runway_days if f.runway_days > 0 else 0.0
    horizon = (f.next_income_date - as_of).days if f.next_income_date else 30
    shortfall = max(0.0, daily_burn * max(horizon, 0) - f.balance_eur)
    return [Card(
        card_key=f"runway:{zero_day.isoformat()}", card_type="runway", family="forecast", stage=stage,
        title=f"{fmt_eur(f.balance_eur)} left, about {f.runway_days} days of runway",
        body=body, eur_impact=round(shortfall, 2), due_date=due, confidence=conf, commercial=False,
        evidence=[f"Balance {fmt_eur(f.balance_eur)} on {fmt_date(as_of)}",
                  f"Spending about {fmt_eur(f.monthly_spend_avg_90d)}/month vs income {fmt_eur(f.monthly_income_avg_90d)}/month"],
        cta=Cta(label="Plan the month", action="open_budget"),
    )]


def gen_cashflow_squeeze(f: Features, c: Customer, txs: list[Transaction], as_of: dt.date) -> list[Card]:
    if f.variable_spend_change_30d < SQUEEZE_MIN_CHANGE:
        return []
    pct = round(f.variable_spend_change_30d * 100)
    top = sorted(f.spend_by_category_30d.items(), key=lambda kv: -kv[1])[:2]
    top_txt = " and ".join(k.replace("_", " ") for k, _ in top) if top else "everyday spending"
    extra = sum(v for _, v in top)
    return [Card(
        card_key=f"cashflow_squeeze:{as_of.strftime('%Y-%m')}", card_type="cashflow_squeeze", family="forecast",
        stage="info",
        title=f"Spending is up {pct}% this month",
        body=f"Mostly {top_txt}. Want a quick plan to end the month comfortably?",
        eur_impact=round(extra, 2), due_date=None, confidence=0.7, commercial=False,
        evidence=[f"Variable spending in the last 30 days is {pct}% above your 3-month average"]
                 + [f"{fmt_eur(v)} on {k.replace('_', ' ')} this month" for k, v in top],
        cta=Cta(label="Talk to an advisor", action="call_advisor"),
    )]


def gen_idle_cash(f: Features, c: Customer, txs: list[Transaction], as_of: dt.date) -> list[Card]:
    if f.idle_cash_eur < IDLE_CASH_MIN_EUR:
        return []
    idle = round(f.idle_cash_eur / 100) * 100
    return [Card(
        card_key="idle_cash:savings", card_type="idle_cash", family="opportunity", stage="info",
        title=f"About {fmt_eur(idle)} has been sitting idle",
        body=f"That's more than {IDLE_CASH_MONTHS_LOOKBACK} months of spending on your current account. A savings account would earn interest without locking it up.",
        eur_impact=round(idle * 0.02), due_date=None, confidence=0.7, commercial=True,
        evidence=[f"Balance {fmt_eur(f.balance_eur)} vs about {fmt_eur(f.monthly_spend_avg_90d)}/month of spending",
                  "No savings account with KBC"],
        cta=Cta(label="See savings options", action="open_savings"),
        details={"estimated_interest_eur": round(idle * 0.02), "note": "2% p.a. illustrative"},
    )]


_LIFE_EVENT_COPY = {
    "first_salary": ("First salary! 🎉", "Welcome to payday. A 3-step starter plan: a buffer, a budget, and a first savings goal.",
                     "Start the 3-step plan", "open_starter_plan", "milestone"),
    "first_invoice": ("Your first invoice got paid", "Nice. As a freelancer, set aside about 21% for VAT and plan for social contributions.",
                      "Set up a tax reserve", "vat_transfer", "milestone"),
    "baby": ("Congratulations on the new arrival", "Groeipakket is coming in. Want a family budget and a child savings goal?",
             "Set up family budget", "open_family_budget", "milestone"),
    "pension_start": ("Your first pension has arrived", "A calmer rhythm. We can help you keep an eye on bills and stay safe from scams.",
                      "See my monthly overview", "open_pension_overview", "milestone"),
    "moved_house": ("New home, new bills", "Time to check home insurance and update recurring payments.",
                    "Review home setup", "open_home_checklist", "milestone"),
}


def gen_life_event(f: Features, c: Customer, txs: list[Transaction], as_of: dt.date) -> list[Card]:
    out = []
    for e in f.life_events:
        if 0 <= (as_of - e.date).days <= LIFE_EVENT_LOOKBACK_DAYS and e.type in _LIFE_EVENT_COPY:
            title, body, cta_label, action, _ = _LIFE_EVENT_COPY[e.type]
            out.append(Card(
                card_key=f"life_event:{e.type}-{e.date.isoformat()}", card_type="life_event", family="milestone",
                stage="info", title=title, body=body, eur_impact=0.0, due_date=None, confidence=0.85,
                commercial=False, evidence=[e.evidence], cta=Cta(label=cta_label, action=action),
            ))
    return out


def gen_scam_awareness(f: Features, c: Customer, txs: list[Transaction], as_of: dt.date) -> list[Card]:
    if f.age < SCAM_MIN_AGE:
        return []
    senior = f.age >= SCAM_SENIOR_AGE
    return [Card(
        card_key=f"scam_awareness:{as_of.strftime('%Y-%W')}", card_type="scam_awareness", family="protection",
        stage="info",
        title="Scam SMS wave this week",
        body="KBC never asks for your card code, PIN or a payment 'to verify'. When in doubt, hang up and call us.",
        eur_impact=0.0, due_date=None, confidence=SCAM_CONFIDENCE_SENIOR if senior else SCAM_CONFIDENCE_BASE,
        commercial=False,
        evidence=["Phishing reports are up this week (synthetic)"] + (["Customers over 65 are targeted most often"] if senior else []),
        cta=Cta(label="How to spot a scam", action="open_scam_tips"),
    )]


def gen_pension_savings(f: Features, c: Customer, txs: list[Transaction], as_of: dt.date) -> list[Card]:
    if as_of.month < PENSION_SEASON_START_MONTH or "pension_savings" in c.products:
        return []
    if not (PENSION_MIN_AGE <= f.age <= PENSION_MAX_AGE) or not (f.has_salary or f.has_invoice_income):
        return []
    if f.balance_eur < PENSION_MAX_DEPOSIT_EUR or (f.runway_days is not None and f.runway_days <= RUNWAY_MAX_DAYS):
        return []   # don't push a deposit on someone without room for it
    year_start = dt.date(as_of.year, 1, 1)
    if any(t.category == "savings_transfer" and t.amount < 0 and t.date >= year_start
           and any(k in t.counterparty.lower() for k in PENSION_NAMES) for t in _past(txs, as_of)):
        return []
    due = dt.date(as_of.year, 12, 31)
    stage = stage_for(due, as_of)
    if stage is None:
        return []
    benefit = round(PENSION_MAX_DEPOSIT_EUR * PENSION_TAX_RATE)
    income = "a salary" if f.has_salary else "invoice income"
    return [Card(
        card_key=f"pension_savings:{as_of.year}", card_type="pension_savings", family="opportunity", stage=stage,
        title=f"Pension savings: up to {fmt_eur(benefit)} back in tax for {as_of.year}",
        body=(f"Deposits into a pension savings plan before {fmt_date(due)} give a tax reduction of up to "
              f"{round(PENSION_TAX_RATE * 100)}% on up to {fmt_eur(PENSION_MAX_DEPOSIT_EUR)} a year. "
              "What you actually get back depends on your tax situation."),
        eur_impact=benefit, due_date=due, confidence=0.5, commercial=True,
        evidence=[f"You have {income}, so you likely pay Belgian income tax",
                  f"No pension savings deposit seen in {as_of.year}",
                  f"Deposits count for {as_of.year} until {fmt_date(due)}"],
        cta=Cta(label="See how it works", action="open_pension_savings"),
        details={"max_deposit_eur": PENSION_MAX_DEPOSIT_EUR, "tax_rate": PENSION_TAX_RATE,
                 "note": "Up to amounts; the actual tax reduction depends on your situation."},
    )]


def gen_late_client(f: Features, c: Customer, txs: list[Transaction], as_of: dt.date) -> list[Card]:
    by_payer: dict[str, list[Transaction]] = defaultdict(list)
    for t in _past(txs, as_of):
        if t.category == "invoice_income" and t.amount > 0:
            by_payer[t.counterparty].append(t)
    best = None
    for cp, items in by_payer.items():
        if len(items) < LATE_CLIENT_MIN_PAYMENTS:
            continue
        items.sort(key=lambda t: (t.date, t.id))
        gaps = sorted(g for g in ((b.date - a.date).days for a, b in zip(items, items[1:])) if g > 0)
        if len(gaps) < LATE_CLIENT_MIN_PAYMENTS - 1:
            continue
        med_gap = round(statistics.median(gaps))
        p80 = gaps[min(len(gaps) - 1, int(len(gaps) * 0.8))]
        if p80 > LATE_CLIENT_STEADY_SPREAD * max(med_gap, 1):
            continue   # irregular payer: "late" would be noise
        since = (as_of - items[-1].date).days
        if since > LATE_CLIENT_MAX_DAYS or since <= max(med_gap * LATE_CLIENT_GAP_MULTIPLE, LATE_CLIENT_MIN_DAYS, gaps[-1]):
            continue
        ratio = since / max(med_gap, 1)
        if best is None or ratio > best[0]:
            best = (ratio, cp, items, med_gap, since)
    if best is None:
        return []
    _, cp, items, med_gap, since = best
    name, last = _name(cp), items[-1]
    typical = round(statistics.median(t.amount for t in items), 2)
    return [Card(
        card_key=f"late_client:{_slug(cp)}-{last.date.isoformat()}", card_type="late_client", family="anomaly",
        stage="info",
        title=f"{name} usually pays every ~{med_gap} days; last payment was {since} days ago",
        body=f"A typical payment from {name} is about {fmt_eur(typical)}. If an invoice is still open, a friendly reminder may help.",
        eur_impact=typical, due_date=None, confidence=0.65, commercial=False,
        evidence=[f"{len(items)} payments from {name} so far, typically every {med_gap} days",
                  f"Last payment {fmt_eur(last.amount)} on {fmt_date(last.date)}, the longest wait so far",
                  "We only see payments, not your open invoices"],
        cta=Cta(label="Send a reminder", action="invoice_reminder"),
        details={"median_gap_days": med_gap, "days_since_last": since},
    )]


def gen_protection_gap(f: Features, c: Customer, txs: list[Transaction], as_of: dt.date) -> list[Card]:
    if "family_insurance" in c.products:
        return []
    past = _past(txs, as_of)
    child_lo = as_of - dt.timedelta(days=PROTECTION_CHILD_LOOKBACK_DAYS)
    ins_lo = as_of - dt.timedelta(days=PROTECTION_INSURANCE_LOOKBACK_DAYS)
    child = [t for t in past if t.category in PROTECTION_CHILD_CATEGORIES and t.date > child_lo]
    if not child or any(t.category == "insurance_family" and t.date > ins_lo for t in past):
        return []
    seen = sorted({t.category.replace("_", " ") for t in child})
    return [Card(
        card_key=f"protection_gap:family-{as_of.year}", card_type="protection_gap", family="protection",
        stage="info",
        title="Your family grew. Did your insurance?",
        body=("We don't see a family liability insurance in your payments. It's worth checking you're covered; "
              "you may already be, for example through a partner's policy."),
        eur_impact=0.0, due_date=None, confidence=0.6, commercial=True,
        evidence=[f"Payments for {', '.join(seen)} in the last 12 months",
                  "No family insurance payment in the last 13 months"],
        cta=Cta(label="Check my cover", action="open_family_insurance"),
        details={"typically_covers": [
            "Damage your children accidentally cause to others (e.g. a broken window, a bike accident)",
            "Damage you or your partner accidentally cause to others in private life",
            "Legal help after such an incident (depends on the policy)",
        ], "note": "Cover and prices differ per policy; we don't quote a price here."},
    )]


def gen_new_payee(f: Features, c: Customer, txs: list[Transaction], as_of: dt.date) -> list[Card]:
    past = sorted(_past(txs, as_of), key=lambda t: (t.date, t.id))
    if not past or (as_of - past[0].date).days < NEW_PAYEE_MIN_HISTORY_DAYS:
        return []
    lo = as_of - dt.timedelta(days=NEW_PAYEE_LOOKBACK_DAYS)
    seen: set[str] = set()
    out: list[Card] = []
    for t in past:
        key = t.counterparty.strip().lower()
        first = key not in seen
        seen.add(key)
        if not first or t.date <= lo or t.amount > -NEW_PAYEE_MIN_EUR or t.category in NEW_PAYEE_EXPECTED:
            continue
        if any(k in key for k in KBC_NAMES) or (t.date - past[0].date).days < NEW_PAYEE_MIN_HISTORY_DAYS:
            continue
        name = _name(t.counterparty)
        ago = (as_of - t.date).days
        out.append(Card(
            card_key=f"new_payee:{_slug(t.counterparty)}-{t.date.isoformat()}", card_type="new_payee",
            family="protection", stage="urgent" if ago <= NEW_PAYEE_URGENT_DAYS else "soon",
            title=f"First payment of {fmt_eur(t.amount)} to {name}. Was this you?",
            body=("You've never paid this recipient before. If you didn't make this payment, or someone "
                  "pressured you to pay quickly, call us straight away."),
            eur_impact=abs(t.amount), due_date=None, confidence=0.7, commercial=False,
            evidence=[f"{fmt_eur(t.amount)} to {name} on {fmt_date(t.date)}",
                      "No earlier payments to or from this recipient in your history",
                      "Scammers often push for one large, urgent payment to a new account"],
            cta=Cta(label="Yes, that was me", action="confirm_payee"),
        ))
    out.sort(key=lambda k: -k.eur_impact)
    return out[:NEW_PAYEE_MAX_CARDS]


GENERATORS = [
    gen_insurance_renewal, gen_vat_reserve, gen_price_increase, gen_duplicate_charge,
    gen_runway, gen_cashflow_squeeze, gen_idle_cash, gen_life_event, gen_scam_awareness,
    gen_pension_savings, gen_late_client, gen_protection_gap, gen_new_payee,
]


def generate_cards(features: Features, customer: Customer, txs: list[Transaction], as_of: dt.date) -> list[Card]:
    cards: list[Card] = []
    seen: set[str] = set()
    for g in GENERATORS:
        for card in g(features, customer, txs, as_of):
            if card.card_key in seen:
                continue
            seen.add(card.card_key)
            cards.append(card)
    return cards
