"""Numerical scenario, temporal isolation, source correction and API ownership tests."""
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth import hash_password
from app.customer_state.models import AccountObservation, TransactionDetails
from app.customer_state.normalization import normalize
from app.customer_state.patterns import detect
from app.customer_state.service import get_state
from app.customer_state.storage import put_account, put_details
from app.schemas import Customer, Transaction
from synth.customer_state import IDS, seed
from synth.generate import TODAY, make_regular


@pytest.fixture
def conn():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    seed(conn)
    yield conn
    conn.close()


def state(conn, scenario="stable", as_of=TODAY):
    return get_state(conn, IDS[scenario], as_of, balance_reference=TODAY)


def test_stable_salary_and_exact_financial_totals(conn):
    s = state(conn)
    assert s.income.estimated_monthly_income == 3000
    assert s.income.income_stability == 1
    assert s.income.income_sources == 1
    assert s.income.income_trend == "stable"
    assert s.income.next_expected_income_date == dt.date(2026, 10, 25)
    assert s.income.next_expected_income_amount == 3000
    assert s.expenses.average_monthly_expenses == 1662
    assert s.expenses.average_fixed_expenses == 1062
    assert s.expenses.average_variable_expenses == 600
    assert s.expenses.average_discretionary_expenses == 212
    assert s.expenses.average_essential_expenses == 1450
    assert s.cash_flow.average_monthly_free_cash_flow == 1338
    assert s.financial_position.current_balance == 4542
    assert s.financial_position.total_liquid_balance == 18542
    assert s.savings.balance == 14000
    assert s.savings.average_monthly_savings == 1000
    assert s.savings.savings_rate == .3333
    assert s.spending.category_metrics["groceries"]["monthly_average"] == 400
    assert s.cash_flow.expected_7_day_balance == pytest.approx(4542-900-3600/183*7, abs=.01)
    assert s.cash_flow.expected_30_day_balance == pytest.approx(4542+3000-900-140-12-1000-3600/183*30, abs=.01)
    assert any(i.type == "LIKELY_RECURRING_SALARY" and i.confidence < 1 for i in s.inferences)


def test_variable_income_multiple_sources(conn):
    s = state(conn, "variable")
    assert s.income.income_sources == 3
    assert s.income.estimated_monthly_income == 3400
    assert s.income.income_stability < .7
    assert any(p.entity == "side client" and p.type == "RECURRING_INCOME" for p in s.patterns)
    assert not any(i.type == "LIKELY_RECURRING_SALARY" for i in s.inferences)


def test_salary_increase_history_and_evidence(conn):
    s = state(conn, "salary_increase")
    changes = [c for c in s.changes if c.type == "SALARY_CHANGED"]
    assert len(changes) == 1
    assert (changes[0].previous_value, changes[0].current_value, changes[0].change_pct) == (3000, 3600, .2)
    assert changes[0].evidence.transaction_ids
    assert s.income.income_trend == "increasing"
    assert s.income.next_expected_income_amount == 3600
    before = state(conn, "salary_increase", dt.date(2026, 7, 31))
    assert before.income.estimated_monthly_income == 3000
    assert not any(c.type == "SALARY_CHANGED" for c in before.changes)
    assert all(t.date <= before.as_of for t in before.observations.transactions)


def test_subscriptions_and_price_changes(conn):
    s = state(conn, "subscriptions")
    assert s.subscriptions.count == 6
    assert s.subscriptions.monthly_total == 65
    assert s.recurring_payments.count == 10
    change = next(c for c in s.changes if c.type == "SUBSCRIPTION_PRICE_CHANGED")
    assert change.current_value == 15 and change.previous_value == 12
    assert any(o.type == "SUBSCRIPTION_COST_INCREASE" for o in s.opportunities)


def test_discretionary_spending_growth(conn):
    s = state(conn, "spending_increase")
    assert s.expenses.average_discretionary_expenses == 362
    assert s.spending.category_metrics["leisure"]["trend"] == "increasing"
    assert any(c.type == "CATEGORY_SPENDING_INCREASED" and c.entity == "leisure" for c in s.changes)


def test_declining_cash_buffer(conn):
    before = state(conn, "declining_buffer", dt.date(2026, 6, 30))
    after = state(conn, "declining_buffer")
    assert after.cash_flow.cash_buffer_months < before.cash_flow.cash_buffer_months
    assert any(c.type == "CASH_BUFFER_CHANGED" and c.current_value < c.previous_value for c in after.changes)
    assert any(c.type == "MONTHLY_CASH_FLOW_CHANGED" for c in after.changes)


def test_increasing_savings(conn):
    s = state(conn, "growing_savings")
    assert s.savings.balance == 9500
    assert s.savings.average_monthly_savings == 650
    assert s.savings.trend == "increasing"
    assert s.savings.savings_rate == .2167
    assert any(c.type == "SAVINGS_BEHAVIOR_CHANGED" for c in s.changes)


def test_debt_principal_and_interest_are_not_conflated(conn):
    s = state(conn, "debt")
    assert s.debt.total_known_debt == 184150
    assert s.debt.monthly_debt_service == 900
    assert s.debt.debt_service_ratio == .3
    assert s.debt.trend == "decreasing"
    assert s.financial_position.known_debt == 184150


def test_upcoming_low_balance_before_payday(conn):
    s = state(conn, "low_balance")
    assert s.financial_position.current_balance > 0
    assert s.cash_flow.lowest_projected_balance < 0
    assert s.cash_flow.liquidity_pressure == "high"
    risk = next(r for r in s.risks if r.type == "LOW_PROJECTED_BALANCE")
    assert risk.data["days_until_income"] == 25
    assert risk.evidence.pattern_ids


def test_foreign_currency_travel_and_unusual_expense(conn):
    s = state(conn, "foreign")
    assert s.freshness["excluded_non_eur_transaction_count"] == 1
    assert any(t.details.currency == "GBP" for t in s.observations.transactions)
    assert "NO_FX_CONVERSION" in s.observations.limitations
    assert any(e.type == "FOREIGN_SPENDING_APPEARED" for e in s.events)
    assert any(e.type == "UNUSUALLY_LARGE_TRANSACTION" and e.entity == "new furniture" for e in s.events)
    assert any(i.type == "POSSIBLE_RECENT_TRAVEL" and i.confidence == .6 for i in s.inferences)
    assert not any("UPCOMING_TRAVEL" in i.type for i in s.inferences)


def test_idempotence_correction_new_transaction_and_snapshot_history(conn):
    first = state(conn)
    assert state(conn).model_dump() == first.model_dump()
    conn.execute("UPDATE transactions SET amount=-120 WHERE customer_id=? AND date='2026-09-05'", (IDS["stable"],))
    second = state(conn)
    assert second.freshness["source_hash"] != first.freshness["source_hash"]
    assert second.expenses.average_monthly_expenses == 1665.33
    assert conn.execute("SELECT COUNT(*) FROM customer_state_snapshots").fetchone()[0] == 1
    assert len({c.id for c in second.changes}) == len(second.changes)
    state(conn, as_of=dt.date(2026, 8, 31))
    assert conn.execute("SELECT COUNT(*) FROM customer_state_snapshots").fetchone()[0] == 2
    tid = conn.execute("SELECT MAX(id)+1 FROM transactions").fetchone()[0]
    db.insert_transactions(conn, [Transaction(id=tid, customer_id=IDS["stable"], date=TODAY,
                                             amount=-600, category="furniture", counterparty="New shop")])
    third = state(conn)
    assert third.expenses.average_monthly_expenses == 1765.33


def test_sensitive_records_remain_raw_but_do_not_create_profile_attributes(conn):
    cid = IDS["stable"]
    ids = [r[0] for r in conn.execute("SELECT id FROM transactions WHERE customer_id=? AND category='subscription'", (cid,))]
    for tid in ids:
        conn.execute("UPDATE transactions SET counterparty='Sensitive merchant', category='healthcare' WHERE id=?", (tid,))
    s = state(conn)
    assert any(t.category == "healthcare" for t in s.observations.transactions)
    assert s.expenses.average_monthly_expenses == 1662
    assert all(x.entity is None and x.category == "other" for x in s.signals if x.transaction_id in ids)
    derived = str([s.patterns, s.inferences, s.changes, s.events, s.spending])
    assert "sensitive merchant" not in derived.lower()
    assert "healthcare" not in derived
    assert s.subscriptions.count == 0


def test_unknown_balances_empty_and_short_history(conn):
    db.insert_customer(conn, Customer(id=999, first_name="Empty", last_name="Customer", birth_year=1980, city="Gent"), 100)
    s = get_state(conn, 999, TODAY, balance_reference=TODAY)
    assert s.income.estimated_monthly_income is None
    assert s.savings.balance is None and s.debt.total_known_debt is None
    assert s.cash_flow.expected_30_day_balance is None
    assert s.patterns == [] and s.inferences == []
    assert s.income.income_stability is None
    with pytest.raises(LookupError):
        get_state(conn, 998, TODAY, balance_reference=TODAY)


def test_midmonth_excludes_partial_month_and_future_snapshots(conn):
    s = state(conn, as_of=dt.date(2026, 9, 10))
    assert s.cash_flow.monthly[-1]["month"] == "2026-08-01"
    assert all(a.observed_at <= s.as_of for a in s.observations.accounts)
    august = state(conn, as_of=dt.date(2026, 8, 31))
    assert s.financial_position.current_balance == august.financial_position.current_balance-1140
    before = state(conn, as_of=dt.date(2025, 1, 1))
    assert before.observations.transactions == []
    assert before.financial_position.current_balance is None


def test_disappeared_income_and_subscription_are_not_projected(conn):
    conn.execute("DELETE FROM transactions WHERE customer_id=? AND category IN ('salary','subscription') AND date>='2026-08-01'", (IDS["stable"],))
    s = state(conn)
    assert {"INCOME_DISAPPEARED", "SUBSCRIPTION_DISAPPEARED"} <= {c.type for c in s.changes}
    assert s.income.next_expected_income_date is None
    assert s.subscriptions.count == 0
    assert s.cash_flow.upcoming_inflows == []
    assert s.cash_flow.monthly[-1]["income"] == 0


def test_new_recurring_source_and_bill(conn):
    conn.execute("DELETE FROM transactions WHERE customer_id=? AND category IN ('salary','subscription','utilities') AND date<'2026-07-01'", (IDS["stable"],))
    s = state(conn)
    assert {"NEW_INCOME_SOURCE", "SUBSCRIPTION_APPEARED", "RECURRING_BILL_APPEARED"} <= {c.type for c in s.changes}


def test_existing_synthetic_data_adapter(conn):
    customer, txs, balance = make_regular(42, 7)
    next_id = conn.execute("SELECT MAX(id)+1 FROM transactions").fetchone()[0]
    for i, t in enumerate(txs):
        t.id = next_id+i
    db.insert_customer(conn, customer, balance)
    db.insert_transactions(conn, txs)
    s = get_state(conn, 42, TODAY, balance_reference=TODAY)
    assert s.financial_position.current_balance == balance
    assert s.income.estimated_monthly_income is not None
    assert s.savings.balance is None
    assert "ground_truth" not in s.model_dump_json()


@pytest.mark.parametrize("username", ["lotte", "sara", "jan"])
def test_existing_long_history_demo_customers(conn, username):
    from synth.demo_customers import demo_customers
    _, customer, txs, balance = next(row for row in demo_customers() if row[0] == username)
    next_id = conn.execute("SELECT MAX(id)+1 FROM transactions").fetchone()[0]
    for i, t in enumerate(txs):
        t.id = next_id+i
    db.insert_customer(conn, customer, balance)
    db.insert_transactions(conn, txs)
    s = get_state(conn, customer.id, TODAY, balance_reference=TODAY)
    assert s.financial_position.current_balance == balance
    assert len(s.cash_flow.monthly) >= 90
    assert s.income.estimated_monthly_income > 0
    assert all(c.detected_at <= TODAY for c in s.changes+s.events)
    assert len({c.id for c in s.changes}) == len(s.changes)
    if username == "sara":
        assert any(c.type == "SUBSCRIPTION_PRICE_CHANGED" and c.entity == "netflix"
                   and c.current_value == 17.99 for c in s.changes)


def test_account_observation_correction_invalidates_state(conn):
    first = state(conn)
    put_account(conn, IDS["stable"], AccountObservation(id=f"savings:{TODAY}", account_id="savings", kind="savings",
                                                     observed_at=TODAY, balance=15000))
    second = state(conn)
    assert second.savings.balance == 15000
    assert second.freshness["source_hash"] != first.freshness["source_hash"]


def test_savings_withdrawals_and_both_transfer_legs_do_not_become_income(conn):
    cid = IDS["stable"]
    tid = conn.execute("SELECT MAX(id)+1 FROM transactions").fetchone()[0]
    db.insert_transactions(conn, [Transaction(id=tid, customer_id=cid, date=dt.date(2026, 9, 29), amount=600,
                                             category="savings_transfer", counterparty="Own Savings"),
                                 Transaction(id=tid+1, customer_id=cid, date=dt.date(2026, 9, 29), amount=-600,
                                             category="savings_transfer", counterparty="Own Current")])
    put_details(conn, tid+1, TransactionDetails(account_id="savings", internal_transfer=True))
    s = state(conn)
    assert s.income.estimated_monthly_income == 3000
    assert s.expenses.average_monthly_expenses == 1662
    assert s.savings.withdrawals_from_savings == 600
    assert s.savings.average_monthly_savings == 900
    assert next(x for x in s.signals if x.transaction_id == tid+1).kind == "transfer"


def test_two_yearly_observations_and_month_end_cadence(conn):
    from app.customer_state.models import Observations, RawTransaction
    annual = [RawTransaction(id=i, date=dt.date(year, 10, 12), amount=-600, category="insurance_car", counterparty="Insurer")
              for i, year in enumerate((2024, 2025), start=1)]
    monthly = [RawTransaction(id=10+i, date=day, amount=3000, category="salary", counterparty="Employer")
               for i, day in enumerate([dt.date(2026, 1, 31), dt.date(2026, 2, 28), dt.date(2026, 3, 31)])]
    raw = Observations(customer_id=1, products=[], transactions=annual+monthly, accounts=[])
    patterns, _ = detect(normalize(raw), dt.date(2026, 3, 31))
    year = next(p for p in patterns if p.category == "insurance_car")
    assert year.monthly_amount == 50
    assert year.next_date == dt.date(2026, 10, 12)
    salary = next(p for p in patterns if p.category == "salary")
    assert salary.next_date == dt.date(2026, 4, 30)


def test_missing_payment_event_survives_resumption(conn):
    cid = IDS["stable"]
    conn.execute("DELETE FROM transactions WHERE customer_id=? AND category='salary' AND date LIKE '2026-08-%'", (cid,))
    before = state(conn, as_of=dt.date(2026, 9, 5))
    event = next(c for c in before.changes if c.type == "INCOME_DISAPPEARED")
    after = state(conn)
    assert event.id in {c.id for c in after.changes}
    assert after.income.next_expected_income_date == dt.date(2026, 10, 25)


def test_new_category_adapter_supports_loan_and_debt_payment_change(conn):
    ids = [r[0] for r in conn.execute("SELECT id FROM transactions WHERE customer_id=? AND category='mortgage' ORDER BY date", (IDS["debt"],))]
    for tid in ids:
        put_details(conn, tid, TransactionDetails(canonical_category="loan", payment_method="direct_debit"))
    conn.execute("UPDATE transactions SET amount=-1000 WHERE id=?", (ids[-1],))
    s = state(conn, "debt")
    assert s.debt.monthly_debt_service == 916.67
    assert any(c.type == "DEBT_PAYMENT_CHANGED" and c.current_value == 1000 for c in s.changes)
    assert all(t.category == "mortgage" for t in s.observations.transactions if t.id in ids)


def test_sensitive_metadata_and_refunds(conn):
    tid = conn.execute("SELECT id FROM transactions WHERE customer_id=? AND category='subscription' LIMIT 1", (IDS["stable"],)).fetchone()[0]
    put_details(conn, tid, TransactionDetails(sensitive=True))
    s = state(conn)
    assert next(x for x in s.signals if x.transaction_id == tid).entity is None
    refund_id = conn.execute("SELECT MAX(id)+1 FROM transactions").fetchone()[0]
    db.insert_transactions(conn, [Transaction(id=refund_id, customer_id=IDS["stable"], date=TODAY, amount=120,
                                             category="groceries", counterparty="Supermarket")])
    refunded = state(conn)
    assert refunded.income.estimated_monthly_income == 3000
    assert refunded.expenses.average_monthly_expenses == 1642


def test_recurring_subscription_refunds_do_not_create_bills_or_income(conn):
    conn.execute("UPDATE transactions SET amount=12 WHERE customer_id=? AND category='subscription'", (IDS["stable"],))
    s = state(conn)
    assert s.subscriptions.count == 0
    assert s.income.estimated_monthly_income == 3000
    assert s.expenses.average_monthly_expenses == 1638
    assert all(p.category != "subscription" for p in s.patterns)


def test_legacy_balance_reconstruction_does_not_mix_currencies(conn):
    cid = IDS["stable"]
    conn.execute("DELETE FROM customer_state_account_observations WHERE customer_id=?", (cid,))
    tid = conn.execute("SELECT MAX(id)+1 FROM transactions").fetchone()[0]
    before = state(conn, as_of=dt.date(2026, 8, 31))
    db.insert_transactions(conn, [Transaction(id=tid, customer_id=cid, date=TODAY, amount=-5000,
                                             category="other", counterparty="External GBP account")])
    put_details(conn, tid, TransactionDetails(account_id="external", currency="GBP"))
    after = state(conn, as_of=dt.date(2026, 8, 31))
    assert after.financial_position.current_balance == before.financial_position.current_balance


def test_provider_boundary_and_versioned_cache(conn):
    class NoInference:
        version = "test-empty"

        def infer(self, state):
            return []

    before = state(conn)
    after = get_state(conn, IDS["stable"], TODAY, balance_reference=TODAY, provider=NoInference())
    assert after.inferences == []
    assert before.income == after.income
    assert before.freshness["algorithm_version"] != after.freshness["algorithm_version"]


def test_schema_migration_is_additive_and_deterministic_seed(conn):
    initial = state(conn)
    db.init_schema(conn)
    assert state(conn).model_dump() == initial.model_dump()
    other = db.connect(":memory:")
    try:
        db.init_schema(other)
        seed(other)
        assert state(other).observations == initial.observations
        assert state(other).changes == initial.changes
    finally:
        other.close()


def test_customer_state_api_session_isolation_and_domains(tmp_path, monkeypatch):
    path = str(tmp_path / "state.db")
    monkeypatch.setattr(db, "DB_PATH", path)
    with db.tx(path) as conn:
        db.init_schema(conn)
        seed(conn, users=True)
        db.insert_user(conn, "state_advisor", hash_password("demo"), "advisor", None)
    from app.main import app
    with TestClient(app) as client:
        assert client.get("/api/me/customer-state").status_code == 401
        assert client.post("/api/login", json={"username": "state_stable", "password": "demo"}).status_code == 200
        response = client.get(f"/api/me/customer-state?customer_id={IDS['debt']}")
        assert response.status_code == 200
        assert response.json()["customer_id"] == IDS["stable"]
        assert "ground_truth" not in response.text
        assert client.get("/api/me/customer-state/income").json()["data"]["estimated_monthly_income"] == 3000
        assert client.get("/api/me/customer-state/cash-flow").status_code == 200
        assert client.get("/api/me/customer-state/invalid").status_code == 404
        assert client.get("/api/me/customer-state?as_of=bad").status_code == 422
        assert client.get("/api/me/customer-state?as_of=2099-01-01").json()["as_of"] == str(TODAY)
        assert response.headers["cache-control"] == "no-store"
        client.cookies.clear()
        client.post("/api/login", json={"username": "state_debt", "password": "demo"})
        assert client.get("/api/me/customer-state/debt").json()["data"]["total_known_debt"] == 184150
        client.cookies.clear()
        client.post("/api/login", json={"username": "state_advisor", "password": "demo"})
        assert client.get("/api/me/customer-state").status_code == 403
