from __future__ import annotations

import datetime as dt

from app.engine.ranker import MAX_CARDS, MAX_PER_FAMILY, rank, score_card
from app.schemas import Card, FeedbackRow, PersonaWeight, Prefs

from tests.test_features import customer

D = dt.date
AS_OF = D(2026, 9, 30)
MIX = [PersonaWeight(persona="freelancer", weight=0.6, evidence=[]),
       PersonaWeight(persona="young_family", weight=0.4, evidence=[])]


def card(key, ctype="price_increase", family="anomaly", stage="info", eur=50, commercial=False, due=None, conf=0.9):
    return Card(card_key=key, card_type=ctype, family=family, stage=stage, title=key, body="", eur_impact=eur,
                due_date=due, confidence=conf, commercial=commercial)


def test_score_formula_and_explanation():
    c = card("vat_reserve:2026q3", "vat_reserve", "deadline", "early", 1840, due=D(2026, 10, 20))
    s = score_card(c, MIX, Prefs(), AS_OF)
    assert 0 < s <= 1
    feed = rank([c], MIX, Prefs(), customer(), AS_OF)
    assert feed.cards[0].score == s
    assert feed.cards[0].rank_explanation == "early · €1.840 impact · fits freelancer"


def test_commercial_gated_by_consent():
    cards = [card("insurance_renewal:x", "insurance_renewal", "deadline", "soon", 168, commercial=True, due=D(2026, 10, 12)),
             card("price_increase:netflix")]
    ok = rank(cards, MIX, Prefs(), customer(consent_personalization=True), AS_OF)
    assert {c.card_key for c in ok.cards} == {"insurance_renewal:x", "price_increase:netflix"}
    no = rank(cards, MIX, Prefs(), customer(consent_personalization=False), AS_OF)
    assert [c.card_key for c in no.cards] == ["price_increase:netflix"]
    assert no.hidden_count == 0  # ineligible cards are not "hidden", they don't exist for this customer


def test_urgent_service_first_and_max_cards():
    cards = [card(f"price_increase:c{i}", eur=1000 * (i + 1)) for i in range(4)]
    cards += [card(f"life_event:e{i}", "life_event", "milestone", eur=0) for i in range(3)]
    cards += [card(f"idle_cash:{i}", "idle_cash", "opportunity", eur=5000, commercial=True) for i in range(2)]
    cards += [card("runway:zero", "runway", "forecast", "urgent", 10, due=AS_OF + dt.timedelta(days=2), conf=0.3)]
    cards += [card("scam_awareness:w", "scam_awareness", "protection", eur=0, conf=0.3)]
    feed = rank(cards, MIX, Prefs(), customer(), AS_OF)
    assert feed.cards[0].card_key == "runway:zero"           # urgent service card first despite low score
    assert len(feed.cards) <= MAX_CARDS
    assert feed.caught_up and feed.hidden_count == len(cards) - len(feed.cards)
    fam = {}
    for c in feed.cards:
        fam[c.family] = fam.get(c.family, 0) + 1
    assert max(fam.values()) <= MAX_PER_FAMILY
    # at most 1 commercial per 3 cards shown
    for n in range(1, len(feed.cards) + 1):
        assert sum(1 for c in feed.cards[:n] if c.commercial) <= -(-n // 3)


def test_snooze_dismiss_accept():
    cards = [card("price_increase:a"), card("price_increase:b")]
    fb = lambda key, dec, days_ago: FeedbackRow(card_key=key, card_type="price_increase", decision=dec,
                                                created_at=AS_OF - dt.timedelta(days=days_ago))
    feed = rank(cards, MIX, Prefs(feedback=[fb("price_increase:a", "snooze", 2)]), customer(), AS_OF)
    assert [c.card_key for c in feed.cards] == ["price_increase:b"]
    feed = rank(cards, MIX, Prefs(feedback=[fb("price_increase:a", "snooze", 8)]), customer(), AS_OF)
    assert len(feed.cards) == 2  # snooze expired after 7 days
    for dec in ("dismiss", "accept"):
        feed = rank(cards, MIX, Prefs(feedback=[fb("price_increase:a", dec, 100)]), customer(), AS_OF)
        assert [c.card_key for c in feed.cards] == ["price_increase:b"]  # permanent


def test_fatigue_less_like_this_reranks_and_recovers():
    a = card("price_increase:a", eur=50)
    b = card("duplicate_charge:b", "duplicate_charge", "anomaly", eur=50)
    base = rank([a, b], MIX, Prefs(), customer(), AS_OF)
    less = FeedbackRow(card_key="price_increase:old", card_type="price_increase", decision="less",
                       created_at=AS_OF - dt.timedelta(days=3))
    after = rank([a, b], MIX, Prefs(feedback=[less]), customer(), AS_OF)
    sa = next(c for c in after.cards if c.card_key == "price_increase:a").score
    sb = next(c for c in base.cards if c.card_key == "price_increase:a").score
    assert abs(sa - sb * 0.3) < 1e-3
    assert after.cards[0].card_key == "duplicate_charge:b"
    old = less.model_copy(update={"created_at": AS_OF - dt.timedelta(days=40)})
    recovered = rank([a, b], MIX, Prefs(feedback=[old]), customer(), AS_OF)
    assert next(c for c in recovered.cards if c.card_key == "price_increase:a").score == sb


def test_novelty_uses_last_visit():
    c = card("vat_reserve:q", "vat_reserve", "deadline", "early", 100, due=D(2026, 10, 20))
    fresh = score_card(c, MIX, Prefs(last_visit=None), AS_OF)
    seen = score_card(card("price_increase:x"), MIX, Prefs(last_visit=AS_OF), AS_OF)
    fresh2 = score_card(card("price_increase:x"), MIX, Prefs(last_visit=None), AS_OF)
    assert fresh > 0 and seen < fresh2


def test_affinity_covers_every_card_type_and_new_payee_leads_for_retirees():
    from app.engine.ranker import AFFINITY
    from app.schemas import CARD_TYPES, PERSONAS
    assert set(AFFINITY) == set(CARD_TYPES)
    assert all(0 <= AFFINITY[t][p] <= 1 for t in CARD_TYPES for p in PERSONAS)
    retiree = [PersonaWeight(persona="retiree", weight=1.0, evidence=[])]
    cards = [card("duplicate_charge:colruyt", "duplicate_charge", eur=64),
             card("idle_cash:savings", "idle_cash", "opportunity", eur=100, commercial=True),
             card("scam_awareness:w", "scam_awareness", "protection", eur=0, conf=0.75),
             card("new_payee:tech-support", "new_payee", "protection", "urgent", eur=1250, conf=0.7),
             card("pension_savings:2026", "pension_savings", "opportunity", "early", eur=315, commercial=True,
                  due=D(2026, 12, 31), conf=0.5)]
    feed = rank(cards, retiree, Prefs(), customer(), AS_OF)
    keys = [c.card_key for c in feed.cards]
    assert keys[0] == "new_payee:tech-support"
    assert keys.index("idle_cash:savings") < keys.index("pension_savings:2026")   # low fit for retirees
    for n in range(1, len(feed.cards) + 1):
        assert sum(1 for c in feed.cards[:n] if c.commercial) <= -(-n // 3)
