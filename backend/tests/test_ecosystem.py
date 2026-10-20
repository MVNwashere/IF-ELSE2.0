"""Ecosystem engine: intent detection, journeys, consent and data minimisation, signed partner webhooks, isolation."""
from __future__ import annotations

import datetime as dt
import json
import os

import pytest
from fastapi.testclient import TestClient

from app import db as dbmod
from app.ecosystem import webhooks
from app.ecosystem.context import build_context
from app.ecosystem.intent import detect
from app.ecosystem.registry import registry
from app.ecosystem.service import payload_for
from synth.demo_customers import demo_customers

D = dt.date


@pytest.fixture(scope="module")
def demo():
    out = {}
    for username, customer, txs, balance in demo_customers():
        txs = sorted(txs, key=lambda t: (t.date, t.counterparty))
        for i, t in enumerate(txs):
            t.id = i + 1
        out[username] = (customer, txs, balance)
    return out


def _goals(demo, username: str, as_of: dt.date) -> dict:
    customer, txs, balance = demo[username]
    return {pid: d for pid, d in detect(build_context(customer, txs, balance, as_of))}


# ---- configuration -------------------------------------------------------------------------------------------------


def test_registry_uses_real_catalogue_items():
    reg = registry()
    assert len(reg.catalogue) == 229 and len(reg.playbooks) >= 13
    assert reg.used_building_blocks() <= set(reg.catalogue)


def test_partner_steps_never_ask_more_than_partner_may_receive():
    reg = registry()
    for pb in reg.playbooks.values():
        for s in pb.steps:
            assert set(s.fields) <= set(reg.partners[s.provider].allowed_fields)
            if reg.partners[s.provider].kind == "partner":
                assert not {"income", "balances", "transactions"} & set(s.fields)


# ---- intent detection --------------------------------------------------------------------------------------------


def test_lotte_house_hunt_is_spotted_before_the_deed(demo):
    assert "buy_home" not in _goals(demo, "lotte", D(2021, 8, 20))
    early = _goals(demo, "lotte", D(2021, 11, 20))["buy_home"]
    late = _goals(demo, "lotte", D(2022, 2, 15))["buy_home"]
    assert 0.5 <= early[0] < late[0]
    assert any("escrow" in e for e in late[1])
    assert "buy_home" not in _goals(demo, "lotte", D(2022, 5, 1))   # she owns the house now


def test_life_goals_chain_over_lottes_years(demo):
    assert "energy_upgrade" in _goals(demo, "lotte", D(2022, 12, 1))
    assert "new_baby" in _goals(demo, "lotte", D(2024, 1, 20))
    assert "go_freelance" not in _goals(demo, "lotte", D(2026, 10, 10))   # left her job, no client paid yet
    assert "go_freelance" in _goals(demo, "lotte", D(2026, 10, 20))     # first invoice paid on 16 Oct


def test_each_demo_customer_has_their_goal(demo):
    assert "get_paid" in _goals(demo, "sara", D(2026, 10, 20))
    assert "peace_of_mind" in _goals(demo, "jan", D(2026, 10, 20))
    marc = _goals(demo, "marc", D(2026, 10, 20))
    assert "retire_well" in marc and "travel" in marc


def test_income_never_leaves_kbc_for_immoscoop(demo):
    customer, txs, balance = demo["lotte"]
    ctx = build_context(customer, txs, balance, D(2021, 11, 20))
    step = registry().step("buy_home", "search")
    # even a grant that (wrongly) lists income is filtered by the partner's allowed fields
    payload = payload_for(step, step.fields + ["income", "balances"], ctx)
    assert set(payload) == {"first_name", "email", "region", "budget_range"}
    assert ctx.values["income"] not in json.dumps(payload)


# ---- API ------------------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("db") / "kbc_eco.db")
    os.environ["KBC_DB_PATH"] = path
    os.environ["DEMO_PASSWORD"] = "demo"
    os.environ["PARTNER_SIM_DELAY"] = "0"     # the simulated partner answers synchronously
    dbmod.DB_PATH = path
    from synth.generate import build

    build(path, n=20, seed=7, verbose=False)
    from app.main import app

    with TestClient(app) as c:
        yield c


def _login(client, username):
    client.cookies.clear()
    assert client.post("/api/login", json={"username": username, "password": "demo"}).status_code == 200


AS_OF = "2021-11-20"


def test_goal_journey_end_to_end(client):
    _login(client, "lotte")
    client.post("/api/me/goals-reset")
    r = client.get(f"/api/me/goals?as_of={AS_OF}").json()
    assert [c["playbook_id"] for c in r["candidates"]][:1] == ["buy_home"]
    assert "home-loan" not in [h["id"] for h in r["holdings"]]   # time travel: no mortgage yet in 2021

    goal = client.post(f"/api/me/goals?as_of={AS_OF}", json={"playbook_id": "buy_home"}).json()
    assert goal["origin"] == "detected" and goal["progress"] == {"done": 0, "total": 7}
    gid = goal["goal_id"]

    # a KBC step completes immediately
    goal = client.post(f"/api/me/goals/{gid}/steps/budget?as_of={AS_OF}", json={"decision": "approve"}).json()
    budget = next(s for s in goal["steps"] if s["step_id"] == "budget")
    assert budget["status"] == "done" and "€" in budget["result"]

    # a partner step: consent grant → outbound → signed webhook from the (simulated) partner → done
    goal = client.post(f"/api/me/goals/{gid}/steps/search?as_of={AS_OF}", json={"decision": "approve"}).json()
    search = next(s for s in goal["steps"] if s["step_id"] == "search")
    assert search["status"] == "done" and "Immoscoop" == search["provider"]["name"]
    assert goal["outcome"]["partner_leads"] == 1 and goal["outcome"]["partner_fees_eur"] == 45

    consents = client.get(f"/api/me/consents?as_of={AS_OF}").json()
    assert consents["partners_with_access"] == 1
    assert {f["field"] for f in consents["grants"][0]["fields"]} == {"first_name", "email", "region", "budget_range"}

    # the candidate is gone now the goal runs, and starting it twice returns the same goal
    assert "buy_home" not in [c["playbook_id"] for c in client.get(f"/api/me/goals?as_of={AS_OF}").json()["candidates"]]
    assert client.post(f"/api/me/goals?as_of={AS_OF}", json={"playbook_id": "buy_home"}).json()["goal_id"] == gid


def test_revoke_blocks_an_open_partner_step(client, monkeypatch):
    _login(client, "lotte")
    client.post("/api/me/goals-reset")
    gid = client.post(f"/api/me/goals?as_of={AS_OF}", json={"playbook_id": "buy_home"}).json()["goal_id"]
    monkeypatch.setattr("app.ecosystem.service.run_simulations", lambda pending: None)   # partner hasn't answered
    goal = client.post(f"/api/me/goals/{gid}/steps/certificates?as_of={AS_OF}", json={"decision": "approve"}).json()
    step = next(s for s in goal["steps"] if s["step_id"] == "certificates")
    assert step["status"] == "in_progress"
    client.post(f"/api/me/consents/{step['grant_id']}/revoke?as_of={AS_OF}")
    goal = next(g for g in client.get(f"/api/me/goals?as_of={AS_OF}").json()["goals"] if g["goal_id"] == gid)
    assert next(s for s in goal["steps"] if s["step_id"] == "certificates")["status"] == "blocked"

    # the partner answering after the revoke is refused
    body, headers = webhooks.signed_request("de_immowinkel", {"event_id": "late-answer-1", "ref": step["ref"],
                                                              "status": "done", "result": "EPC ready"})
    assert client.post("/api/partners/de_immowinkel/webhook", content=body, headers=headers).status_code == 409


def test_webhook_rejects_bad_signatures_and_other_partners(client):
    _login(client, "lotte")
    client.post("/api/me/goals-reset")
    gid = client.post(f"/api/me/goals?as_of={AS_OF}", json={"playbook_id": "buy_home"}).json()["goal_id"]
    import app.ecosystem.service as svc
    original = svc.run_simulations
    svc.run_simulations = lambda pending: None
    try:
        goal = client.post(f"/api/me/goals/{gid}/steps/renovation?as_of={AS_OF}", json={"decision": "approve"}).json()
    finally:
        svc.run_simulations = original
    ref = next(s for s in goal["steps"] if s["step_id"] == "renovation")["ref"]
    event = {"event_id": "setle-evt-0001", "ref": ref, "status": "done", "result": "Report ready"}

    body, headers = webhooks.signed_request("setle", event)
    tampered = body.replace(b"Report ready", b"Report fake!")
    assert client.post("/api/partners/setle/webhook", content=tampered, headers=headers).status_code == 401
    assert client.post("/api/partners/setle/webhook", content=body, headers={}).status_code == 401
    # Immoscoop signing for Setle's step: wrong key for the path, and the ref isn't routed to it
    body_i, headers_i = webhooks.signed_request("immoscoop", event)
    assert client.post("/api/partners/setle/webhook", content=body_i, headers=headers_i).status_code == 401
    assert client.post("/api/partners/immoscoop/webhook", content=body_i, headers=headers_i).status_code == 404
    # extra keys are rejected
    body_x, headers_x = webhooks.signed_request("setle", {**event, "event_id": "setle-evt-0002", "income": 1})
    assert client.post("/api/partners/setle/webhook", content=body_x, headers=headers_x).status_code == 422

    assert client.post("/api/partners/setle/webhook", content=body, headers=headers).json() == {"ok": True}
    replay = client.post("/api/partners/setle/webhook", content=body, headers=headers).json()
    assert replay == {"ok": True, "duplicate": True}
    goal = next(g for g in client.get(f"/api/me/goals?as_of={AS_OF}").json()["goals"] if g["goal_id"] == gid)
    assert next(s for s in goal["steps"] if s["step_id"] == "renovation")["result"] == "Report ready"


def test_goals_and_grants_are_customer_bound(client):
    _login(client, "lotte")
    client.post("/api/me/goals-reset")
    gid = client.post(f"/api/me/goals?as_of={AS_OF}", json={"playbook_id": "buy_home"}).json()["goal_id"]
    goal = client.post(f"/api/me/goals/{gid}/steps/search?as_of={AS_OF}", json={"decision": "approve"}).json()
    grant_id = next(s for s in goal["steps"] if s["step_id"] == "search")["grant_id"]
    _login(client, "sara")
    assert client.post(f"/api/me/goals/{gid}/steps/budget", json={"decision": "approve"}).status_code == 404
    assert client.post(f"/api/me/goals/{gid}/cancel").status_code == 404
    assert client.post(f"/api/me/consents/{grant_id}/revoke").status_code == 404
    assert client.get("/api/me/consents").json()["grants"] == []
    assert client.get("/api/ecosystem/overview").status_code == 403


def test_input_validation(client):
    _login(client, "sara")
    assert client.post("/api/me/goals", json={"playbook_id": "../etc"}).status_code == 422
    assert client.post("/api/me/goals", json={"playbook_id": "nope"}).status_code == 404
    assert client.post("/api/me/goals/1/steps/BAD-ID", json={"decision": "approve"}).status_code == 422
    assert client.post("/api/me/goals/1/steps/budget", json={"decision": "sudo"}).status_code == 422


def test_already_held_steps_are_not_asked_twice(client):
    _login(client, "marc")
    client.post("/api/me/goals-reset")
    goal = client.post("/api/me/goals", json={"playbook_id": "retire_well"}).json()
    held = {s["step_id"] for s in goal["steps"] if s["already_held"]}
    assert held == {"pension_savings"}


def test_kate_offers_the_journey(client):
    _login(client, "sara")
    client.post("/api/me/goals-reset")
    r = client.post("/api/me/kate", json={"message": "a client owes me money"}).json()
    assert r["actions"][0]["kind"] == "start_goal" and r["actions"][0]["playbook_id"] == "get_paid"
    opener = client.post("/api/me/kate", json={"message": ""}).json()
    assert any(a["kind"] == "start_goal" for a in opener["actions"])


def test_feed_cards_link_to_journeys(client):
    _login(client, "marc")
    cards = client.get("/api/me/home").json()["feed"]["cards"]
    linked = [c for c in cards if c["details"].get("playbook_id")]
    assert linked and all(c["details"]["products"] for c in linked)


def test_ecosystem_console(client):
    _login(client, "advisor")
    o = client.get("/api/ecosystem/overview").json()
    assert o["catalogue_items"] == 229 and o["partners"] >= 10
    assert any(r["detected"] > 0 for r in o["funnel"])
    assert any(e["kind"] == "outbound" for e in o["events"])
