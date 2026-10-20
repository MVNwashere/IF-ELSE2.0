"""Scoring, hard constraints, lifecycle, fatigue → an ordered Feed.

score = persona_fit × (0.40·urgency + 0.30·impact + 0.20·confidence + 0.10·novelty) × fatigue
"""
from __future__ import annotations

import datetime as dt
import math

from ..schemas import PERSONAS, Card, Customer, Feed, Persona, PersonaWeight, Prefs
from .features import fmt_eur

# ---- tuning knobs -----------------------------------------------------------------
W_URGENCY, W_IMPACT, W_CONFIDENCE, W_NOVELTY = 0.40, 0.30, 0.20, 0.10
URGENCY = {"urgent": 1.0, "soon": 0.7, "early": 0.4, "info": 0.3}
IMPACT_LOG_SCALE = 3.5
NOVELTY_NEW, NOVELTY_SEEN = 1.0, 0.5
FATIGUE_LESS, FATIGUE_DISMISS = 0.3, 0.8
FATIGUE_RECOVERY_DAYS = 30
SNOOZE_DAYS = 7
MAX_CARDS = 7
MAX_PER_FAMILY = 2
COMMERCIAL_EVERY = 3            # at most 1 commercial card per 3 cards shown

# affinity[card_type][persona] in 0..1
AFFINITY: dict[str, dict[Persona, float]] = {
    "insurance_renewal": {"student": 0.6, "young_professional": 0.9, "young_family": 0.9, "freelancer": 0.9, "retiree": 0.8},
    "vat_reserve":       {"student": 0.1, "young_professional": 0.1, "young_family": 0.2, "freelancer": 1.0, "retiree": 0.1},
    "price_increase":    {"student": 0.9, "young_professional": 0.8, "young_family": 0.8, "freelancer": 0.7, "retiree": 0.8},
    "duplicate_charge":  {"student": 0.9, "young_professional": 0.9, "young_family": 0.9, "freelancer": 0.9, "retiree": 1.0},
    "runway":            {"student": 1.0, "young_professional": 0.7, "young_family": 0.8, "freelancer": 0.8, "retiree": 0.6},
    "cashflow_squeeze":  {"student": 0.9, "young_professional": 0.8, "young_family": 0.9, "freelancer": 0.8, "retiree": 0.7},
    "idle_cash":         {"student": 0.2, "young_professional": 0.8, "young_family": 0.7, "freelancer": 0.7, "retiree": 0.9},
    "life_event":        {"student": 0.9, "young_professional": 0.9, "young_family": 0.9, "freelancer": 0.9, "retiree": 0.9},
    "scam_awareness":    {"student": 0.2, "young_professional": 0.2, "young_family": 0.3, "freelancer": 0.3, "retiree": 1.0},
    "pension_savings":   {"student": 0.1, "young_professional": 0.6, "young_family": 0.5, "freelancer": 0.6, "retiree": 0.1},
    "late_client":       {"student": 0.1, "young_professional": 0.2, "young_family": 0.3, "freelancer": 1.0, "retiree": 0.2},
    "protection_gap":    {"student": 0.2, "young_professional": 0.4, "young_family": 0.9, "freelancer": 0.5, "retiree": 0.3},
    "new_payee":         {"student": 0.7, "young_professional": 0.7, "young_family": 0.7, "freelancer": 0.7, "retiree": 1.0},
}


def persona_fit(card: Card, mix: list[PersonaWeight]) -> float:
    aff = AFFINITY.get(card.card_type, {})
    return sum(pw.weight * aff.get(pw.persona, 0.5) for pw in mix) if mix else 0.5


def impact_score(eur: float) -> float:
    return min(1.0, math.log10(1 + abs(eur)) / IMPACT_LOG_SCALE)


def novelty_score(card: Card, prefs: Prefs) -> float:
    """We don't store card creation dates, so: new if there was no previous visit, or if the card's
    due date lies after the last visit (a deadline that surfaced since). Info cards after a visit = seen."""
    if prefs.last_visit is None:
        return NOVELTY_NEW
    if card.due_date and card.due_date > prefs.last_visit:
        return NOVELTY_NEW
    return NOVELTY_SEEN


def fatigue_factor(card: Card, prefs: Prefs, as_of: dt.date) -> float:
    f = 1.0
    for fb in prefs.feedback:
        if fb.card_type != card.card_type or fb.created_at > as_of:
            continue
        if (as_of - fb.created_at).days > FATIGUE_RECOVERY_DAYS:
            continue
        if fb.decision == "less":
            f *= FATIGUE_LESS
        elif fb.decision == "dismiss":
            f *= FATIGUE_DISMISS
    return f


def score_card(card: Card, mix: list[PersonaWeight], prefs: Prefs, as_of: dt.date) -> float:
    base = (W_URGENCY * URGENCY[card.stage] + W_IMPACT * impact_score(card.eur_impact)
            + W_CONFIDENCE * card.confidence + W_NOVELTY * novelty_score(card, prefs))
    return round(persona_fit(card, mix) * base * fatigue_factor(card, prefs, as_of), 4)


def _fit_phrase(card: Card, mix: list[PersonaWeight]) -> str:
    aff = AFFINITY.get(card.card_type, {})
    if all(aff.get(p, 0) >= 0.6 for p in PERSONAS):
        return "fits every persona"
    best = max(mix, key=lambda pw: pw.weight * aff.get(pw.persona, 0)) if mix else None
    return f"fits {best.persona.replace('_', ' ')}" if best else "general"


def _impact_phrase(card: Card) -> str:
    if card.eur_impact <= 0:
        return "no direct € impact"
    per = "/yr" if card.card_type in ("insurance_renewal", "price_increase", "idle_cash") else ""
    return f"{fmt_eur(round(card.eur_impact))}{per} impact"


def _hidden_by_feedback(card: Card, prefs: Prefs, as_of: dt.date) -> bool:
    for fb in prefs.feedback:
        if fb.card_key != card.card_key or fb.created_at > as_of:
            continue
        if fb.decision in ("dismiss", "accept"):
            return True
        if fb.decision == "snooze" and (as_of - fb.created_at).days < SNOOZE_DAYS:
            return True
    return False


def rank(cards: list[Card], persona_mix: list[PersonaWeight], prefs: Prefs, customer: Customer,
         as_of: dt.date) -> Feed:
    # 1. consent gates commercial cards; 2. feedback hides specific card keys
    eligible = [c for c in cards
                if (customer.consent_personalization or not c.commercial)
                and not _hidden_by_feedback(c, prefs, as_of)]
    scored: list[Card] = []
    for c in eligible:
        s = score_card(c, persona_mix, prefs, as_of)
        scored.append(c.model_copy(update={
            "score": s,
            "rank_explanation": f"{c.stage} · {_impact_phrase(c)} · {_fit_phrase(c, persona_mix)}",
        }))
    # 3. urgent service cards first, then by score
    scored.sort(key=lambda c: (0 if (c.stage == "urgent" and not c.commercial) else 1, -c.score, c.card_key))

    # 4–6. commercial ratio, family cap, max cards
    shown: list[Card] = []
    family_count: dict[str, int] = {}
    deferred_commercial: list[Card] = []
    pool = list(scored)
    while pool and len(shown) < MAX_CARDS:
        c = pool.pop(0)
        if family_count.get(c.family, 0) >= MAX_PER_FAMILY:
            continue
        if c.commercial:
            commercial_shown = sum(1 for s in shown if s.commercial)
            # allowed if, after adding, commercial ≤ ceil((n)/3) i.e. at most 1 per 3 slots
            if commercial_shown + 1 > math.ceil((len(shown) + 1) / COMMERCIAL_EVERY):
                deferred_commercial.append(c)
                continue
        shown.append(c)
        family_count[c.family] = family_count.get(c.family, 0) + 1
        # a deferred commercial card may now fit
        if deferred_commercial and not c.commercial:
            pool.insert(0, deferred_commercial.pop(0))
    hidden = len(eligible) - len(shown)
    return Feed(cards=shown, caught_up=True, hidden_count=max(0, hidden))
