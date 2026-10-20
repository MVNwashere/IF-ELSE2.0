"""The customer profile: facts, corrections and permissions, validated, audited and actually used by the engine."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app import db as dbmod


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("db") / "kbc_profile.db")
    os.environ["KBC_DB_PATH"] = path
    os.environ["DEMO_PASSWORD"] = "demo"
    dbmod.DB_PATH = path
    from synth.generate import build

    build(path, n=20, seed=7)
    from app.main import app

    with TestClient(app) as c:
        yield c


def _as(client: TestClient, username: str) -> None:
    client.cookies.clear()
    assert client.post("/api/login", json={"username": username, "password": "demo"}).status_code == 200


def _field(profile: dict, key: str) -> dict:
    return next(f for f in profile["fields"] if f["key"] == key)


def _audit(action_prefix: str) -> list[str]:
    with dbmod.tx() as conn:
        return [r["action"] for r in conn.execute("SELECT action FROM audit_log WHERE action LIKE ?",
                                                  (action_prefix + "%",))]


def test_profile_shows_three_layers(client):
    _as(client, "sara")
    p = client.get("/api/me/profile").json()
    assert p["first_name"] == "Sara"
    assert {f["key"] for f in p["fields"]} >= {"children", "employment", "avoid_topics"}
    assert p["personas"] and all(x["evidence"] for x in p["personas"])
    assert {x["purpose"] for x in p["permissions"]} == {"personalise_offers", "detect_life_events", "kate_memory",
                                                       "kate_ai", "advisor_view"}
    # sending data to an external AI model is off until the customer says yes
    assert next(x for x in p["permissions"] if x["purpose"] == "kate_ai")["allowed"] is False
    assert "partners_with_access" in p["data_access"]


def test_fact_roundtrip_changes_persona_and_is_audited(client):
    _as(client, "jan")
    p = client.put("/api/me/profile/facts/children", json={"value": 2}).json()
    f = _field(p, "children")
    assert (f["value"], f["value_label"], f["source"]) == (2, "2 children", "you")
    fam = next(x for x in p["personas"] if x["persona"] == "young_family")
    assert fam["from_you"] and any("You told us you have 2 children" in e for e in fam["evidence"])
    home = client.get("/api/me/home").json()
    assert any(x["persona"] == "young_family" for x in home["persona_mix"])
    p = client.delete("/api/me/profile/facts/children").json()
    assert _field(p, "children")["value"] is None
    assert "profile.fact.set.you" in _audit("profile.fact") and "profile.fact.delete" in _audit("profile.fact")


def test_fact_validation(client):
    _as(client, "jan")
    bad = [("children", 99), ("children", "two"), ("children", True), ("employment", "astronaut"),
           ("avoid_topics", ["investing", "gambling"]), ("cares_for_relative", 1)]
    for key, value in bad:
        assert client.put(f"/api/me/profile/facts/{key}", json={"value": value}).status_code == 422, (key, value)
    assert client.put("/api/me/profile/facts/health", json={"value": "x"}).status_code == 422
    assert client.put("/api/me/profile/facts/children", json={"value": "<script>"}).status_code == 422
    p = client.put("/api/me/profile/facts/avoid_topics", json={"value": ["insurance", "investing", "investing"]}).json()
    assert _field(p, "avoid_topics")["value"] == ["insurance", "investing"]
    client.delete("/api/me/profile/facts/avoid_topics")


def test_kate_memory_off_blocks_saves_from_kate(client):
    _as(client, "jan")
    client.put("/api/me/profile/permissions/kate_memory", json={"allowed": False})
    assert client.put("/api/me/profile/facts/housing", json={"value": "renting", "via": "kate"}).status_code == 403
    assert client.put("/api/me/profile/facts/housing", json={"value": "renting"}).status_code == 200   # the form still works
    client.put("/api/me/profile/permissions/kate_memory", json={"allowed": True})
    client.put("/api/me/profile/facts/partner", json={"value": "married", "via": "kate"})
    p = client.post("/api/me/profile/forget-kate").json()
    assert _field(p, "partner")["value"] is None and _field(p, "housing")["value"] == "renting"
    client.delete("/api/me/profile/facts/housing")


def test_persona_correction_removes_it_until_undone(client):
    _as(client, "jan")
    home = client.get("/api/me/home").json()
    top = home["persona_mix"][0]["persona"]
    p = client.post("/api/me/profile/corrections", json={"kind": "persona", "target": top}).json()
    assert top not in {x["persona"] for x in p["personas"]}
    assert p["corrections"][0]["label"].startswith("Not ")
    assert top not in {x["persona"] for x in client.get("/api/me/home").json()["persona_mix"]}
    p = client.post("/api/me/profile/corrections", json={"kind": "persona", "target": top, "state": "clear"}).json()
    assert top in {x["persona"] for x in p["personas"]} and not p["corrections"]
    assert client.post("/api/me/profile/corrections", json={"kind": "persona", "target": "astronaut"}).status_code == 422
    assert client.post("/api/me/profile/corrections", json={"kind": "goal", "target": "../x"}).status_code == 422


def test_life_event_detection_permission_and_goal_corrections(client):
    _as(client, "lotte")
    goals = client.get("/api/me/goals").json()["candidates"]
    assert goals, "Lotte's demo data should suggest at least one goal"
    first = goals[0]["playbook_id"]
    p = client.post("/api/me/profile/corrections", json={"kind": "goal", "target": first}).json()
    assert first not in {g["playbook_id"] for g in p["goals"]}
    assert first not in {c["playbook_id"] for c in client.get("/api/me/goals").json()["candidates"]}
    client.post("/api/me/profile/corrections", json={"kind": "goal", "target": first, "state": "clear"})

    client.put("/api/me/profile/permissions/detect_life_events", json={"allowed": False})
    assert client.get("/api/me/goals").json()["candidates"] == []
    assert client.get("/api/me/profile").json()["goals"] == []
    client.put("/api/me/profile/permissions/detect_life_events", json={"allowed": True})
    assert client.get("/api/me/goals").json()["candidates"]


def test_personalise_offers_is_the_existing_consent(client):
    _as(client, "sara")
    client.put("/api/me/profile/permissions/personalise_offers", json={"allowed": False})
    home = client.get("/api/me/home").json()
    assert home["customer"]["consent_personalization"] is False
    assert not any(c["commercial"] for c in home["feed"]["cards"])
    client.post("/api/me/consent", json={"consent_personalization": True})
    p = client.get("/api/me/profile").json()
    assert next(x for x in p["permissions"] if x["purpose"] == "personalise_offers")["allowed"] is True


def test_profile_is_session_bound(client):
    _as(client, "sara")
    client.put("/api/me/profile/facts/risk_appetite", json={"value": "careful"})
    _as(client, "jan")
    assert _field(client.get("/api/me/profile").json(), "risk_appetite")["value"] is None
    client.cookies.clear()
    assert client.get("/api/me/profile").status_code == 401
    assert client.put("/api/me/profile/facts/children", json={"value": 1}).status_code == 401
    _as(client, "sara")
    client.delete("/api/me/profile/facts/risk_appetite")


def test_advisor_sees_profile_only_with_permission(client):
    _as(client, "sara")
    client.put("/api/me/profile/permissions/advisor_view", json={"allowed": False})
    assert client.get("/api/advisor/profile/sara").status_code == 403    # a customer is not an advisor
    _as(client, "advisor")
    assert client.get("/api/advisor/profile/sara").status_code == 403
    assert "advisor.profile.denied" in _audit("advisor.profile")
    assert client.get("/api/advisor/profile/nobody_here").status_code == 404
    _as(client, "sara")
    client.put("/api/me/profile/permissions/advisor_view", json={"allowed": True})
    _as(client, "advisor")
    r = client.get("/api/advisor/profile/sara")
    assert r.status_code == 200 and r.json()["first_name"] == "Sara"


def test_avoided_topics_hold_back_offers(client):
    from app.profile.fields import offer_topics
    _as(client, "sara")
    before = client.get("/api/me/home").json()["feed"]
    assert any("investing" in offer_topics(c["title"]) for c in before["cards"]), "fixture: Sara sees an investing tip"
    client.put("/api/me/profile/facts/avoid_topics", json={"value": ["investing"]})
    after = client.get("/api/me/home").json()["feed"]
    assert not any("investing" in offer_topics(c["title"]) and not c["card_type"].startswith("core_")
                   for c in after["cards"])
    assert after["hidden_count"] > before["hidden_count"]
    client.delete("/api/me/profile/facts/avoid_topics")


def test_kate_proposes_profile_save_and_never_writes(client):
    _as(client, "jan")
    client.put("/api/me/profile/permissions/kate_memory", json={"allowed": True})
    r = client.post("/api/me/kate", json={"message": "We have three kids, by the way"}).json()
    a = next(a for a in r["actions"] if a["kind"] == "update_profile")
    assert (a["fact_key"], a["fact_value"]) == ("children", 3)
    assert _field(client.get("/api/me/profile").json(), "children")["value"] is None   # proposal only
    r = client.post("/api/me/kate", json={"message": "What do you know about me?"}).json()
    assert r["actions"][0]["kind"] == "open_profile" and "transactions" in r["reply"]
    r = client.post("/api/me/kate", json={"message": "Who has my data?"}).json()
    assert r["actions"][0]["kind"] == "open_passport"
