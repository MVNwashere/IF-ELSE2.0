"""The demo personas (tom, els, amir, pieter, nina) and Lotte's simulated future chapters."""
from __future__ import annotations

import datetime as dt

import pytest

from app.ecosystem.context import build_context
from app.ecosystem.intent import DETECTORS, detect
from synth.demo_customers import (
    RESERVE, RESERVE_BACK, demo_customers, lotte_future_chapters, lotte_future_transactions,
)
from synth.generate import TODAY

D = dt.date
EXPECTED = {
    "tom": {"side_job"},
    "els": {"care_parent", "study_start"},
    "amir": {"move_house"},
    "pieter": {"go_international"},
    "nina": {"back_on_track"},
}
COMMERCIAL = {"first_investment", "travel", "buy_home", "go_international", "ev_switch", "together"}


@pytest.fixture(scope="module")
def demo():
    out = {}
    for username, customer, txs, balance in demo_customers():
        txs = sorted(txs, key=lambda t: (t.date, t.counterparty))
        for i, t in enumerate(txs):
            t.id = i + 1
        out[username] = (customer, txs, balance)
    return out


def _found(demo, username: str, as_of: dt.date = TODAY) -> set[str]:
    customer, txs, balance = demo[username]
    return {pid for pid, _ in detect(build_context(customer, txs, balance, as_of))}


@pytest.mark.parametrize("username", sorted(EXPECTED))
def test_persona_builds_with_ground_truth(demo, username):
    customer, txs, balance = demo[username]
    assert txs and all(t.date <= TODAY for t in txs)
    goals = {e["type"].split(":", 1)[1] for e in customer.ground_truth["events"] if e["type"].startswith("goal:")}
    assert goals == EXPECTED[username]
    assert len({c.id for _, c, _, _ in demo_customers()}) == len(demo_customers())   # unique ids


def test_unique_usernames():
    names = [u for u, *_ in demo_customers()]
    assert len(names) == len(set(names)) and {"tom", "els", "amir", "pieter", "nina"} <= set(names)


def test_balances_make_sense(demo):
    assert demo["pieter"][2] > 20000                  # a healthy business
    assert 0 <= demo["nina"][2] < 2500                # tight, but not overdrawn today
    assert demo["amir"][2] > 0


def test_newcomer_short_history(demo):
    _, txs, _ = demo["amir"]
    assert (TODAY - txs[0].date).days < 140           # about four months
    _found(demo, "amir")                              # every detector copes with a short history


@pytest.mark.parametrize("username", sorted(EXPECTED))
def test_intended_goals_detected(demo, username):
    missing = [g for g in EXPECTED[username] if g not in DETECTORS]
    if missing:
        pytest.xfail(f"detector(s) not built yet: {missing}")
    assert EXPECTED[username] <= _found(demo, username)


def test_nina_gets_no_commercial_goal(demo):
    assert not (COMMERCIAL & _found(demo, "nina"))


def test_tom_is_not_going_freelance(demo):
    assert "go_freelance" not in _found(demo, "tom")  # the salary keeps coming: a side job


def test_lotte_future_is_not_stored(demo):
    _, txs, _ = demo["lotte"]
    assert max(t.date for t in txs) <= TODAY


def test_lotte_future_chapters():
    chapters = lotte_future_chapters()
    assert [c["id"] for c in chapters] == ["first_vat", "trip", "first_employee", "regularisation"]
    assert all(t.date > TODAY for c in chapters for t in c["txs"])
    assert all(c["txs"] for c in chapters)


def test_reserve_covers_the_regularisation():
    reserve, lowest, paid = 0.0, 0.0, False
    for t in lotte_future_transactions():
        if t.counterparty == RESERVE:
            reserve -= t.amount
        elif t.counterparty == RESERVE_BACK:
            reserve -= t.amount
        elif "regularisatie" in t.counterparty:
            paid = t.amount < -1000
        lowest = min(lowest, reserve)
    assert paid and lowest >= -0.01 and reserve >= 0
