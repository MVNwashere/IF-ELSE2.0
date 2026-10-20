"""build_home(customer, txs, balance_today, prefs, as_of) → HomeResponse.

The only place in the engine that may touch the wall clock (for `generated_at`), and only as a default.
"""
from __future__ import annotations

import datetime as dt

from ..schemas import (Customer, CustomerPublic, Features, HomeResponse, Milestone, Prefs, TimelineResponse,
                       Transaction)
from . import cards as cards_mod
from . import persona as persona_mod
from . import ranker
from .features import compute_features
from .layout import plan_home_layout


def customer_public(customer: Customer) -> CustomerPublic:
    return CustomerPublic(first_name=customer.first_name, language=customer.language,
                          consent_personalization=customer.consent_personalization)


def build_home(customer: Customer, txs: list[Transaction], balance_today: float, prefs: Prefs,
               as_of: dt.date, generated_at: dt.datetime | None = None) -> HomeResponse:
    return build_home_with_features(customer, txs, balance_today, prefs, as_of, generated_at)[0]


def build_home_with_features(customer: Customer, txs: list[Transaction], balance_today: float, prefs: Prefs,
                             as_of: dt.date, generated_at: dt.datetime | None = None) -> tuple[HomeResponse, Features]:
    """Kate needs the features behind the home screen to answer questions like "how am I doing"."""
    features = compute_features(customer, txs, balance_today, as_of)
    persona_mix = persona_mod.infer_persona_mix(features, prefs.declared)
    candidates = cards_mod.generate_cards(features, customer, txs, as_of)
    feed = ranker.rank(candidates, persona_mix, prefs, customer, as_of)
    plan = plan_home_layout(features, persona_mix, prefs, customer, txs, as_of, feed.cards)
    return HomeResponse(
        as_of=as_of,
        customer=customer_public(customer),
        persona_mix=persona_mix,
        layout=plan.layout,
        feed=feed,
        generated_at=generated_at or dt.datetime.now(dt.timezone.utc),
        llm_copy=False,
        style=prefs.style,
        suggestions=plan.suggestions,
        gallery=plan.gallery,
        declared=prefs.declared,
    ), features


_MILESTONE_LABELS = {
    "first_salary": "First salary",
    "first_invoice": "Went freelance",
    "baby": "Baby",
    "pension_start": "Pension",
    "moved_house": "Mortgage",
}


def build_timeline(customer: Customer, txs: list[Transaction], balance_today: float) -> TimelineResponse:
    if not txs:
        today = dt.date(1970, 1, 1)
        return TimelineResponse(min_date=today, max_date=today, milestones=[])
    dates = [t.date for t in txs]
    lo, hi = min(dates), max(dates)
    features = compute_features(customer, txs, balance_today, hi)
    milestones = [Milestone(date=e.date, label=_MILESTONE_LABELS.get(e.type, e.type.replace("_", " ").title()))
                  for e in features.life_events]
    milestones.sort(key=lambda m: m.date)
    return TimelineResponse(min_date=lo, max_date=hi, milestones=milestones)
