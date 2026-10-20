"""Synthetic data sanity checks (DESIGN.md §6.1)."""
from __future__ import annotations

import json
import sqlite3

import pytest

from app.schemas import CATEGORIES
from synth.generate import TODAY, build

ALL_SCENARIOS = {"student", "young_family", "freelancer", "retiree", "young_professional",
                 "insurance_renewal", "price_increase", "duplicate_charge", "cashflow_squeeze", "idle_cash"}


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("db") / "kbc_test.db")
    summary = build(path, n=30, seed=7, verbose=False)
    assert summary["customers"] == 33
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def rows(conn, sql, *args):
    return [dict(r) for r in conn.execute(sql, args)]


def test_every_scenario_is_present(conn):
    seen: set[str] = set()
    for r in rows(conn, "SELECT ground_truth FROM customers"):
        gt = json.loads(r["ground_truth"])
        seen.update(gt["personas"])
        seen.update(e["type"] for e in gt["events"])
    missing = ALL_SCENARIOS - seen
    assert not missing, f"scenarios never injected: {missing}"


def test_all_categories_are_allowed(conn):
    used = {r["category"] for r in rows(conn, "SELECT DISTINCT category FROM transactions")}
    assert used <= set(CATEGORIES)
    assert len(used) >= 20


def test_all_dates_end_today(conn):
    hi = rows(conn, "SELECT MAX(date) AS d FROM transactions")[0]["d"]
    assert hi <= TODAY.isoformat()


def test_sara_car_insurance_renews_in_12_days(conn):
    r = rows(conn, "SELECT amount, counterparty FROM transactions WHERE customer_id = 9002 "
                   "AND category = 'insurance_car' AND date = '2025-10-12'")
    assert r == [{"amount": -612.0, "counterparty": "AG Insurance"}]


def test_sara_netflix_price_increase(conn):
    r = rows(conn, "SELECT date, amount FROM transactions WHERE customer_id = 9002 AND counterparty = 'Netflix' "
                   "AND date >= '2026-08-01' ORDER BY date")
    assert [x["amount"] for x in r] == [-13.99, -17.99]


def test_sara_is_a_blend(conn):
    cats = {r["category"] for r in rows(conn, "SELECT DISTINCT category FROM transactions WHERE customer_id = 9002 "
                                              "AND date >= '2026-04-01'")}
    assert {"invoice_income", "vat_payment", "child_benefit", "childcare"} <= cats


def test_jan_duplicate_charge(conn):
    r = rows(conn, "SELECT COUNT(*) AS n FROM transactions WHERE customer_id = 9003 AND date = '2026-09-27' "
                   "AND counterparty = 'Colruyt' AND amount = -64.2")
    assert r[0]["n"] == 2


def test_jan_is_a_retiree_with_idle_cash(conn):
    assert rows(conn, "SELECT COUNT(*) AS n FROM transactions WHERE customer_id = 9003 AND category = 'pension'")[0]["n"] >= 70
    bal = rows(conn, "SELECT balance_today FROM accounts WHERE customer_id = 9003")[0]["balance_today"]
    products = json.loads(rows(conn, "SELECT products FROM customers WHERE id = 9003")[0]["products"])
    assert bal >= 12000 and "savings" not in products


def test_lotte_time_travel(conn):
    def n(cat, year):
        return rows(conn, "SELECT COUNT(*) AS n FROM transactions WHERE customer_id = 9001 AND category = ? "
                          "AND date LIKE ?", cat, f"{year}%")[0]["n"]
    assert n("student_income", 2019) > 0 and n("salary", 2019) == 0
    assert n("salary", 2023) == 13 and n("student_income", 2023) == 0   # 12 pay slips + December bonus
    assert n("child_benefit", 2025) == 12 and n("childcare", 2025) == 12
    assert n("invoice_income", 2026) > 0 and n("salary", 2026) == 0
    assert n("vat_payment", 2026) == 2
    first_invoice = rows(conn, "SELECT MIN(date) AS d FROM transactions WHERE customer_id = 9001 "
                               "AND category = 'invoice_income'")[0]["d"]
    assert first_invoice == "2026-01-15"


def test_demo_customers_have_living_costs_every_month(conn):
    for cid in (9001, 9002, 9003):
        months = rows(conn, "SELECT DISTINCT substr(date, 1, 7) AS ym FROM transactions WHERE customer_id = ?", cid)
        grocery_months = {r["ym"] for r in rows(conn, "SELECT DISTINCT substr(date, 1, 7) AS ym FROM transactions "
                                                       "WHERE customer_id = ? AND category = 'groceries'", cid)}
        assert len(months) >= 96
        assert {m["ym"] for m in months} == grocery_months


def test_users_and_roles(conn):
    users = {r["username"]: r for r in rows(conn, "SELECT username, role, customer_id FROM users")}
    assert users["lotte"]["customer_id"] == 9001
    assert users["sara"]["customer_id"] == 9002
    assert users["jan"]["customer_id"] == 9003
    assert users["advisor"]["role"] == "advisor" and users["advisor"]["customer_id"] is None
    assert users["c1"]["role"] == "customer" and users["c1"]["customer_id"] == 1


def test_regular_customers_are_consistent(conn):
    for r in rows(conn, "SELECT id, birth_year, products, ground_truth FROM customers WHERE id <= 30"):
        gt = json.loads(r["ground_truth"])
        products = json.loads(r["products"])
        age = TODAY.year - r["birth_year"]
        if "student" in gt["personas"]:
            assert 18 <= age <= 25
        if "retiree" in gt["personas"]:
            assert age >= 65
        for e in gt["events"]:
            if e["type"] == "insurance_renewal":
                assert "car_insurance" not in products
                assert e["counterparty"] != "KBC Verzekeringen"
            if e["type"] == "idle_cash":
                assert "savings" not in products
        assert rows(conn, "SELECT COUNT(*) AS n FROM transactions WHERE customer_id = ?", r["id"])[0]["n"] > 100


def test_deterministic(tmp_path):
    a = str(tmp_path / "a.db")
    b = str(tmp_path / "b.db")
    build(a, n=5, seed=3, verbose=False)
    build(b, n=5, seed=3, verbose=False)
    ca, cb = sqlite3.connect(a), sqlite3.connect(b)
    ta = ca.execute("SELECT date, amount, category, counterparty FROM transactions ORDER BY id").fetchall()
    tb = cb.execute("SELECT date, amount, category, counterparty FROM transactions ORDER BY id").fetchall()
    assert ta == tb
    ca.close(); cb.close()


def _balance_at(conn, cid: int, as_of: str) -> float:
    today = rows(conn, "SELECT balance_today AS b FROM accounts WHERE customer_id = ?", cid)[0]["b"]
    after = rows(conn, "SELECT COALESCE(SUM(amount), 0) AS s FROM transactions WHERE customer_id = ? AND date > ?",
                 cid, as_of)[0]["s"]
    return round(today - after, 2)


def test_lotte_balance_is_sane_in_every_era(conn):
    """The engine walks the balance back from balance_today; every era must land in its band."""
    expectations = {
        "2019-03-01": (100, 900),     # student
        "2019-11-20": (100, 400),     # student, deliberately tight month → runway card
        "2020-05-20": (100, 400),
        "2021-08-15": (300, 4500),    # just started working
        "2022-06-01": (1000, 4500),   # young professional with a mortgage
        "2024-04-01": (2000, 5000),   # young family
        "2026-09-30": (3000, 8000),   # freelancer
    }
    for as_of, (lo, hi) in expectations.items():
        b = _balance_at(conn, 9001, as_of)
        assert lo <= b <= hi, f"lotte @ {as_of}: {b} not in [{lo}, {hi}]"


def test_sara_and_jan_balances(conn):
    assert 3000 <= _balance_at(conn, 9002, "2026-09-30") <= 8000
    assert 2000 <= _balance_at(conn, 9002, "2020-01-01") <= 9000
    assert 12500 <= _balance_at(conn, 9003, "2026-09-30") <= 15000
    assert 12000 <= _balance_at(conn, 9003, "2024-09-30") <= 15500


def test_lotte_has_moments_in_every_era(conn):
    def amounts(cp, lo, hi):
        return [r["amount"] for r in rows(conn, "SELECT amount FROM transactions WHERE customer_id = 9001 "
                                                "AND counterparty = ? AND date BETWEEN ? AND ? ORDER BY date", cp, lo, hi)]
    assert amounts("Spotify Student", "2019-09-01", "2019-10-31") == [-4.99, -5.99]
    assert amounts("Alma 2 Leuven", "2020-02-20", "2020-02-29") == [-7.8, -7.8]
    assert amounts("Telenet", "2022-08-01", "2022-09-30") == [-52.0, -58.0]
    assert amounts("Basic-Fit", "2025-01-01", "2025-02-28") == [-24.99, -29.99]


def test_sara_q3_invoices_and_clients(conn):
    q3 = rows(conn, "SELECT SUM(amount) AS s FROM transactions WHERE customer_id = 9002 "
                    "AND category = 'invoice_income' AND date >= '2026-07-01'")[0]["s"]
    assert 8500 <= q3 <= 9500
    clients = rows(conn, "SELECT COUNT(DISTINCT counterparty) AS n FROM transactions WHERE customer_id = 9002 "
                         "AND category = 'invoice_income' AND date >= '2026-04-01'")[0]["n"]
    assert clients >= 5
    monthly = rows(conn, "SELECT SUM(amount) / 6.0 AS s FROM transactions WHERE customer_id = 9002 "
                         "AND category = 'invoice_income' AND date >= '2026-04-01'")[0]["s"]
    assert 2800 <= monthly <= 5000


def test_regular_customers_rarely_overdrawn(conn):
    n = rows(conn, "SELECT COUNT(*) AS n FROM accounts WHERE customer_id < 9000")[0]["n"]
    neg = rows(conn, "SELECT COUNT(*) AS n FROM accounts WHERE customer_id < 9000 AND balance_today < 0")[0]["n"]
    assert neg <= max(2, n * 0.08)


def _daily_path(conn, cid: int) -> dict[str, float]:
    today = rows(conn, "SELECT balance_today AS b FROM accounts WHERE customer_id = ?", cid)[0]["b"]
    by_day: dict[str, float] = {}
    for r in rows(conn, "SELECT date, amount FROM transactions WHERE customer_id = ?", cid):
        by_day[r["date"]] = by_day.get(r["date"], 0.0) + r["amount"]
    path, suffix = {}, 0.0
    for d in sorted(by_day, reverse=True):
        path[d] = round(today - suffix, 2)
        suffix += by_day[d]
    return path


def test_lotte_daily_balance_never_negative_and_family_era_in_band(conn):
    path = _daily_path(conn, 9001)
    assert min(path.values()) > 0
    family = [b for d, b in path.items() if "2024-06-01" <= d <= "2025-12-31"]
    assert min(family) >= 2000 and max(family) <= 8000
    freelance = [b for d, b in path.items() if "2026-01-01" <= d <= "2026-09-30"]
    assert min(freelance) >= 3000


def test_idle_cash_customers_clear_the_engine_threshold(conn):
    """Engine rule: balance > 6 × avg monthly total outflow (90 days, savings transfers excluded), no savings product."""
    for r in rows(conn, "SELECT id, products, ground_truth FROM customers"):
        gt = json.loads(r["ground_truth"])
        if not any(e["type"] == "idle_cash" for e in gt["events"]):
            continue
        bal = rows(conn, "SELECT balance_today AS b FROM accounts WHERE customer_id = ?", r["id"])[0]["b"]
        out = -rows(conn, "SELECT COALESCE(SUM(amount), 0) AS s FROM transactions WHERE customer_id = ? AND amount < 0 "
                          "AND category != 'savings_transfer' AND date > ?", r["id"],
                    (TODAY - __import__("datetime").timedelta(days=90)).isoformat())[0]["s"] / 3
        assert "savings" not in json.loads(r["products"])
        assert bal >= 8 * out, f"customer {r['id']}: {bal} < 8 x {out}"
        assert bal >= 6 * out + 2000
