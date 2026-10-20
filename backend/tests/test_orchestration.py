"""Orchestration: messy partners (reject, timeout, late, demotion), households with joint approval,
stalled journeys and measured outcomes for the life-event goals."""
from __future__ import annotations

import datetime as dt
import os

import pytest
from fastapi.testclient import TestClient

from app import db as dbmod
from app.ecosystem import outcomes, webhooks
from app.ecosystem.models import Estimates, Goal, Progress, ProviderPublic, Step, Win, WinTotals
from app.schemas import Transaction

D = dt.date


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("db") / "kbc_orch.db")
    os.environ["KBC_DB_PATH"] = path
    os.environ["DEMO_PASSWORD"] = "demo"
    os.environ["PARTNER_SIM_DELAY"] = "0"     # simulated partners answer synchronously
    dbmod.DB_PATH = path
    from synth.generate import build

    build(path, n=20, seed=7, verbose=False)
    from app.main import app

    with TestClient(app) as c:
        yield c
    for pid in ("billit", "soluz_io", "immoscoop"):
        webhooks.set_behaviour(pid, "done")


@pytest.fixture(autouse=True)
def default_partners():
    for pid in ("billit", "soluz_io", "immoscoop"):
        webhooks.set_behaviour(pid, "done")
    yield
    for pid in ("billit", "soluz_io", "immoscoop"):
        webhooks.set_behaviour(pid, "done")


def _login(client, username):
    client.cookies.clear()
    assert client.post("/api/login", json={"username": username, "password": "demo"}).status_code == 200


def _step(goal: dict, step_id: str) -> dict:
    return next(s for s in goal["steps"] if s["step_id"] == step_id)


def _goal(resp: dict, goal_id: int) -> dict | None:
    return next((g for g in resp["goals"] if g["goal_id"] == goal_id), None)


def _freelance(client, as_of: str) -> int:
    _login(client, "lotte")
    client.post("/api/me/goals-reset")
    goal = client.post(f"/api/me/goals?as_of={as_of}", json={"playbook_id": "go_freelance"}).json()
    return goal["goal_id"]


def _grants(client, partner_id: str) -> list[dict]:
    return [g for g in client.get("/api/me/consents").json()["grants"] if g["partner_id"] == partner_id]


# ---- messy partners -------------------------------------------------------------------------------------------------


def test_rejection_offers_the_next_partner_and_needs_fresh_consent(client):
    gid = _freelance(client, "2026-10-20")
    webhooks.set_behaviour("billit", "reject")
    goal = client.post(f"/api/me/goals/{gid}/steps/e_invoicing?as_of=2026-10-20", json={"decision": "approve"}).json()
    step = _step(goal, "e_invoicing")
    assert step["status"] == "blocked"
    assert step["fallback"]["reason"] == "rejected" and step["fallback"]["partner_id"] == "soluz_io"
    assert "Fully booked" in step["result"]
    assert [g["status"] for g in _grants(client, "billit")] == ["revoked"]   # Billit's consent ended
    assert _grants(client, "soluz_io") == []                                 # nothing shared with the fallback yet
    assert next(a for a in step["alternatives"] if a["provider"]["id"] == "billit")["tried"]

    # picking the partner that declined again is refused while another one is available
    r = client.post(f"/api/me/goals/{gid}/steps/e_invoicing?as_of=2026-10-20",
                    json={"decision": "approve", "partner_id": "billit"})
    assert r.status_code == 422

    goal = client.post(f"/api/me/goals/{gid}/steps/e_invoicing?as_of=2026-10-20", json={"decision": "approve"}).json()
    step = _step(goal, "e_invoicing")
    assert step["status"] == "done" and step["provider"]["id"] == "soluz_io" and step["fallback"] is None
    assert [g["status"] for g in _grants(client, "soluz_io")] == ["active"]   # a fresh grant, approved by the customer


def test_partner_events_stay_idempotent(client):
    gid = _freelance(client, "2026-10-20")
    webhooks.set_behaviour("billit", "timeout")      # Billit stays silent: we answer for it below
    goal = client.post(f"/api/me/goals/{gid}/steps/e_invoicing?as_of=2026-10-20", json={"decision": "approve"}).json()
    ref = _step(goal, "e_invoicing")["ref"]
    payload = {"event_id": f"{ref}.rejected", "ref": ref, "status": "rejected", "result": "Outside our region"}
    body, headers = webhooks.signed_request("billit", payload)
    assert client.post("/api/partners/billit/webhook", content=body, headers=headers).json() == {"ok": True}
    body, headers = webhooks.signed_request("billit", payload)
    assert client.post("/api/partners/billit/webhook", content=body, headers=headers).json()["duplicate"] is True
    # a partner can't sign for another partner's lead
    body, headers = webhooks.signed_request("soluz_io", payload)
    assert client.post("/api/partners/soluz_io/webhook", content=body, headers=headers).status_code == 404


def test_timeout_moves_on_and_a_late_answer_is_refused(client):
    gid = _freelance(client, "2026-10-10")
    webhooks.set_behaviour("billit", "timeout")
    goal = client.post(f"/api/me/goals/{gid}/steps/e_invoicing?as_of=2026-10-10", json={"decision": "approve"}).json()
    ref = _step(goal, "e_invoicing")["ref"]
    assert _step(goal, "e_invoicing")["status"] == "in_progress"

    # ten days later in simulated time: Billit's 24-hour SLA has passed
    goal = _goal(client.get("/api/me/goals?as_of=2026-10-20").json(), gid)
    step = _step(goal, "e_invoicing")
    assert step["status"] == "blocked" and step["fallback"]["reason"] == "timeout"
    assert step["fallback"]["partner_id"] == "soluz_io"
    assert [g["status"] for g in _grants(client, "billit")] == ["revoked"]
    assert _grants(client, "soluz_io") == []          # never auto-shared: the customer approves again

    body, headers = webhooks.signed_request("billit", {"event_id": f"{ref}.done", "ref": ref, "status": "done",
                                                       "result": "Done after all"})
    assert client.post("/api/partners/billit/webhook", content=body, headers=headers).status_code == 409

    goal = client.post(f"/api/me/goals/{gid}/steps/e_invoicing?as_of=2026-10-20", json={"decision": "approve"}).json()
    assert _step(goal, "e_invoicing")["provider"]["id"] == "soluz_io"
    assert _step(goal, "e_invoicing")["status"] == "done"


def test_scorecard_and_demotion_after_repeated_sla_misses(client):
    webhooks.set_behaviour("billit", "timeout")
    for _ in range(2):
        gid = _freelance(client, "2026-10-10")
        client.post(f"/api/me/goals/{gid}/steps/e_invoicing?as_of=2026-10-10", json={"decision": "approve"})
        client.get("/api/me/goals?as_of=2026-10-20")
    gid = _freelance(client, "2026-10-20")
    goal = _goal(client.get("/api/me/goals?as_of=2026-10-20").json(), gid)
    alts = _step(goal, "e_invoicing")["alternatives"]
    assert alts[0]["provider"]["id"] == "soluz_io" and alts[0]["recommended"]   # Billit no longer first
    assert next(a for a in alts if a["provider"]["id"] == "billit")["demoted"]

    _login(client, "advisor")
    rows = {r["partner_id"]: r for r in client.get("/api/ecosystem/overview").json()["partner_rows"]}
    billit = rows["billit"]
    assert billit["sla_misses"] >= 2 and billit["demoted"] and billit["late_answers"] >= 1
    assert billit["sim_mode"] == "timeout" and billit["outcome_rate_live"] is not None
    assert rows["soluz_io"]["outcome_rate_live"] == 1.0


def test_partner_simulation_switch_is_advisor_only(client):
    _login(client, "lotte")
    assert client.post("/api/ecosystem/partners/billit/simulate", json={"mode": "reject"}).status_code in (401, 403)
    _login(client, "advisor")
    assert client.post("/api/ecosystem/partners/billit/simulate", json={"mode": "reject"}).json()["mode"] == "reject"
    assert client.post("/api/ecosystem/partners/kbc/simulate", json={"mode": "reject"}).status_code == 404
    assert client.post("/api/ecosystem/partners/billit/simulate", json={"mode": "explode"}).status_code == 422


# ---- households -----------------------------------------------------------------------------------------------------

AS_OF = "2021-11-20"


def test_joint_approval_needs_both_and_strangers_see_nothing(client):
    for u in ("sara", "jan"):
        _login(client, u)
        client.post("/api/me/goals-reset")
    _login(client, "lotte")
    client.post("/api/me/goals-reset")
    gid = client.post(f"/api/me/goals?as_of={AS_OF}", json={"playbook_id": "buy_home"}).json()["goal_id"]
    assert client.post(f"/api/me/goals/{gid}/household", json={"username": "nobody"}).status_code == 404
    goal = client.post(f"/api/me/goals/{gid}/household", json={"username": "sara"}).json()
    assert [(m["first_name"], m["status"]) for m in goal["household"]][1][1] == "invited"

    # a stranger can't accept, see, approve or act on it
    _login(client, "jan")
    assert client.post(f"/api/me/household/{gid}", json={"accept": True}).status_code == 404
    assert _goal(client.get("/api/me/goals").json(), gid) is None
    assert client.post(f"/api/me/goals/{gid}/steps/search?as_of={AS_OF}", json={"decision": "approve"}).status_code == 404
    assert client.post(f"/api/me/goals/{gid}/household", json={"username": "jan"}).status_code == 404

    _login(client, "sara")
    resp = client.get("/api/me/goals").json()
    assert [i["goal_id"] for i in resp["invitations"]] == [gid] and _goal(resp, gid) is None
    assert client.post(f"/api/me/household/{gid}", json={"accept": True}).json() == {"ok": True}
    shared = _goal(client.get("/api/me/goals").json(), gid)
    assert shared["role"] == "member"

    # the owner approves a partner step: nothing leaves KBC until the member approves too
    _login(client, "lotte")
    goal = client.post(f"/api/me/goals/{gid}/steps/search?as_of={AS_OF}", json={"decision": "approve"}).json()
    step = _step(goal, "search")
    assert step["joint"] and step["status"] == "proposed"
    assert step["approved_by"] == ["Lotte"] and step["waiting_for"] == ["Sara"]
    assert _grants(client, "immoscoop") == []
    # a KBC step (no data leaves KBC) needs only one tap
    assert _step(client.post(f"/api/me/goals/{gid}/steps/budget?as_of={AS_OF}",
                             json={"decision": "approve"}).json(), "budget")["status"] == "done"

    _login(client, "sara")
    goal = client.post(f"/api/me/goals/{gid}/steps/search?as_of={AS_OF}", json={"decision": "approve"}).json()
    assert _step(goal, "search")["status"] == "done"
    grants = _grants(client, "immoscoop")
    assert len(grants) == 1 and "every household member" in grants[0]["purpose"]

    _login(client, "jan")
    assert client.post(f"/api/me/consents/{grants[0]['grant_id']}/revoke").status_code == 404
    _login(client, "sara")      # either member can revoke
    assert client.post(f"/api/me/consents/{grants[0]['grant_id']}/revoke").status_code == 200
    _login(client, "lotte")
    assert [g["status"] for g in _grants(client, "immoscoop")] == ["revoked"]


def test_personal_goals_cannot_be_shared(client):
    _login(client, "lotte")
    client.post("/api/me/goals-reset")
    gid = client.post("/api/me/goals?as_of=2026-10-20", json={"playbook_id": "go_freelance"}).json()["goal_id"]
    assert client.post(f"/api/me/goals/{gid}/household", json={"username": "sara"}).status_code == 422
    assert client.post(f"/api/me/goals/{gid}/household", json={"username": "lotte"}).status_code == 422


# ---- stalled journeys ---------------------------------------------------------------------------------------------


def _stalled(client, as_of: str, gid: int):
    return _goal(client.get(f"/api/me/goals?as_of={as_of}").json(), gid)["stall"]


def test_stall_prompt_appears_once(client):
    _login(client, "lotte")
    client.post("/api/me/goals-reset")
    gid = client.post(f"/api/me/goals?as_of={AS_OF}", json={"playbook_id": "buy_home"}).json()["goal_id"]
    assert _stalled(client, "2021-12-10", gid) is None              # 20 days: not yet
    prompt = _stalled(client, "2021-12-25", gid)
    assert prompt["days"] == 35 and prompt["options"] == ["keep", "pause", "stop"]
    assert _stalled(client, "2022-01-05", gid) is not None          # still up, within two weeks
    assert _stalled(client, "2022-01-20", gid) is None              # ignored: never again
    assert _stalled(client, "2022-03-01", gid) is None


def test_keep_and_pause_answers(client):
    _login(client, "lotte")
    client.post("/api/me/goals-reset")
    gid = client.post(f"/api/me/goals?as_of={AS_OF}", json={"playbook_id": "buy_home"}).json()["goal_id"]
    assert _stalled(client, "2021-12-25", gid) is not None
    assert client.post(f"/api/me/goals/{gid}/stall?as_of=2021-12-25", json={"answer": "keep"}).json() == {"ok": True}
    assert _stalled(client, "2021-12-26", gid) is None

    client.post("/api/me/goals-reset")
    gid = client.post(f"/api/me/goals?as_of={AS_OF}", json={"playbook_id": "buy_home"}).json()["goal_id"]
    client.post(f"/api/me/goals/{gid}/stall?as_of=2021-12-25", json={"answer": "pause"})
    goal = _goal(client.get("/api/me/goals?as_of=2022-02-01").json(), gid)
    assert goal["paused"] and goal["stall"] is None
    client.post(f"/api/me/goals/{gid}/stall?as_of=2022-02-01", json={"answer": "resume"})
    assert not _goal(client.get("/api/me/goals?as_of=2022-02-01").json(), gid)["paused"]
    _login(client, "jan")
    assert client.post(f"/api/me/goals/{gid}/stall", json={"answer": "stop"}).status_code == 404


# ---- measured outcomes for the new goals ----------------------------------------------------------------------------


def _goal_model(pid: str, done_on: dt.date) -> Goal:
    prov = ProviderPublic(id="kbc", name="KBC", kind="kbc", blurb="", vetting=[], integration="")
    step = Step(step_id="s1", order=1, title="t", description="", provider=prov, why_this_provider="", products=[],
                status="done", data_shared=[], data_not_shared=[], consent_days=0, win=Win(),
                estimates=Estimates(customer_eur=100), done_on=done_on)
    return Goal(goal_id=1, playbook_id=pid, title="t", icon="", tagline="", ecosystems=[], status="active",
                created_on=done_on, origin="detected", evidence=[], progress=Progress(done=1, total=1), steps=[step],
                outcome=WinTotals(), potential=WinTotals())


def _tx(d: dt.date, amount: float, cp: str, cat: str = "other") -> Transaction:
    return Transaction(id=0, customer_id=1, date=d, amount=amount, category=cat, counterparty=cp)


def test_outcome_move_house_deposit_returned():
    g = _goal_model("move_house", D(2026, 6, 1))
    assert outcomes.measure(g, [], D(2026, 7, 1))[0].status == "pending"
    txs = [_tx(D(2026, 8, 1), 1650, "Huurwaarborg Immo Leuven")]
    m = outcomes.measure(g, txs, D(2026, 9, 1))[0]
    assert m.status == "verified" and m.measured_eur == 1650
    assert outcomes.measure(g, [], D(2026, 11, 1))[0].status == "not_met"


def test_outcome_back_on_track():
    g = _goal_model("back_on_track", D(2026, 5, 1))
    before = [_tx(D(2026, m, 5), -120, "Klarna") for m in (1, 2, 3, 4)]
    after = [_tx(D(2026, m, 5), -30, "Klarna") for m in (6, 7)]
    m = outcomes.measure(g, before + after, D(2026, 7, 15))[0]
    assert m.status == "verified" and m.measured_eur > 0
    bounced = before + after + [_tx(D(2026, 6, 20), 45, "Storno domiciliëring Telenet")]
    assert outcomes.measure(g, bounced, D(2026, 7, 15))[0].status == "not_met"
    # a student restaurant called Alma is not pay-later
    assert not outcomes._is_bnpl(_tx(D(2020, 1, 1), -5, "Alma 2 Leuven"))


def test_outcome_ev_switch_and_care():
    g = _goal_model("ev_switch", D(2026, 3, 1))
    fuel = [_tx(D(2025, m, 10), -180, "Q8 Leuven", "transport") for m in range(9, 13)]
    fuel += [_tx(D(2026, m, 10), -180, "Shell Herent", "transport") for m in (1, 2)]
    fuel += [_tx(D(2026, m, 10), -20, "Q8 Leuven", "transport") for m in (5, 6, 7, 8)]
    m = outcomes.measure(g, fuel, D(2026, 8, 20))[0]
    assert m.status == "verified" and m.measured_eur > 1000

    g = _goal_model("care_parent", D(2026, 8, 1))
    care = [_tx(D(2026, m, 3), -1900, "WZC Hof ter Linde (woonzorgcentrum)", "healthcare") for m in (9, 10)]
    m = outcomes.measure(g, care, D(2026, 10, 15), balance_today=5000)[0]
    assert m.status == "verified" and m.measured_eur == 3800
    pension = [_tx(D(2026, 10, 10), 2000, "Federale Pensioendienst", "pension")]
    m = outcomes.measure(g, care + pension, D(2026, 10, 15), balance_today=500)[0]
    assert m.status == "not_met" and "below zero" in m.summary
