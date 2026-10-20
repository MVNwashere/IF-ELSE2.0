"""Customer State → nine-persona catalogue feed boundaries."""
import pytest

from app import db
from app.customer_state.service import get_state
from app.recommender.feed import CATALOGUE, _core_cards, infer_personas, recommend
from app.schemas import FeedbackRow, Prefs
from synth.customer_state import IDS, seed
from synth.generate import TODAY


@pytest.fixture
def scenario():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    seed(conn)

    def load(name="stable"):
        customer_id = IDS[name]
        return (db.get_customer(conn, customer_id),
                get_state(conn, customer_id, TODAY, balance_reference=TODAY))

    yield load
    conn.close()


def test_catalogue_has_all_defined_cards_and_related_links():
    assert len(CATALOGUE) == 100
    assert len({item["id"] for item in CATALOGUE}) == 100
    ids = {item["id"] for item in CATALOGUE}
    assert all(item["fits"] and set(item["related"]) <= ids for item in CATALOGUE)


def test_customer_state_drives_personas_and_feed(scenario):
    customer, state = scenario("variable")
    feed, personas = recommend(customer, state, Prefs())
    assert personas[0]["code"] == "SELF"
    assert abs(sum(p["weight"] for p in personas) - 1) < 0.001
    assert feed.cards[0].card_type == "core_money"
    assert any(card.card_type == "catalog_bz_02" for card in feed.cards)
    assert all(card.evidence and card.rank_explanation for card in feed.cards)


def test_minors_never_receive_adult_or_risky_content(scenario):
    customer, state = scenario()
    customer = customer.model_copy(update={"birth_year": 2010})
    feed, personas = recommend(customer, state, Prefs())
    assert [p["code"] for p in personas] == ["TEEN"]
    assert feed.cards
    assert all(c.card_type.startswith(("core_", "catalog_ys_")) for c in feed.cards)
    assert not any(c.card_type in ("core_investments", "core_debt", "core_insurance", "core_health") or c.commercial
                   for c in feed.cards)


def test_retiree_gets_plain_monthly_safety_reminder(scenario):
    customer, state = scenario()
    customer = customer.model_copy(update={"birth_year": 1948})
    feed, personas = recommend(customer, state, Prefs())
    assert personas[0]["code"] == "SEN"
    reminder = next(c for c in feed.cards if c.card_type == "catalog_el_02")
    assert reminder.card_key.endswith("2026-09")
    assert "PIN" in reminder.body
    assert "this week" not in reminder.body.lower()


def test_consent_and_feedback_change_recommendations(scenario):
    customer, state = scenario()
    feed, _ = recommend(customer, state, Prefs())
    first = feed.cards[0]
    dismissed = Prefs(feedback=[FeedbackRow(card_key=first.card_key, card_type=first.card_type,
                                           decision="dismiss", created_at=TODAY)])
    after, _ = recommend(customer, state, dismissed)
    assert first.card_key not in {c.card_key for c in after.cards}
    without_consent, _ = recommend(customer.model_copy(update={"consent_personalization": False}), state, Prefs())
    assert not any(c.commercial for c in without_consent.cards)


def test_unsupported_triggers_do_not_make_financial_claims(scenario):
    customer, state = scenario()
    feed, _ = recommend(customer, state, Prefs())
    types = {c.card_type for c in feed.cards}
    assert "catalog_el_04" not in types  # healthcare never profiles a customer
    assert "catalog_rt_01" not in types  # no pension projection source
    assert "catalog_sv_06" not in types  # no live savings rates


def test_core_money_present_and_feedback_key_stable(scenario):
    customer, state = scenario()
    feed, _ = recommend(customer, state, Prefs())
    card = next(c for c in feed.cards if c.card_type == "core_money")
    assert card.card_key == "core:money"
    assert card.details["metrics"]
    assert card.details["related_cards"]
    assert any(related["card_type"] == "core_goals" and related["details"]["planner"]["kind"] == "savings"
               for related in card.details["related_cards"])
    goals = next(c for c in _core_cards(customer, state, infer_personas(customer, state, Prefs()))
                 if c.card_type == "core_goals")
    assert goals.details["planner"]["kind"] == "savings"
