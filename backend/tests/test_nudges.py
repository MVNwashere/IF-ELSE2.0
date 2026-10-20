"""Kate nudges: the attention policy (budget, quiet hours, digest, dedupe, mute, learning, urgent bypass), the
demo moments (Lotte's first invoice, Jan's scam alert), what is never pushed, and auth/isolation."""
from __future__ import annotations

import datetime as dt
import os

import pytest
from fastapi.testclient import TestClient

from app import db as dbmod
from app.ecosystem import nudges as N
from app.schemas import KateAction

D = dt.date
T = dt.datetime


def _cand(key: str, tier: str = "deadline", at: T = T(2026, 10, 1, 10, 0), **kw) -> N.Cand:
    return N.Cand(key=key, topic=key.split(":")[0], tier=tier, title=key, why="why", evidence=[],
                  action=KateAction(kind="open_card", label="Open"), at=at, source="test", **kw)


def _run(slots: list[tuple[T, list[N.Cand]]], budget: int = 2, ack_list=None) -> N.SimResult:
    res = N.SimResult(budget=budget)
    urgent_days: set[dt.date] = set()
    for t, cands in slots:
        N._process_slot(res, t, cands, ack_list or [], {}, urgent_days)
    return res


def _channels(res: N.SimResult) -> dict[str, str]:
    return {d.cand.key: d.channel for d in res.deliveries}


# ---- policy (pure) --------------------------------------------------------------------------------------------------


def test_budget_two_a_week_then_inbox():
    slots = [(T(2026, 10, d, 10), [_cand(f"vat_return:k{d}")]) for d in (1, 2, 3)]
    ch = _channels(_run(slots))
    assert ch == {"vat_return:k1": "push", "vat_return:k2": "push", "vat_return:k3": "inbox"}
    # the window is rolling: 7 days after the first push there is room again
    slots.append((T(2026, 10, 8, 11), [_cand("vat_return:k8")]))
    assert _channels(_run(slots))["vat_return:k8"] == "push"


def test_retiree_budget_is_one():
    slots = [(T(2026, 10, d, 10), [_cand(f"trip:k{d}")]) for d in (1, 2)]
    res = _run(slots, budget=N.BUDGET_RETIREE)
    assert _channels(res) == {"trip:k1": "push", "trip:k2": "inbox"}
    assert "Attention budget" in res.deliveries[1].held_reason


def test_urgent_bypasses_budget_and_quiet_hours():
    late = T(2026, 10, 3, 23, 30)
    assert N._deliver_at(_cand("new_payee:x", tier="urgent", at=late)) == late
    slots = [(T(2026, 10, d, 10), [_cand(f"vat_return:k{d}")]) for d in (1, 2)]
    slots.append((late, [_cand("new_payee:x", tier="urgent", at=late)]))
    assert _channels(_run(slots))["new_payee:x"] == "push"


def test_quiet_hours_wait_for_the_morning():
    assert N._deliver_at(_cand("journey_result:1-a", tier="waiting", at=T(2026, 10, 3, 22, 15))) == T(2026, 10, 4, 8)
    assert N._deliver_at(_cand("journey_result:1-a", tier="waiting", at=T(2026, 10, 3, 6, 5))) == T(2026, 10, 3, 8)
    assert N._deliver_at(_cand("journey_result:1-a", tier="waiting", at=T(2026, 10, 3, 14, 5))) == T(2026, 10, 3, 14, 5)


def test_same_slot_is_one_digest_counting_once():
    morning = T(2026, 10, 1, 8)
    res = _run([(morning, [_cand("vat_return:a"), _cand("trip:b", tier="deadline"), _cand("goal_done:3", tier="moment")]),
                (T(2026, 10, 2, 10), [_cand("advance_tax:c")])])
    ch = _channels(res)
    assert ch["vat_return:a"] == ch["trip:b"] == ch["goal_done:3"] == "digest"
    assert ch["advance_tax:c"] == "push" and len(res.pushes) == 2


def test_no_non_urgent_push_after_an_urgent_alert_that_day():
    res = _run([(T(2026, 10, 1, 9), [_cand("new_payee:x", tier="urgent")]), (T(2026, 10, 1, 14), [_cand("trip:b")])])
    assert _channels(res) == {"new_payee:x": "push", "trip:b": "inbox"}


def test_mute_silences_the_topic_for_90_days_and_dismissals_learn():
    mute = [N.Ack("vat_return:old", "vat_return", "mute", D(2026, 9, 1))]
    assert _channels(_run([(T(2026, 10, 1, 10), [_cand("vat_return:new")])], ack_list=mute)) == {}
    assert _channels(_run([(T(2026, 12, 15, 10), [_cand("vat_return:later")])], ack_list=mute)) == {"vat_return:later": "push"}
    # security alerts cannot be muted
    mute_scam = [N.Ack("new_payee:old", "new_payee", "mute", D(2026, 9, 1))]
    assert _channels(_run([(T(2026, 10, 1, 10), [_cand("new_payee:new", tier="urgent", mutable=False)])],
                          ack_list=mute_scam)) == {"new_payee:new": "push"}
    two = [N.Ack(f"trip:{i}", "trip", "dismissed", D(2026, 9, 1)) for i in (1, 2)]
    res = _run([(T(2026, 10, 1, 10), [_cand("trip:3")])], ack_list=two)
    assert _channels(res) == {"trip:3": "inbox"} and "dismissed" in res.deliveries[0].held_reason


# ---- the engine on the demo data ------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("db") / "kbc_nudges.db")
    os.environ["KBC_DB_PATH"] = path
    os.environ["DEMO_PASSWORD"] = "demo"
    os.environ["PARTNER_SIM_DELAY"] = "0"
    dbmod.DB_PATH = path
    from synth.generate import build

    build(path, n=20, seed=7, verbose=False)
    from app.main import app

    with TestClient(app) as c:
        yield c


def _login(client, username):
    client.cookies.clear()
    assert client.post("/api/login", json={"username": username, "password": "demo"}).status_code == 200


def _nudges(client, since: str, as_of: str) -> dict:
    r = client.get(f"/api/me/nudges?since={since}&as_of={as_of}")
    assert r.status_code == 200, r.text
    return r.json()


def test_lotte_hero_nudge_buzzes_on_16_october(client):
    _login(client, "lotte")
    client.post("/api/me/goals-reset")
    client.post("/api/me/nudges-reset")
    assert not any(n["topic"] == "intent_go_freelance" for n in _nudges(client, "2026-10-01", "2026-10-10")["nudges"])
    r = _nudges(client, "2026-10-10", "2026-10-20")
    hero = [n for n in r["nudges"] if n["nudge_key"] == "intent_go_freelance:once"]
    assert len(hero) == 1
    h = hero[0]
    assert h["delivered_at"].startswith("2026-10-16") and h["channel"] == "push" and h["tier"] == "moment"
    assert h["action"]["kind"] == "start_goal" and h["action"]["playbook_id"] == "go_freelance"
    assert "first invoice" in h["title"].lower() and h["why"]
    # deterministic: the same window gives the same answer, and it is sent once
    assert _nudges(client, "2026-10-10", "2026-10-20")["nudges"] == r["nudges"]
    assert not any(n["topic"] == "intent_go_freelance" for n in _nudges(client, "2026-10-17", "2026-10-20")["nudges"])


def test_jan_scam_nudge_is_urgent_and_cannot_be_muted(client):
    _login(client, "jan")
    client.post("/api/me/nudges-reset")
    r = _nudges(client, "2026-10-10", "2026-10-20")
    scam = [n for n in r["nudges"] if n["topic"] == "new_payee"]
    assert scam and scam[0]["tier"] == "urgent" and scam[0]["channel"] == "push" and not scam[0]["mutable"]
    assert scam[0]["action"]["kind"] == "open_card" and scam[0]["action"]["card_key"] == scam[0]["nudge_key"]
    assert r["budget"]["persona"] == "retiree" and r["budget"]["limit"] == 1
    ack = client.post(f"/api/me/nudges/{scam[0]['nudge_key']}/ack?as_of=2026-10-20", json={"action": "mute"}).json()
    assert ack["status"] == "dismissed" and ack["muted_until"] is None
    client.post("/api/me/nudges-reset")


def test_no_nudge_for_price_increase_or_promos(client):
    _login(client, "sara")
    keys = [n["nudge_key"] for n in _nudges(client, "2026-09-01", "2026-10-20")["nudges"]]
    assert not any(k.startswith(("price_increase", "idle_cash", "scam_awareness", "cashflow_squeeze")) for k in keys)
    _login(client, "jan")
    keys = [n["nudge_key"] for n in _nudges(client, "2026-08-25", "2026-10-20")["nudges"]]
    assert not any(k.startswith(("idle_cash", "scam_awareness", "cashflow_squeeze")) for k in keys)


def test_every_nudge_has_one_action_and_a_why(client):
    for user in ("lotte", "sara", "jan", "marc"):
        _login(client, user)
        r = _nudges(client, "2026-09-20", "2026-10-20")
        for n in r["nudges"]:
            assert n["title"] and n["why"] and n["action"]["kind"] in ("open_card", "start_goal", "open_goal")
        pushed = sorted(dt.datetime.fromisoformat(n["delivered_at"]) for n in r["nudges"]
                        if n["tier"] != "urgent" and n["channel"] == "push")
        for i, t in enumerate(pushed):   # never more than the budget in any rolling week (digests not counted here)
            assert sum(1 for u in pushed[: i + 1] if t - u < dt.timedelta(days=7)) <= r["budget"]["limit"]


def test_ack_open_and_mute_persist_per_customer(client):
    _login(client, "sara")
    client.post("/api/me/nudges-reset")
    r = _nudges(client, "2026-09-20", "2026-10-20")
    vat = next(n for n in r["nudges"] if n["topic"] == "vat_return")
    assert client.post(f"/api/me/nudges/{vat['nudge_key']}/ack?as_of=2026-10-20", json={"action": "opened"}).status_code == 200
    again = _nudges(client, "2026-09-20", "2026-10-20")
    assert next(n for n in again["nudges"] if n["nudge_key"] == vat["nudge_key"])["status"] == "opened"

    # muting the topic in September silences the October VAT nudge
    m = client.post("/api/me/nudges/vat_return:2026-07/ack?as_of=2026-09-01", json={"action": "mute"}).json()
    assert m["status"] == "muted" and m["muted_until"] == "2026-11-30"
    assert not any(n["topic"] == "vat_return" for n in _nudges(client, "2026-09-20", "2026-10-20")["nudges"])

    # isolation: Lotte's view is untouched by Sara's acks
    _login(client, "lotte")
    assert all(n["status"] == "new" for n in _nudges(client, "2026-10-10", "2026-10-20")["nudges"])
    _login(client, "sara")
    client.post("/api/me/nudges-reset")
    assert any(n["topic"] == "vat_return" for n in _nudges(client, "2026-09-20", "2026-10-20")["nudges"])


def test_input_validation(client):
    _login(client, "sara")
    assert client.post("/api/me/nudges/vat_return:x/ack", json={"action": "delete"}).status_code == 422
    assert client.post("/api/me/nudges/not-a-key/ack", json={"action": "opened"}).status_code == 422
    assert client.post("/api/me/nudges/marketing:x/ack", json={"action": "opened"}).status_code == 422
    assert client.post("/api/me/nudges/vat_return:x';drop/ack", json={"action": "opened"}).status_code in (404, 422)
    assert client.get("/api/me/nudges?as_of=not-a-date").status_code == 422


def test_auth(client):
    client.cookies.clear()
    assert client.get("/api/me/nudges").status_code == 401
    assert client.get("/api/ecosystem/nudge-stats").status_code == 401
    _login(client, "sara")
    assert client.get("/api/ecosystem/nudge-stats").status_code == 403
    _login(client, "advisor")
    assert client.get("/api/me/nudges").status_code == 403
    s = client.get("/api/ecosystem/nudge-stats").json()
    assert s["customers"] >= 4 and s["max_non_urgent_any_7d"] <= N.BUDGET_DEFAULT
    assert s["naive_pushes"] >= s["pushes"] and {t["tier"] for t in s["by_tier"]} == set(N.TIER_ORDER)
    for c in s["per_customer"]:
        assert c["max_non_urgent_7d"] <= c["budget"]
