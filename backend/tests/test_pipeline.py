from __future__ import annotations

import datetime as dt

from app.engine.pipeline import build_home, build_timeline, customer_public
from app.schemas import HomeResponse, Prefs, TimelineResponse

from tests.test_features import END
from tests.test_persona import lotte_history

D = dt.date


def test_build_home_validates_and_is_deterministic():
    c, txs = lotte_history()
    now = dt.datetime(2026, 9, 30, 12, 0, tzinfo=dt.timezone.utc)
    home = build_home(c, txs, 2500.0, Prefs(), END, generated_at=now)
    assert isinstance(home, HomeResponse)
    HomeResponse.model_validate(home.model_dump())      # round-trips through the schema
    HomeResponse.model_validate_json(home.model_dump_json())
    again = build_home(c, txs, 2500.0, Prefs(), END, generated_at=now)
    assert home.model_dump() == again.model_dump()
    assert home.customer == customer_public(c)
    assert home.persona_mix[0].persona == "freelancer"
    assert home.layout.sections[0].size == "hero"
    assert home.layout.sections[1].component == "ForYouFeed"
    assert home.feed.cards and all(k.rank_explanation for k in home.feed.cards)
    assert home.llm_copy is False


def test_build_home_changes_with_as_of():
    c, txs = lotte_history()
    student = build_home(c, txs, 2500.0, Prefs(), D(2019, 11, 15))
    freelancer = build_home(c, txs, 2500.0, Prefs(), END)
    assert student.persona_mix[0].persona == "student"
    assert freelancer.persona_mix[0].persona == "freelancer"
    assert {k.card_type for k in freelancer.feed.cards} >= {"vat_reserve"}
    assert not any(k.card_type == "vat_reserve" for k in student.feed.cards)


def test_timeline_milestones():
    c, txs = lotte_history()
    tl = build_timeline(c, txs, 2500.0)
    assert isinstance(tl, TimelineResponse)
    assert tl.min_date == D(2018, 9, 1) and tl.max_date == max(t.date for t in txs)
    labels = {m.label: m.date for m in tl.milestones}
    assert labels["First salary"] == D(2021, 7, 25)
    assert labels["Mortgage"] == D(2022, 3, 15)
    assert labels["Baby"] == D(2024, 2, 10)
    assert labels["Went freelance"] == D(2026, 1, 12)
    assert tl.milestones == sorted(tl.milestones, key=lambda m: m.date)
