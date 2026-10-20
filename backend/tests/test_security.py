"""Regression tests for the Aikido findings: limiter bounds and atomicity, login enumeration and lockout,
Host header validation, snapshot growth, restricted transactions and hidden tiles."""
from __future__ import annotations

import datetime as dt
import threading

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import auth, db
from app.customer_state import storage
from app.customer_state.models import TransactionDetails
from app.customer_state.service import get_state
from app.customer_state.storage import put_details
from synth.customer_state import IDS, SCENARIO_TODAY as TODAY, seed


@pytest.fixture
def conn():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    seed(conn, users=True)
    yield conn
    conn.close()


@pytest.fixture
def fresh_limiters(monkeypatch):
    monkeypatch.setattr(auth, "_login_by_ip_user", auth.SlidingWindowLimiter(auth.LOGIN_MAX_ATTEMPTS, 900))
    monkeypatch.setattr(auth, "_login_by_ip", auth.SlidingWindowLimiter(auth.LOGIN_MAX_ATTEMPTS_PER_IP, 900))


def test_limiter_is_atomic_under_concurrency():
    limiter = auth.SlidingWindowLimiter(10, 60)
    barrier = threading.Barrier(50)
    results = []

    def worker():
        barrier.wait()
        results.append(limiter.hit("user"))

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(r is not None for r in results) == 10


def test_limiter_memory_is_bounded():
    limiter = auth.SlidingWindowLimiter(10, 900, max_keys=10_000)
    for i in range(100_000):
        limiter.hit(("1.2.3.4", f"user{i}"))
    assert len(limiter) <= 10_000


def test_failed_logins_from_one_ip_do_not_lock_out_another(conn, fresh_limiters):
    for _ in range(auth.LOGIN_MAX_ATTEMPTS):
        with pytest.raises(HTTPException) as e:
            auth.authenticate(conn, "state_stable", "wrong", "10.0.0.1")
        assert e.value.status_code == 401
    with pytest.raises(HTTPException) as e:
        auth.authenticate(conn, "state_stable", "demo", "10.0.0.1")
    assert e.value.status_code == 429
    assert auth.authenticate(conn, "state_stable", "demo", "10.0.0.2")["username"] == "state_stable"


def test_successful_logins_do_not_count(conn, fresh_limiters):
    for _ in range(auth.LOGIN_MAX_ATTEMPTS * 2):
        auth.authenticate(conn, "state_stable", "demo", "10.0.0.3")


def test_unknown_user_runs_a_full_password_verify(conn, fresh_limiters, monkeypatch):
    calls = []
    real = auth.verify_password
    monkeypatch.setattr(auth, "verify_password", lambda pw, stored: calls.append(stored) or real(pw, stored))
    errors = []
    for username in ("nobody_here", "state_stable"):
        with pytest.raises(HTTPException) as e:
            auth.authenticate(conn, username, "wrong", "10.0.0.4")
        errors.append((e.value.status_code, e.value.detail))
    assert len(calls) == 2 and calls[0] == auth._DUMMY_HASH
    assert errors[0] == errors[1]


def test_untrusted_host_header_is_rejected():
    from app.main import app
    with TestClient(app) as client:
        assert client.get("/api/me/session", headers={"Host": "evil.com"}).status_code == 400
        assert client.get("/api/me/session", headers={"Host": "evil.com/api/login?x="}).status_code == 400
        assert client.get("/api/me/session").status_code == 401  # allowed host reaches the app


def test_snapshots_per_customer_are_capped(conn, monkeypatch):
    monkeypatch.setattr(storage, "MAX_SNAPSHOTS_PER_CUSTOMER", 3)
    for days in range(5):
        get_state(conn, IDS["stable"], TODAY - dt.timedelta(days=days), balance_reference=TODAY)
    count = conn.execute("SELECT COUNT(*) FROM customer_state_snapshots WHERE customer_id=?",
                         (IDS["stable"],)).fetchone()[0]
    assert count == 3


def test_snapshot_dates_before_history_are_clamped(tmp_path, monkeypatch):
    path = str(tmp_path / "state.db")
    monkeypatch.setattr(db, "DB_PATH", path)
    with db.tx(path) as c:
        db.init_schema(c)
        seed(c, users=True)
    from app.main import app
    with TestClient(app) as client:
        assert client.post("/api/login", json={"username": "state_stable", "password": "demo"}).status_code == 200
        a = client.get("/api/me/customer-state?as_of=1900-01-01").json()["as_of"]
        b = client.get("/api/me/customer-state?as_of=1950-06-01").json()["as_of"]
    assert a == b
    with db.tx(path) as c:
        lo = db.date_range(c, IDS["stable"])[0]
    assert a == lo.isoformat()


def test_restricted_transactions_do_not_change_the_profile(conn):
    cid = IDS["stable"]
    before = get_state(conn, cid, TODAY, balance_reference=TODAY)
    tid = conn.execute("SELECT MAX(id)+1 FROM transactions").fetchone()[0]
    from app.schemas import Transaction
    db.insert_transactions(conn, [Transaction(id=tid, customer_id=cid, date=TODAY - dt.timedelta(days=40),
                                              amount=-900, category="leisure", counterparty="Private clinic")])
    put_details(conn, tid, TransactionDetails(sensitive=True))
    after = get_state(conn, cid, TODAY, balance_reference=TODAY)
    assert after.spending.category_metrics == before.spending.category_metrics
    assert after.spending.top_categories == before.spending.top_categories
    assert after.spending.top_merchants == before.spending.top_merchants
    assert all(tid not in c.evidence.transaction_ids for c in after.changes)


def test_rate_limited_responses_carry_retry_after(conn, fresh_limiters):
    for _ in range(auth.LOGIN_MAX_ATTEMPTS):
        with pytest.raises(HTTPException):
            auth.authenticate(conn, "state_stable", "wrong", "10.0.0.5")
    with pytest.raises(HTTPException) as e:
        auth.authenticate(conn, "state_stable", "wrong", "10.0.0.5")
    assert e.value.status_code == 429
    assert 1 <= int(e.value.headers["Retry-After"]) <= 15 * 60 + 1


def test_kate_limit_is_exact_under_concurrency_and_sets_retry_after(monkeypatch):
    from app import main
    monkeypatch.setattr(main, "_kate_limiter", auth.SlidingWindowLimiter(10, 60))
    barrier = threading.Barrier(50)
    outcomes = []

    def worker():
        barrier.wait()
        try:
            main._kate_rate_limit(42)
            outcomes.append(200)
        except HTTPException as e:
            outcomes.append(e.headers["Retry-After"] and e.status_code)

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert outcomes.count(200) == 10 and outcomes.count(429) == 40
