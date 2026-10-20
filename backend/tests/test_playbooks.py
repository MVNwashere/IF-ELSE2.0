"""The life-event and business goal playbooks, their partners, feed links and Kate's phrases."""
from types import SimpleNamespace

import pytest

from app.ecosystem.links import CARD_PLAYBOOK, CARD_TYPE_PLAYBOOK
from app.ecosystem.registry import SENSITIVE_NEVER_TO_PARTNERS, registry
from app.ecosystem.service import payload_for
from app.engine.kate import _goal_intent

NEW_GOALS = ("side_job", "go_international", "care_parent", "move_house", "sell_business", "back_on_track",
             "farm_growth", "ev_switch", "first_investment", "together", "separation")
CHAINS = {"side_job": "go_freelance", "go_international": "first_employee", "sell_business": "retire_well",
          "together": "buy_home", "separation": "move_house", "back_on_track": "peace_of_mind",
          "move_house": "buy_home", "ev_switch": "energy_upgrade"}
SOFT_PARTNERS = ("budget_coach", "family_mediator", "notary_network")   # no commission on life's hard moments


@pytest.mark.parametrize("goal", NEW_GOALS)
def test_new_playbook_is_valid(goal):
    pb = registry().playbooks[goal]
    assert 3 <= len(pb.steps) <= 6
    assert pb.trigger and pb.tagline and pb.ecosystems


def test_chains():
    reg = registry()
    for goal, nxt in CHAINS.items():
        assert reg.playbooks[goal].next_goal == nxt


def test_new_ecosystems_are_covered():
    reg = registry()
    used = {reg.catalogue[p].ecosystem for pb in reg.playbooks.values() for s in pb.steps for p in s.products}
    for eco in ("International business", "Health and wellbeing", "Agriculture and horticulture", "Security",
                "Administration and documents", "Investing", "Family and protection"):
        assert eco in used, eco
    assert {"business-valuation-advice", "business-transfer-advice", "go-deal-pro", "agroflex-credit",
            "online-fraud-insurance", "invest-spare-change", "registered-email-ipex"} <= reg.used_building_blocks()


def test_back_on_track_has_no_upsell():
    reg = registry()
    pb = reg.playbooks["back_on_track"]
    credit = {c for c in reg.catalogue if "loan" in c or "credit" in c or "budget-facility" in c}
    for s in pb.steps:
        assert not s.kbc_products, s.id
        assert s.estimates.kbc_revenue_eur == 0, s.id
        assert not set(s.products) & credit, s.id
        partner = reg.partners[s.provider]
        if partner.kind == "partner":
            assert partner.value_share.amount_eur == 0 and partner.value_share.pct == 0


def test_soft_partners_earn_kbc_nothing():
    reg = registry()
    for pid in SOFT_PARTNERS:
        vs = reg.partners[pid].value_share
        assert vs.amount_eur == 0 and vs.pct == 0, pid


def test_new_partners_never_receive_bank_data():
    reg = registry()
    ctx = SimpleNamespace(values={f: f"<{f}>" for f in reg.fields})
    for goal in NEW_GOALS:
        for s in reg.playbooks[goal].steps:
            if reg.partners[s.provider].kind != "partner":
                continue
            # even a grant that (wrongly) lists everything only lets the partner's allowed fields through
            out = payload_for(s, list(reg.fields), ctx)
            assert not set(out) & set(SENSITIVE_NEVER_TO_PARTNERS), (goal, s.id)
            assert set(out) <= set(reg.partners[s.provider].allowed_fields)


def test_sensitive_new_fields_are_marked():
    reg = registry()
    assert reg.fields["care_need"].sensitive and reg.fields["debt_overview"].sensitive


def test_alternatives_for_new_steps():
    reg = registry()
    step = reg.step("move_house", "commute")
    assert set(reg.options("move_house", step)) == {"cambio", "mobit", "blue_bike"}
    assert set(reg.options("side_job", reg.step("side_job", "e_invoicing"))) == {"billit", "soluz_io"}


def test_feed_links_point_to_existing_playbooks():
    reg = registry()
    for mapping in (CARD_PLAYBOOK, CARD_TYPE_PLAYBOOK):
        for options in mapping.values():
            for pid in (options,) if isinstance(options, str) else options:
                assert pid in reg.playbooks, pid
    assert CARD_PLAYBOOK["LE-04"] == "together"
    assert CARD_PLAYBOOK["LE-01"][0] == "move_house"


def _goals():
    reg = registry()
    return SimpleNamespace(
        goals=[], candidates=[],
        playbooks=[SimpleNamespace(playbook_id=p.id, title=p.title, steps=len(p.steps)) for p in reg.playbooks.values()])


@pytest.mark.parametrize("text,goal", [
    ("i'm starting a side business", "side_job"),
    ("my mother is moving into a care home", "care_parent"),
    ("we're moving in together", "together"),
    ("we're separating, what happens with the mortgage?", "separation"),
    ("i want to start investing", "first_investment"),
    ("i want an electric car", "ev_switch"),
    ("i'm behind on my bills and the bailiff wrote", "back_on_track"),
    ("i want to sell my business in a few years", "sell_business"),
    ("i have my first clients abroad", "go_international"),
    ("we're moving house next month", "move_house"),
    # older goals keep their phrases
    ("i want to invest my savings", "retire_well"),
    ("we're planning an international trip", "travel"),
    ("i want to buy a house", "buy_home"),
])
def test_kate_offers_the_right_goal(text, goal):
    r = _goal_intent(_goals(), text)
    assert r is not None and r.actions[0].kind == "start_goal" and r.actions[0].playbook_id == goal


def test_kate_is_gentle_on_hard_moments():
    r = _goal_intent(_goals(), "i have debt i can't pay")
    assert r.reply.startswith("Thanks for telling me")
