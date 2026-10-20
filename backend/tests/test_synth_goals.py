"""Synthetic data: goal scenarios for every playbook and near misses."""
from __future__ import annotations

import datetime as dt
import re
from collections import Counter

import pytest

from synth.generate import NEAR_MISS_LABELS, TODAY, make_regular

N, SEED = 400, 42
GOALS = {"buy_home", "energy_upgrade", "new_baby", "go_freelance", "retire_well", "travel", "peace_of_mind",
         "job_change", "mobility", "first_employee", "inheritance", "study_start",
         "side_job", "go_international", "care_parent", "move_house", "sell_business", "back_on_track",
         "farm_growth", "ev_switch", "first_investment", "together", "separation"}


@pytest.fixture(scope="module")
def portfolio():
    return [make_regular(cid, SEED) for cid in range(1, N + 1)]


def _types(customer) -> list[str]:
    return [e["type"] for e in customer.ground_truth["events"]]


def test_generation_is_deterministic(portfolio):
    for cid in (3, 77, 150):
        c, txs, bal = make_regular(cid, SEED)
        c0, txs0, bal0 = portfolio[cid - 1]
        assert bal == bal0 and c.ground_truth == c0.ground_truth
        assert [(t.date, t.amount, t.counterparty) for t in txs] == [(t.date, t.amount, t.counterparty) for t in txs0]


def test_every_goal_has_truth(portfolio):
    seen = Counter(t.split(":", 1)[1] for c, _, _ in portfolio for t in _types(c) if t.startswith("goal:"))
    missing = GOALS - set(seen)
    assert not missing, f"goals without injected truth: {missing}"


def test_near_misses_exist_and_are_labelled(portfolio):
    near = [c for c, _, _ in portfolio if any(t.startswith("near_miss:") for t in _types(c))]
    assert len(near) >= N * 0.04
    labelled = {t.split(":", 1)[1] for c in near for t in _types(c) if t.startswith("near_miss:")}
    assert labelled <= {g for goals in NEAR_MISS_LABELS.values() for g in goals}
    assert len(labelled) >= 10


def test_one_scenario_per_customer(portfolio):
    """A customer gets a new goal scenario or a near miss, never both (saving_for_house is a real buy_home)."""
    for c, _, _ in portfolio:
        near = {e.get("pattern") for e in c.ground_truth["events"] if e["type"].startswith("near_miss:")}
        assert len(near) <= 1
        goals = {e["type"] for e in c.ground_truth["events"]
                 if e["type"].startswith("goal:") and e.get("kind") != "base_sweep"}
        if near and near != {"saving_for_house"}:
            assert not goals - {"goal:retire_well", "goal:peace_of_mind"}, (c.id, near, goals)


def test_scenarios_never_leave_the_account_overdrawn(portfolio):
    for c, _, bal in portfolio:
        if any(t.startswith(("goal:", "near_miss:")) for t in _types(c)):
            assert bal >= 0, (c.id, _types(c), bal)


def test_contract_counterparties(portfolio):
    """The detectors key on these strings: keep them as the contract writes them."""
    by_goal: dict[str, list] = {}
    for c, txs, _ in portfolio:
        for t in _types(c):
            if t.startswith("goal:"):
                by_goal.setdefault(t.split(":", 1)[1], []).append(txs)
    intl = re.compile(r"\((DE|FR|NL|UK|US|LU|ES|IT)\)$")
    assert any(intl.search(t.counterparty) for txs in by_goal["go_international"] for t in txs
               if t.category == "invoice_income")
    for txs in by_goal["side_job"]:
        assert any("(inschrijving KBO)" in t.counterparty for t in txs)
        recent = [t for t in txs if t.category == "salary" and t.date > TODAY - dt.timedelta(days=60)]
        assert recent, "a side job keeps the salary"
    for txs in by_goal["care_parent"]:
        assert any(t.category == "healthcare" and ("woonzorgcentrum" in t.counterparty or "thuis" in t.counterparty)
                   for t in txs)
    for txs in by_goal["ev_switch"]:
        assert sum(t.counterparty in ("Allego", "Shell Recharge", "Ionity", "Fastned") for t in txs) >= 3


def test_near_miss_webshop_refund_does_not_look_foreign(portfolio):
    intl = re.compile(r"\((DE|FR|NL|UK|US|LU|ES|IT)\)$")
    for c, txs, _ in portfolio:
        if "near_miss:go_international" in _types(c):
            assert not any(intl.search(t.counterparty) for t in txs if t.category == "invoice_income")
