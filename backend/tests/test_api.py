"""API tests: auth, IDOR isolation, validation, feedback loop, as_of clamping."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app import db as dbmod


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("db") / "kbc_test.db")
    os.environ["KBC_DB_PATH"] = path
    os.environ["DEMO_PASSWORD"] = "demo"
    dbmod.DB_PATH = path
    from synth.generate import build

    build(path, n=20, seed=7)
    from app.main import app

    with TestClient(app) as c:
        yield c


def _login(client: TestClient, username: str, password: str = "demo"):
    return client.post("/api/login", json={"username": username, "password": password})


def test_home_requires_login(client):
    client.cookies.clear()
    assert client.get("/api/me/home").status_code == 401


def test_bad_password_rejected(client):
    client.cookies.clear()
    assert _login(client, "sara", "wrong").status_code == 401


def test_login_validation(client):
    client.cookies.clear()
    r = client.post("/api/login", json={"username": "Sara; DROP TABLE users", "password": "demo"})
    assert r.status_code == 422


def test_home_is_session_bound(client):
    client.cookies.clear()
    assert _login(client, "sara").status_code == 200
    sara = client.get("/api/me/home").json()
    assert sara["customer"]["first_name"] == "Sara"
    assert "ground_truth" not in str(sara)
    # No way to ask for another customer: there is no customer id parameter at all
    assert client.get("/api/me/home?customer_id=9003").json()["customer"]["first_name"] == "Sara"

    client.cookies.clear()
    assert _login(client, "jan").status_code == 200
    jan = client.get("/api/me/home").json()
    assert jan["customer"]["first_name"] == "Jan"


def test_home_response_shape(client):
    client.cookies.clear()
    _login(client, "sara")
    home = client.get("/api/me/home").json()
    assert home["layout"]["sections"][0]["size"] == "hero"
    assert home["layout"]["sections"][1]["component"] == "ForYouFeed"
    assert abs(sum(p["weight"] for p in home["persona_mix"]) - 1) < 1e-6
    assert len(home["feed"]["cards"]) <= 7


def test_as_of_is_clamped(client):
    client.cookies.clear()
    _login(client, "sara")
    r = client.get("/api/me/home?as_of=2099-01-01")
    assert r.status_code == 200
    assert r.json()["as_of"] <= "2026-09-30"
    assert client.get("/api/me/home?as_of=not-a-date").status_code == 422


def test_timeline(client):
    client.cookies.clear()
    _login(client, "lotte")
    tl = client.get("/api/me/timeline").json()
    assert tl["min_date"] < tl["max_date"]
    assert len(tl["milestones"]) >= 3


def test_feedback_changes_feed(client):
    client.cookies.clear()
    _login(client, "sara")
    home = client.get("/api/me/home").json()
    assert home["feed"]["cards"], "sara should have cards"
    first = home["feed"]["cards"][0]
    after = client.post("/api/me/feedback",
                        json={"card_key": first["card_key"], "card_type": first["card_type"],
                              "decision": "dismiss"}).json()
    assert all(c["card_key"] != first["card_key"] for c in after["feed"]["cards"])
    reset = client.post("/api/me/feedback",
                        json={"card_key": "reset", "card_type": first["card_type"], "decision": "reset"}).json()
    assert any(c["card_key"] == first["card_key"] for c in reset["feed"]["cards"])


def test_home_feed_uses_customer_state_and_catalogue(client):
    client.cookies.clear()
    _login(client, "sara")
    home = client.get("/api/me/home").json()
    assert {p["code"] for p in home["feed_personas"]} >= {"PAR", "SELF"}
    assert any(c["card_type"] == "core_money" for c in home["feed"]["cards"])
    assert any(c["card_type"].startswith("catalog_") for c in home["feed"]["cards"])
    assert all(c["details"].get("related_cards") is not None for c in home["feed"]["cards"])


def test_feed_personas_follow_history_without_future_products(client):
    client.cookies.clear()
    _login(client, "lotte")
    student = client.get("/api/me/home?as_of=2018-09-30").json()
    freelancer = client.get("/api/me/home?as_of=2026-09-30").json()
    assert student["feed_personas"][0]["code"] == "STU"
    assert freelancer["feed_personas"][0]["code"] == "SELF"
    assert "STU" not in {p["code"] for p in freelancer["feed_personas"]}


def test_feedback_validation(client):
    client.cookies.clear()
    _login(client, "sara")
    r = client.post("/api/me/feedback", json={"card_key": "<script>", "card_type": "runway", "decision": "dismiss"})
    assert r.status_code == 422
    r = client.post("/api/me/feedback", json={"card_key": "x", "card_type": "runway", "decision": "delete_all"})
    assert r.status_code == 422
    r = client.post("/api/me/feedback", json={"card_key": "x", "card_type": "not_a_card", "decision": "dismiss"})
    assert r.status_code == 422


def test_layout_pref_hides_component(client):
    client.cookies.clear()
    _login(client, "sara")
    home = client.get("/api/me/home").json()
    halves = [s["component"] for s in home["layout"]["sections"] if s["size"] == "half"]
    if not halves:
        pytest.skip("no half-size components to hide")
    target = halves[0]
    after = client.post("/api/me/layout-prefs", json={"component": target, "state": "hidden"}).json()
    assert target not in [s["component"] for s in after["layout"]["sections"]]
    client.post("/api/me/layout-prefs", json={"component": target, "state": "reset"})
    r = client.post("/api/me/layout-prefs", json={"component": "EvilComponent", "state": "pinned"})
    assert r.status_code == 422


def test_consent_gates_commercial(client):
    client.cookies.clear()
    _login(client, "sara")
    off = client.post("/api/me/consent", json={"consent_personalization": False}).json()
    assert not any(c["commercial"] for c in off["feed"]["cards"])
    on = client.post("/api/me/consent", json={"consent_personalization": True}).json()
    assert on["customer"]["consent_personalization"] is True


def test_advisor_role_enforced(client):
    client.cookies.clear()
    _login(client, "sara")
    assert client.get("/api/advisor/overview").status_code == 403
    client.cookies.clear()
    _login(client, "advisor")
    assert client.get("/api/me/home").status_code == 403
    r = client.get("/api/advisor/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["customers_scored"] >= 20
    assert body["projected_2_3m_seconds"] > 0


def test_security_headers(client):
    client.cookies.clear()
    r = client.post("/api/logout")
    assert "Content-Security-Policy" in r.headers
    assert r.headers["X-Frame-Options"] == "DENY"


# ---- v2: customisation, suggestions, declared signals, Kate ------------------------


def _as(client: TestClient, username: str) -> None:
    client.cookies.clear()
    assert _login(client, username).status_code == 200
    client.post("/api/me/layout-reset")
    client.post("/api/me/style", json={})


def test_pin_at_position_survives_time_travel(client):
    _as(client, "lotte")
    h = client.post("/api/me/layout-prefs", json={"component": "ScamShield", "state": "pinned", "position": 1}).json()
    comps = [s["component"] for s in h["layout"]["sections"]]
    assert comps[3] == "ScamShield"
    for day in ["2019-03-01", "2022-06-01", "2024-06-01"]:
        comps = [s["component"] for s in client.get(f"/api/me/home?as_of={day}").json()["layout"]["sections"]]
        assert comps[3] == "ScamShield", day
    client.post("/api/me/layout-reset")


def test_only_one_pinned_hero(client):
    _as(client, "sara")
    client.post("/api/me/layout-prefs", json={"component": "BalanceHero", "state": "pinned"})
    h = client.post("/api/me/layout-prefs", json={"component": "PensionHero", "state": "pinned"}).json()
    assert h["layout"]["sections"][0]["component"] == "PensionHero"
    assert sum(s["pinned"] for s in h["layout"]["sections"] if s["size"] == "hero") == 1
    client.post("/api/me/layout-reset")


def test_style_roundtrip_and_validation(client):
    _as(client, "jan")
    h = client.post("/api/me/style", json={"density": "compact", "appearance": "dark", "accent": "teal"}).json()
    assert h["layout"]["theme"]["density"] == "compact" and h["layout"]["theme"]["appearance"] == "dark"
    assert h["style"]["accent"] == "teal"
    assert client.post("/api/me/style", json={"accent": "#ff0000"}).status_code == 422
    h = client.post("/api/me/style", json={}).json()
    assert h["layout"]["theme"]["density"] == "large" and h["layout"]["theme"]["overrides"] == []


def test_suggestion_accept_pins_and_dismiss_hides(client):
    _as(client, "sara")
    h = client.post("/api/me/suggestion", json={"component": "SplitBills", "decision": "accept"}).json()
    assert any(s["component"] == "SplitBills" and s["pinned"] for s in h["layout"]["sections"])
    client.post("/api/me/suggestion", json={"component": "ScamShield", "decision": "dismiss"})
    assert client.post("/api/me/suggestion", json={"component": "Nope", "decision": "accept"}).status_code == 422
    client.post("/api/me/layout-reset")


def test_declared_signal_shifts_persona_and_can_be_cleared(client):
    _as(client, "jan")
    before = {p["persona"]: p["weight"] for p in client.get("/api/me/home").json()["persona_mix"]}
    h = client.post("/api/me/declare", json={"signal": "going_freelance", "state": "set"}).json()
    after = {p["persona"]: p["weight"] for p in h["persona_mix"]}
    assert after.get("freelancer", 0) > before.get("freelancer", 0)
    assert any("You told Kate" in e for p in h["persona_mix"] for e in p["evidence"])
    h = client.post("/api/me/declare", json={"signal": "going_freelance", "state": "clear"}).json()
    assert {p["persona"]: p["weight"] for p in h["persona_mix"]} == before


def test_kate_opener_card_and_actions(client):
    _as(client, "sara")
    home = client.get("/api/me/home").json()
    r = client.post("/api/me/kate", json={"message": ""}).json()
    assert r["reply"].startswith("Hi Sara") or "Sara" in r["reply"]
    card = home["feed"]["cards"][0]
    r = client.post("/api/me/kate", json={"message": "Why am I seeing this?", "card_key": card["card_key"]}).json()
    assert card["evidence"][0][:20] in r["reply"]
    r = client.post("/api/me/kate", json={"message": "Can you make the text bigger?"}).json()
    assert r["actions"][0]["kind"] == "set_style" and r["actions"][0]["style"]["density"] == "large"
    # Kate only proposes: nothing changed
    assert client.get("/api/me/home").json()["layout"]["theme"]["overrides"] == []


def test_kate_validation_and_isolation(client):
    _as(client, "sara")
    assert client.post("/api/me/kate", json={"message": "x" * 501}).status_code == 422
    assert client.post("/api/me/kate", json={"message": "hi", "card_key": "../etc"}).status_code == 422
    client.cookies.clear()
    assert client.post("/api/me/kate", json={"message": "hi"}).status_code == 401
