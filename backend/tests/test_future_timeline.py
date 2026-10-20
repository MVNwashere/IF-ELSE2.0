"""Lotte's simulated life timeline after today: served in memory, never stored, today's view unchanged."""
from __future__ import annotations

import datetime as dt
import os

import pytest
from fastapi.testclient import TestClient

from app import db as dbmod
from synth.demo_customers import lotte_future_chapters, lotte_future_transactions

TODAY = dt.date(2026, 10, 20)


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("db") / "kbc_future.db")
    os.environ["KBC_DB_PATH"] = path
    os.environ["DEMO_PASSWORD"] = "demo"
    dbmod.DB_PATH = path
    from synth.generate import build

    build(path, n=5, seed=7, verbose=False)
    from app.main import app

    with TestClient(app) as c:
        yield c


def _login(client: TestClient, username: str):
    client.cookies.clear()
    assert client.post("/api/login", json={"username": username, "password": "demo"}).status_code == 200


def test_future_is_not_stored(client):
    with dbmod.tx() as conn:
        lo, hi = dbmod.date_range(conn, 9001)
    assert hi <= TODAY
    assert all(t.date > TODAY for t in lotte_future_transactions())


def test_today_balance_unchanged_by_the_overlay(client):
    with dbmod.tx() as conn:
        txs = dbmod.get_transactions(conn, 9001)
        end = dbmod.get_balance_today(conn, 9001)
        stored = conn.execute("SELECT balance_today FROM accounts WHERE customer_id = 9001").fetchone()[0]
    from app.engine.features import balance_at
    assert balance_at(txs, end, TODAY) == pytest.approx(stored, abs=0.01)


def test_default_is_today_and_future_is_reachable(client):
    _login(client, "lotte")
    assert client.get("/api/me/home").json()["as_of"] == TODAY.isoformat()
    tl = client.get("/api/me/timeline").json()
    assert tl["today"] == TODAY.isoformat() and tl["max_date"] > TODAY.isoformat()
    assert sum(m["label"].startswith("Simulated") for m in tl["milestones"]) == len(lotte_future_chapters())
    goals = client.get("/api/me/goals?as_of=2027-12-01").json()
    assert "first_employee" in [c["playbook_id"] for c in goals["candidates"]]


def test_other_customers_have_no_future(client):
    _login(client, "sara")
    tl = client.get("/api/me/timeline").json()
    assert tl["max_date"] == TODAY.isoformat()
    assert client.get("/api/me/home?as_of=2028-01-01").json()["as_of"] == TODAY.isoformat()
