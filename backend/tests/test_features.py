"""Features tests + shared fixture helpers (imported by the other engine tests)."""
from __future__ import annotations

import datetime as dt

from app.engine.features import balance_series, compute_features
from app.schemas import Customer, Transaction

D = dt.date


class TxBuilder:
    """Tiny helper to hand-build transaction histories."""

    def __init__(self, customer_id: int = 1):
        self.customer_id = customer_id
        self.txs: list[Transaction] = []
        self._id = 0

    def add(self, date: dt.date, amount: float, category: str, counterparty: str) -> "TxBuilder":
        self._id += 1
        self.txs.append(Transaction(id=self._id, customer_id=self.customer_id, date=date, amount=amount,
                                    category=category, counterparty=counterparty))
        return self

    def monthly(self, start: dt.date, end: dt.date, amount: float, category: str, counterparty: str,
                day: int = 1) -> "TxBuilder":
        y, m = start.year, start.month
        while D(y, m, 1) <= end:
            d = D(y, m, min(day, 28))
            if start <= d <= end:
                self.add(d, amount, category, counterparty)
            m += 1
            if m > 12:
                m, y = 1, y + 1
        return self

    def yearly(self, first: dt.date, end: dt.date, amount: float, category: str, counterparty: str) -> "TxBuilder":
        d = first
        while d <= end:
            self.add(d, amount, category, counterparty)
            d = d.replace(year=d.year + 1)
        return self


def customer(**kw) -> Customer:
    base = dict(id=1, first_name="Test", last_name="Person", birth_year=1990, city="Leuven", language="nl",
                products=["current"], consent_personalization=True)
    base.update(kw)
    return Customer(**base)


def baseline(b: TxBuilder, start: dt.date, end: dt.date) -> TxBuilder:
    """Everyday spending every month so features are never empty."""
    b.monthly(start, end, -320, "groceries", "Colruyt", day=5)
    b.monthly(start, end, -320, "groceries", "Colruyt", day=19)
    b.monthly(start, end, -95, "utilities", "Engie", day=8)
    b.monthly(start, end, -35, "telecom", "Proximus", day=10)
    b.monthly(start, end, -80, "leisure", "Cinema Kinepolis", day=15)
    return b


END = D(2026, 9, 30)


def salaried_customer():
    b = TxBuilder()
    baseline(b, D(2025, 1, 1), END)
    b.monthly(D(2025, 1, 1), END, 2600, "salary", "Acme NV", day=25)
    b.monthly(D(2025, 1, 1), END, -850, "rent", "Immo Leuven", day=1)
    return customer(birth_year=1995), b.txs


def test_balance_at_as_of_undoes_future_transactions():
    c, txs = salaried_customer()
    f_now = compute_features(c, txs, 3000.0, END)
    assert f_now.balance_eur == 3000.0
    f_past = compute_features(c, txs, 3000.0, D(2026, 9, 24))  # before the 25 Sep salary
    assert f_past.balance_eur == 3000.0 - 2600  # salary undone (no other txs 25..30 Sep)


def test_only_past_transactions_are_used():
    c, txs = salaried_customer()
    f = compute_features(c, txs, 3000.0, D(2025, 6, 30))
    assert f.last_tx_date <= D(2025, 6, 30)
    assert f.first_tx_date == D(2025, 1, 1)


def test_income_and_spend_averages_and_flags():
    c, txs = salaried_customer()
    f = compute_features(c, txs, 3000.0, END)
    assert 2500 < f.monthly_income_avg_90d < 2700
    assert 1300 < f.monthly_spend_avg_90d < 1900  # 90-day window catches 2 of 3 rent payments
    assert f.has_salary and f.has_rent and not f.has_pension and not f.has_child_signals
    assert f.income_regularity < 0.1
    assert f.income_sources_180d == 1
    assert f.next_income_date == D(2026, 10, 25)
    assert f.next_income_eur == 2600
    assert f.runway_days is None  # income > spend


def test_recurring_monthly_and_yearly_and_price_change():
    b = TxBuilder()
    baseline(b, D(2025, 1, 1), END)
    b.monthly(D(2025, 1, 1), D(2026, 8, 31), -13.99, "subscription", "Netflix", day=14)
    b.add(D(2026, 9, 14), -17.99, "subscription", "Netflix")
    b.yearly(D(2024, 10, 12), D(2025, 10, 12), -612, "insurance_car", "AG Insurance")
    f = compute_features(customer(), b.txs, 1000.0, END)
    netflix = next(r for r in f.recurring_payments if r.counterparty == "Netflix")
    assert netflix.period_days == 30 and netflix.amount_eur == 17.99 and netflix.previous_amount_eur == 13.99
    ag = next(r for r in f.recurring_payments if r.counterparty == "AG Insurance")
    assert ag.period_days == 365 and ag.next_date == D(2026, 10, 12) and ag.previous_amount_eur is None


def test_runway_and_idle_cash():
    b = TxBuilder()
    baseline(b, D(2025, 6, 1), END)  # ~850/month spend, no income
    f = compute_features(customer(products=["current"]), b.txs, 425.0, END)
    assert f.runway_days is not None and 10 <= f.runway_days <= 20
    f2 = compute_features(customer(products=["current"]), b.txs, 20000.0, END)
    assert f2.idle_cash_eur > 10000
    f3 = compute_features(customer(products=["current", "savings"]), b.txs, 20000.0, END)
    assert f3.idle_cash_eur == 0


def test_variable_spend_change():
    b = TxBuilder()
    baseline(b, D(2025, 6, 1), END)
    for day in range(1, 29):  # September spree
        b.add(D(2026, 9, day), -60, "leisure", "Bar")
    f = compute_features(customer(), b.txs, 1000.0, END)
    assert f.variable_spend_change_30d > 0.8


def test_life_events_and_quarter_income():
    b = TxBuilder()
    baseline(b, D(2025, 1, 1), END)
    b.monthly(D(2025, 1, 1), D(2025, 12, 31), 2400, "salary", "Acme NV", day=25)
    b.monthly(D(2026, 1, 1), END, 3000, "invoice_income", "Client A", day=10)
    b.add(D(2024, 3, 1), 170, "child_benefit", "Groeipakket")
    f = compute_features(customer(), b.txs, 1000.0, END)
    types = {e.type: e.date for e in f.life_events}
    assert types["first_salary"] == D(2025, 1, 25)
    assert types["first_invoice"] == D(2026, 1, 10)
    assert types["baby"] == D(2024, 3, 1)
    assert f.quarter_invoice_income_eur == 9000  # Jul, Aug, Sep
    assert f.has_invoice_income


def test_balance_series_is_consistent():
    c, txs = salaried_customer()
    s = balance_series(c, txs, 3000.0, END, days=30)
    assert len(s) == 30 and s[-1] == 3000.0
    f = compute_features(c, txs, 3000.0, END - dt.timedelta(days=29))
    assert abs(s[0] - f.balance_eur) < 0.01


def test_vat_period_rule():
    from app.engine.features import vat_period
    # on/before the due date of the last ended quarter → that quarter
    assert vat_period(D(2026, 9, 30))[2:] == (D(2026, 10, 20), "Q3 2026")
    assert vat_period(D(2026, 10, 20))[2:] == (D(2026, 10, 20), "Q3 2026")
    # after it → running quarter
    assert vat_period(D(2026, 10, 21))[2:] == (D(2027, 1, 20), "Q4 2026")
    assert vat_period(D(2026, 1, 10))[2:] == (D(2026, 1, 20), "Q4 2025")
    assert vat_period(D(2026, 2, 1))[2:] == (D(2026, 4, 20), "Q1 2026")
    c, txs = salaried_customer()
    f = compute_features(c, txs, 3000.0, END)
    assert f.vat_period_label == "Q3 2026" and f.vat_due_date is None  # no invoices → no due date


def test_one_offs_excluded_from_forecasts_and_runway_capped():
    b = TxBuilder()
    baseline(b, D(2025, 1, 1), END)
    b.monthly(D(2025, 1, 1), END, 2400, "salary", "Acme NV", day=25)
    b.add(D(2026, 9, 20), -12500, "notary", "Notaris Claes")
    f = compute_features(customer(), b.txs, 1500.0, END)
    assert f.variable_spend_change_30d < 0.2
    assert f.runway_days is None                       # regular burn is covered by salary
    assert f.spend_by_category_30d["notary"] == 12500  # still visible in the breakdown
    b2 = TxBuilder()
    baseline(b2, D(2025, 6, 1), END)
    assert compute_features(customer(), b2.txs, 200000.0, END).runway_days is None  # > 365 days → None


def test_no_squeeze_signal_without_baseline_history():
    b = TxBuilder()
    baseline(b, D(2026, 8, 1), END)
    for day in range(1, 29):
        b.add(D(2026, 9, day), -60, "leisure", "Bar")
    assert compute_features(customer(), b.txs, 1000.0, END).variable_spend_change_30d == 0.0


def test_single_insurance_payment_counts_as_yearly_and_utilities_never_change_price():
    b = TxBuilder()
    baseline(b, D(2025, 9, 1), END)
    b.add(D(2025, 10, 14), -735.62, "insurance_car", "Baloise")
    b.monthly(D(2025, 9, 1), D(2026, 8, 31), -110, "utilities", "Farys", day=8)
    b.add(D(2026, 9, 8), -160, "utilities", "Farys")     # usage-driven, not a price increase
    f = compute_features(customer(), b.txs, 1000.0, END)
    ins = next(r for r in f.recurring_payments if r.counterparty == "Baloise")
    assert ins.period_days == 365 and ins.next_date == D(2026, 10, 14) and ins.previous_amount_eur is None
    farys = next(r for r in f.recurring_payments if r.counterparty == "Farys")
    assert farys.period_days == 30 and farys.previous_amount_eur is None


def test_monthly_spend_excludes_one_offs_so_idle_cash_shows():
    b = TxBuilder()
    baseline(b, D(2025, 6, 1), END)                                    # ≈ €850/month regular
    b.add(D(2026, 9, 10), -4000, "furniture", "IKEA")
    b.monthly(D(2025, 6, 1), END, -500, "savings_transfer", "KBC Spaarrekening", day=27)
    f = compute_features(customer(products=["current"]), b.txs, 13510.0, END)
    assert f.monthly_spend_avg_90d < 1000
    assert f.idle_cash_eur > 8000


def test_price_change_detected_after_two_payments_at_new_price_but_not_after_60_days():
    b = TxBuilder()
    baseline(b, D(2025, 1, 1), END)
    b.monthly(D(2025, 1, 1), D(2026, 7, 31), -8.99, "subscription", "Disney+", day=14)
    b.monthly(D(2026, 8, 1), END, -11.99, "subscription", "Disney+", day=14)   # 14 Aug and 14 Sep
    r = next(r for r in compute_features(customer(), b.txs, 500.0, END).recurring_payments if r.counterparty == "Disney+")
    assert r.amount_eur == 11.99 and r.previous_amount_eur == 8.99
    b.monthly(D(2026, 10, 1), D(2026, 12, 31), -11.99, "subscription", "Disney+", day=14)
    r = next(r for r in compute_features(customer(), b.txs, 500.0, D(2026, 12, 20)).recurring_payments if r.counterparty == "Disney+")
    assert r.previous_amount_eur is None   # the change is older than 60 days
