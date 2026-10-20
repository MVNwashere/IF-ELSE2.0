"""One home screen from three engines, with one number per fact.

The layout engine (engine/layout.py) picks the tiles and the moments that need action (engine/cards.py: a VAT
return due, a payment that may be a scam, a late client). The recommender (recommender/feed.py) adds the overview
cards from Customer State and the content catalogue. Shown side by side they used to disagree: two "upcoming bills"
lists from two detectors, a spending tile over the last 30 days next to a card for this calendar month, an invoice
tile with its own "unpaid" heuristic. This module merges them by explicit rules:

1. Moments first. Engine cards are what the customer can act on today; they lead the feed by urgency.
2. One source per fact. Upcoming payments, spending this month, the balance and the open-invoice estimate each come
   from one place; tiles that would repeat a card are dropped, hero tiles are filled from the same numbers.
3. No duplicates. Where two cards tell the same story (VAT due + the VAT tracker, a suspicious payment + the generic
   scam tip) the more specific one stays.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from ..customer_state.models import CustomerState
from ..engine.features import fmt_eur
from ..engine.layout import REGISTRY
from ..schemas import Card, HomeResponse
from .feed import balance_dip_card, category_name, coming_up_card, upcoming_items

MAX_HOME_CARDS = 8
STAGE_ORDER = {"urgent": 0, "soon": 1, "early": 2, "info": 2}   # "early" = months ahead: no reason to jump the queue
PENSION_BILLS_DAYS = 30
SEASONAL = {"pension_savings", "scam_awareness"}   # the same message for everyone this season


def _source_rank(card: Card) -> int:
    """Within a stage: what to act on (engine), then your own overview (core), then tips, offers and seasonal
    reminders (catalogue)."""
    if card.card_type.startswith("catalog_") or card.card_type in SEASONAL:
        return 2
    return 1 if card.card_type.startswith("core_") else 0


def _month_flows(state: CustomerState, kind: str) -> list:
    return [s for s in state.signals if s.currency == "EUR" and s.kind == kind
            and s.date.year == state.as_of.year and s.date.month == state.as_of.month and s.date <= state.as_of]


def compose_home(home: HomeResponse, engine_cards: list[Card], state: CustomerState, balance_eur: float) -> None:
    """Mutates `home`: feed = engine moments + recommender cards without duplicates; sections share their numbers.
    `balance_eur`: the current-account balance at `as_of` from the engine's features. It equals Customer State's on
    real dates and also covers the simulated future, which Customer State does not see."""
    rec = list(home.feed.cards)
    sections = home.layout.sections
    hero = next((s for s in sections if s.size == "hero"), None)
    comps = {s.component for s in sections}
    cards = [*engine_cards, *rec]
    types = {c.card_type for c in cards}
    drop: set[str] = set()

    # --- one number per fact -------------------------------------------------------------------------------------
    items = upcoming_items(state)
    lowest, low_date = state.cash_flow.lowest_projected_balance, state.cash_flow.lowest_projected_date
    if hero and hero.component == "TaxReserveHero":
        # The VAT the return asks for is the reserve on the tile; the expected payment to the tax office uses the same
        # figure, and the balance forecast moves with it.
        reserve = float(hero.props.get("reserve_eur") or 0)
        vat = next((i for i in items if i["category"] == "vat_payment"), None)
        if vat and reserve > 0:
            delta = round(reserve - vat["amount"], 2)
            vat["amount"] = round(reserve, 2)
            if lowest is not None and (low_date is None or low_date >= dt.date.fromisoformat(vat["date"])):
                lowest = round(lowest - delta, 2)
        hero.props["vat_payment"] = vat
        hero.props["action"] = {"label": "Set it aside now", "action": "vat_transfer"}
        drop |= {"vat_reserve", "catalog_bz_02"}
    rebuilt = {"core_coming_up": coming_up_card(state, items, lowest) if items else None,
               "core_unusual": balance_dip_card(state, lowest, low_date) if lowest is not None and lowest < 0 else None}

    def refresh(card: Card) -> Card:
        new = rebuilt.get(card.card_type)
        if new is None:
            return card
        new.details["related_cards"] = card.details.get("related_cards", [])
        return new.model_copy(update={"score": card.score, "rank_explanation": card.rank_explanation})

    cards = [refresh(c) for c in cards]

    if hero is not None:
        hero.props.setdefault("balance_eur", round(balance_eur, 2))
        if hero.component == "PensionHero":
            soon = [i for i in items if (dt.date.fromisoformat(i["date"]) - state.as_of).days <= PENSION_BILLS_DAYS]
            hero.props.update(upcoming_bills_eur=round(sum(i["amount"] for i in soon), 2),
                              upcoming_bills_count=len(soon), bills_horizon_days=PENSION_BILLS_DAYS)
        if hero.component == "FamilyBudgetHero" and _month_flows(state, "expense"):
            # only when Customer State has this month (not in the simulated future): then it matches the spending card
            spent: dict[str, float] = defaultdict(float)
            for s in _month_flows(state, "expense"):
                spent[s.category] += -s.amount
            top = sorted(spent.items(), key=lambda kv: kv[1], reverse=True)[:4]
            hero.props.update(month_spent_eur=round(sum(spent.values()), 2),
                              month_income_eur=round(sum(s.amount for s in _month_flows(state, "income")), 2),
                              top_categories=[{"category": k, "label": category_name(k), "eur": round(v, 2)} for k, v in top])

    # --- no duplicates ---------------------------------------------------------------------------------------------
    if "new_payee" in types:
        # a payment that may be a scam explains this month's spending jump and beats the generic safety tips
        drop |= {"scam_awareness", "catalog_el_02", "cashflow_squeeze"}
    elif "scam_awareness" in types:
        drop.add("catalog_el_02")
    if "vat_reserve" in types:
        drop.add("catalog_bz_02")
    if "core_unusual" in types and lowest is not None and lowest < 0:
        drop.add("runway")   # the same dip, said twice
    if state.financial_position.known_savings is None:
        drop.add("core_money")   # the KBC ball already shows the current account
    if "catalog_sv_01" in types or "SavingsGoal" in comps:
        drop.add("core_goals")   # a real buffer or savings plan beats the €1.000 example

    pruned = set()
    if "core_coming_up" in types:
        pruned.add("UpcomingBills")
    if "core_spending" in types:
        pruned.add("SpendingByCategory")
    savings = next((s for s in sections if s.component == "SavingsGoal"), None)
    if savings is not None and not savings.props.get("saved_eur") and "catalog_sv_01" in types:
        pruned.add("SavingsGoal")   # an empty plan next to the measured buffer card
    home.layout.sections = [s for s in sections if s.component not in pruned or s.size == "hero"]

    kept = [c for c in cards if c.card_type not in drop]
    seen: set[str] = set()
    unique = []
    for c in kept:
        if c.card_key not in seen:
            seen.add(c.card_key)
            unique.append(c)
    unique.sort(key=lambda c: (STAGE_ORDER.get(c.stage, 3), _source_rank(c), -c.score))
    shown = unique[:MAX_HOME_CARDS]
    for c in shown:
        c.details.setdefault("related_cards", [])   # engine cards have none; the detail sheet expects the list
    home.feed.cards = shown
    home.feed.hidden_count += len(unique) - len(shown)

    # tiles that talk about the feed follow the merged feed
    for s in home.layout.sections:
        if s.component == "AdvisorContact" and "new_payee" in types:
            payee = next(c for c in engine_cards if c.card_type == "new_payee")
            s.props["reason"] = f"Talk through the {fmt_eur(payee.eur_impact)} payment you may not recognise"
        if s.component == "KateTile":
            s.props.update(REGISTRY["KateTile"]["props"]({"cards": shown}))
