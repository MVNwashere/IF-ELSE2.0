"""Core engine round 2: measured outcomes, inbound data sources, partner alternatives and fee transparency,
deletion webhooks, partner onboarding manifests, advisor handoff and the learning loop."""
from __future__ import annotations

import datetime as dt
import os

import pytest
from fastapi.testclient import TestClient

from app import db as dbmod
from app.ecosystem import webhooks
from app.ecosystem.models import Estimates, Goal, Step
from app.ecosystem.outcomes import measure
from app.ecosystem.registry import registry
from app.schemas import Transaction

D = dt.date


# ---- outcomes (pure) ------------------------------------------------------------------------------------------------


def _goal(playbook_id: str, created: dt.date, done: dict[str, dt.date], est: float = 600) -> Goal:
    pb = registry().playbooks[playbook_id]
    steps = [Step.model_construct(step_id=s.id, status="done" if s.id in done else "proposed", already_held=False,
                                  done_on=done.get(s.id), estimates=Estimates(customer_eur=est if s.id in done else 0))
             for s in pb.steps]
    return Goal.model_construct(playbook_id=playbook_id, created_on=created, steps=steps)


def _bills(start: dt.date, months: int, amount: float) -> list[Transaction]:
    out = []
    for i in range(months):
        y, m = divmod(start.month - 1 + i, 12)
        out.append(Transaction(id=len(out) + 1, customer_id=1, date=D(start.year + y, m + 1, 5), amount=-amount,
                               category="utilities", counterparty="Luminus"))
    return out


def test_energy_saving_is_verified_from_later_bills():
    txs = _bills(D(2023, 1, 1), 12, 280) + _bills(D(2024, 1, 1), 8, 160)
    goal = _goal("energy_upgrade", D(2023, 11, 1), {"advice": D(2023, 11, 1), "group_purchase": D(2023, 11, 1)})
    [m] = measure(goal, txs, D(2024, 8, 1))
    assert m.status == "verified" and m.metric == "energy_spend"
    assert 1300 <= m.measured_eur <= 1500          # (280 - 160) × 12
    assert m.estimate_eur == 1200 and any("Before" in e for e in m.evidence)


def test_energy_outcome_is_pending_before_the_data_exists():
    txs = _bills(D(2023, 1, 1), 12, 280)
    goal = _goal("energy_upgrade", D(2023, 11, 1), {"advice": D(2023, 11, 1)})
    [m] = measure(goal, txs, D(2023, 12, 1))
    assert m.status == "pending" and m.check_on == D(2024, 3, 30)
    assert "We'll compare" in m.summary
    assert measure(_goal("energy_upgrade", D(2023, 11, 1), {}), txs, D(2024, 8, 1)) == []   # no steps done


def test_late_client_payments_resume():
    pay = lambda d: Transaction(id=1, customer_id=1, date=d, amount=2000, category="invoice_income",   # noqa: E731
                                counterparty="Acme NV")
    txs = [pay(D(2026, m, 1)) for m in range(1, 6)]
    goal = _goal("get_paid", D(2026, 8, 1), {"reminders": D(2026, 8, 1)}, est=0)
    [m] = measure(goal, txs, D(2026, 8, 10))
    assert m.status == "pending" and "Acme NV" in m.label
    [m] = measure(goal, txs + [pay(D(2026, 8, 20))], D(2026, 9, 1))
    assert m.status == "verified" and m.measured_eur == 2000


def test_travel_insured_before_departure():
    goal = _goal("travel", D(2026, 6, 1), {"insurance": D(2026, 6, 2)})
    [m] = measure(goal, [], D(2026, 6, 3))
    assert m.status == "verified" and "before you leave" in m.summary


# ---- API ------------------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("db") / "kbc_core.db")
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


def _audit(action: str) -> list[str]:
    with dbmod.tx() as conn:
        return [r["target"] for r in conn.execute("SELECT target FROM audit_log WHERE action = ?", (action,))]


def test_measured_outcome_via_time_travel(client):
    _login(client, "lotte")
    client.post("/api/me/goals-reset")
    at = "2023-02-01"
    gid = client.post(f"/api/me/goals?as_of={at}", json={"playbook_id": "energy_upgrade"}).json()["goal_id"]
    goal = client.post(f"/api/me/goals/{gid}/steps/group_purchase?as_of={at}", json={"decision": "approve"}).json()
    [m] = goal["measured"]
    assert m["status"] == "pending" and m["check_on"]
    later = next(g for g in client.get("/api/me/goals?as_of=2024-06-01").json()["goals"] if g["goal_id"] == gid)
    [m] = later["measured"]
    assert m["status"] == "verified" and m["measured_eur"] > 0 and m["estimate_eur"] == 180


def test_sources_connect_disconnect_isolation_and_audit(client):
    _login(client, "marc")
    client.post("/api/me/goals-reset")
    r = client.get("/api/me/sources").json()
    mp = next(s for s in r["sources"] if s["source_id"] == "mypension")
    assert mp["status"] == "available" and mp["values"] == {} and mp["needs_consent"]
    # purpose binding: mypension is not for a travel goal
    assert client.post("/api/me/sources/mypension/connect", json={"playbook_id": "travel"}).status_code == 422
    assert client.post("/api/me/sources/kbo/connect", json={"playbook_id": "go_freelance"}).status_code == 409
    assert client.post("/api/me/sources/nope/connect", json={"playbook_id": "retire_well"}).status_code == 404
    assert client.post("/api/me/sources/BAD!/connect", json={"playbook_id": "retire_well"}).status_code in (404, 422)
    assert client.post("/api/me/sources/mypension/connect",
                       json={"playbook_id": "retire_well", "extra": 1}).status_code == 422
    r = client.post("/api/me/sources/mypension/connect", json={"playbook_id": "retire_well"}).json()
    mp = next(s for s in r["sources"] if s["source_id"] == "mypension")
    assert mp["status"] == "connected" and mp["values"]["pension_statutory_monthly_eur"] > 0
    assert mp["expires_on"] and mp["playbook_id"] == "retire_well"
    assert any(s["source_id"] == "mypension" for s in client.get("/api/me/consents").json()["sources"])
    assert any(t.startswith("mypension") for t in _audit("source.connect"))

    from app.ecosystem import sources
    with dbmod.tx() as conn:
        marc_id = conn.execute("SELECT customer_id FROM users WHERE username = 'marc'").fetchone()[0]
        assert "pension_statutory_monthly_eur" in sources.values_for(conn, marc_id, D(2026, 10, 20))
        assert sources.values_for(conn, marc_id, D(2020, 1, 1)).get("pension_statutory_monthly_eur") is None

    # the step hint now says it's connected
    goal = client.post("/api/me/goals", json={"playbook_id": "retire_well"}).json()
    gap = next(s for s in goal["steps"] if s["step_id"] == "pension_gap")
    assert gap["source_hint"]["source_id"] == "mypension" and gap["source_hint"]["connected"]

    # another customer sees nothing of it
    _login(client, "sara")
    r = client.get("/api/me/sources").json()
    assert next(s for s in r["sources"] if s["source_id"] == "mypension")["status"] == "available"
    client.post("/api/me/sources/mypension/disconnect")   # disconnects only sara's (none)
    _login(client, "marc")
    r = client.post("/api/me/sources/mypension/disconnect").json()
    assert next(s for s in r["sources"] if s["source_id"] == "mypension")["status"] == "available"
    assert "mypension" in _audit("source.disconnect")
    with dbmod.tx() as conn:
        assert "pension_statutory_monthly_eur" not in sources.values_for(conn, marc_id, D(2026, 10, 20))


def test_partner_alternatives_choice_and_fee_transparency(client):
    _login(client, "lotte")
    client.post("/api/me/goals-reset")
    goal = client.post("/api/me/goals", json={"playbook_id": "go_freelance"}).json()
    step = next(s for s in goal["steps"] if s["step_id"] == "e_invoicing")
    names = [o["provider"]["id"] for o in step["alternatives"]]
    assert set(names) == {"billit", "soluz_io"} and step["alternatives"][0]["recommended"]
    # ranked by outcome rate, never by fee
    rates = [o["outcome_rate"] for o in step["alternatives"]]
    assert rates == sorted(rates, reverse=True)
    assert "KBC earns" in step["fee"]["kbc_earns"] and all("KBC earns" in o["fee"]["kbc_earns"] for o in step["alternatives"])
    gid = goal["goal_id"]
    url = f"/api/me/goals/{gid}/steps/e_invoicing"
    assert client.post(url, json={"decision": "approve", "partner_id": "immoscoop"}).status_code == 422
    assert client.post(url, json={"decision": "approve", "partner_id": "BAD ID"}).status_code == 422
    assert client.post(url, json={"decision": "decline", "partner_id": "soluz_io"}).status_code == 422
    goal = client.post(url, json={"decision": "approve", "partner_id": "soluz_io"}).json()
    step = next(s for s in goal["steps"] if s["step_id"] == "e_invoicing")
    assert step["provider"]["id"] == "soluz_io" and step["status"] == "done"   # Soluz.io answered via its webhook
    assert next(o for o in step["alternatives"] if o["provider"]["id"] == "soluz_io")["chosen"]
    grant = client.get("/api/me/consents").json()["grants"][0]
    assert grant["partner_id"] == "soluz_io" and "KBC earns" in grant["kbc_earns"]


def test_partner_confirms_deletion_after_revoke(client, monkeypatch):
    _login(client, "lotte")
    client.post("/api/me/goals-reset")
    gid = client.post("/api/me/goals?as_of=2021-11-20", json={"playbook_id": "buy_home"}).json()["goal_id"]
    goal = client.post(f"/api/me/goals/{gid}/steps/search?as_of=2021-11-20", json={"decision": "approve"}).json()
    step = next(s for s in goal["steps"] if s["step_id"] == "search")
    # a deletion confirmation while the consent is still active is refused
    body, headers = webhooks.signed_request("immoscoop", {"event_id": "imm-del-early", "ref": step["ref"],
                                                          "status": "deleted"})
    assert client.post("/api/partners/immoscoop/webhook", content=body, headers=headers).status_code == 409
    r = client.post(f"/api/me/consents/{step['grant_id']}/revoke?as_of=2021-11-20").json()
    g = next(x for x in r["grants"] if x["grant_id"] == step["grant_id"])
    assert g["status"] == "revoked" and g["deletion_confirmed_by"] == "Immoscoop" and g["deletion_confirmed_at"]
    with dbmod.tx() as conn:
        kinds = [e["kind"] for e in conn.execute("SELECT kind FROM eco_events WHERE partner_id = 'immoscoop'")]
    assert "deleted" in kinds


def test_partner_manifest_validation(client):
    manifest = {
        "id": "new_partner", "name": "New Partner", "ecosystems": ["Mobility"], "catalogue_ids": ["car-sharing-cambio"],
        "allowed_fields": ["first_name", "email"], "value_share": {"model": "lead_fee", "amount_eur": 10},
        "webhook": {"url": "https://partner.example.com/kbc", "events": ["done", "deleted"]}, "sla_hours": 24,
    }
    _login(client, "lotte")
    assert client.post("/api/ecosystem/partners/manifest", json=manifest).status_code == 403
    _login(client, "advisor")
    r = client.post("/api/ecosystem/partners/manifest", json=manifest).json()
    assert r["valid"] and r["signing"]["secret_env"] == "PARTNER_WEBHOOK_SECRET_NEW_PARTNER"
    assert len(r["signing"]["key_fingerprint"]) == 12
    assert webhooks.secret_of("new_partner").hex() not in str(r)       # the key itself is never returned
    bad = client.post("/api/ecosystem/partners/manifest",
                      json={**manifest, "id": "bad_partner", "allowed_fields": ["first_name", "income", "dna"]}).json()
    assert not bad["valid"]
    assert any("unknown field dna" in p for p in bad["problems"]) and any("income" in p for p in bad["problems"])
    assert not client.post("/api/ecosystem/partners/manifest", json={**manifest, "id": "billit"}).json()["valid"]
    assert client.post("/api/ecosystem/partners/manifest", json={**manifest, "rogue": 1}).status_code == 422
    assert client.post("/api/ecosystem/partners/manifest",
                       json={**manifest, "webhook": {"url": "http://x.example.com", "events": ["done"]}}).status_code == 422
    assert [m["id"] for m in client.get("/api/ecosystem/partners/onboarding").json()] == ["new_partner"]


def test_advisor_handoff_books_a_meeting(client):
    _login(client, "marc")
    client.post("/api/me/goals-reset")
    goal = client.post("/api/me/goals", json={"playbook_id": "retire_well"}).json()
    step = next(s for s in goal["steps"] if s["step_id"] == "private_banker")
    assert step["provider"]["kind"] == "advisor" and step["data_shared"] == []
    goal = client.post(f"/api/me/goals/{goal['goal_id']}/steps/private_banker", json={"decision": "approve"}).json()
    step = next(s for s in goal["steps"] if s["step_id"] == "private_banker")
    assert step["status"] == "done" and "Meeting booked" in step["booking"]
    assert client.get("/api/me/consents").json()["grants"] == []    # nothing left KBC


def test_console_learning_loop_and_outcomes(client):
    _login(client, "sara")
    client.get("/api/me/goals")             # the candidate is shown
    _login(client, "advisor")
    o = client.get("/api/ecosystem/overview").json()
    assert o["learning"] and o["rules"]
    row = next(r for r in o["learning"] if r["playbook_id"] == "get_paid")
    assert row["shown"] >= 1 and 0 <= row["hit_rate"] <= 1
    assert set(o["outcomes"]) >= {"verified", "pending", "not_met", "verified_eur"}
