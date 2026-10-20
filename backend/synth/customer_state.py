"""Deterministic financial scenarios, using the existing banking tables and TxBuilder.

Append to a generated database (never deletes existing customers):
    python -m synth.customer_state --db kbc.db
Accounts: state_stable, state_variable, ...; password uses the existing DEMO_PASSWORD.
"""
from __future__ import annotations

import argparse
import datetime as dt
import random

from app import db
from app.auth import hash_password
from app.customer_state.models import AccountObservation, TransactionDetails
from app.customer_state.storage import put_account, put_details
from app.schemas import Customer
from .generate import DEMO_PASSWORD, TODAY, TxBuilder, safe_date

SCENARIOS = ("stable", "variable", "salary_increase", "subscriptions", "spending_increase",
             "declining_buffer", "growing_savings", "debt", "low_balance", "foreign")
IDS = {name: 100001+i for i, name in enumerate(SCENARIOS)}


def seed(conn, *, users: bool = False) -> dict[str, int]:
    """Call on an initialized DB. Existing scenario IDs are reserved and must be unused."""
    next_id = conn.execute("SELECT COALESCE(MAX(id), 0)+1 FROM transactions").fetchone()[0]
    password = hash_password(DEMO_PASSWORD) if users else None
    for name, cid in IDS.items():
        if db.get_customer(conn, cid):
            raise ValueError(f"Customer {cid} already exists; use a fresh DB or seed only once")
        b = TxBuilder(cid, random.Random(cid), dt.date(2026, 1, 1), TODAY)
        for m in range(1, 10):
            salary = (1800, 4100, 2300, 5000, 1600, 3400, 2400, 4200, 2000)[m-1] if name == "variable" else 3000
            if name == "salary_increase" and m >= 8:
                salary = 3600
            if name == "low_balance":
                salary = 2200
            cat = "invoice_income" if name == "variable" else "salary"
            b.add(safe_date(2026, m, 25+(m % 3)-1), salary, cat, "Employer" if cat == "salary" else f"Client {m % 2}")
            if name == "variable":
                b.add(safe_date(2026, m, 10), 300, "invoice_income", "Side Client")
            b.add(safe_date(2026, m, 1), 1400 if name == "low_balance" else 900,
                  "mortgage" if name == "debt" else "rent", "Home lender" if name == "debt" else "Landlord")
            b.add(safe_date(2026, m, 8+m % 2), 150+(m % 3-1)*10, "utilities", "Electricity")
            b.add(safe_date(2026, m, 14), 15 if name == "subscriptions" and m >= 8 else 12, "subscription", "Stream")
            for day in (5, 12, 19, 26):
                b.add(safe_date(2026, m, day), 100, "groceries", "Supermarket")
            leisure = 650 if name == "spending_increase" and m >= 8 else 200
            if name == "declining_buffer":
                leisure = 300+m*250
            b.add(safe_date(2026, m, 18), leisure, "leisure", "Restaurant")
            saved = 100*m if name == "growing_savings" else 1000
            if name in {"declining_buffer", "low_balance"}:
                saved = 0
            if saved:
                b.add(safe_date(2026, m, 27), saved, "savings_transfer", "Own Savings")
            if name == "subscriptions":
                for i in range(5):
                    b.add(safe_date(2026, m, 10+i), 8+i, "subscription", f"Service {i}")
                b.add(safe_date(2026, m, 16), 65, "telecom", "Internet")
                b.add(safe_date(2026, m, 17), 40, "insurance_home", "Insurance")
        if name == "foreign":
            b.add(dt.date(2026, 9, 12), 480, "leisure", "Lisbon Hotel")
            b.add(dt.date(2026, 9, 13), 80, "leisure", "Lisbon Cafe")
            b.add(dt.date(2026, 9, 14), 50, "other", "London Shop")
            b.add(dt.date(2026, 9, 20), 2400, "furniture", "New Furniture")
        txs = sorted(b.txs, key=lambda t: (t.date, t.counterparty))
        for t in txs:
            t.id = next_id
            next_id += 1
        # Balanced ledgers: savings receives the opposite of the one-sided legacy savings transfer.
        opening = 50 if name == "low_balance" else 6000 if name == "declining_buffer" else 1500
        closing = round(opening+sum(t.amount for t in txs if t.counterparty != "London Shop"), 2)
        db.insert_customer(conn, Customer(id=cid, first_name=name, last_name="Synthetic", birth_year=1990,
                                          city="Leuven", products=["current", "savings"] + (["mortgage"] if name == "debt" else [])), closing)
        db.insert_transactions(conn, txs)
        for t in txs:
            put_details(conn, t.id, TransactionDetails(account_id="external-gbp" if t.counterparty == "London Shop" else "current",
                                                      country="PT" if t.counterparty.startswith("Lisbon") else "GB"
                                                      if t.counterparty == "London Shop" else "BE",
                                                      currency="GBP" if t.counterparty == "London Shop" else "EUR",
                                                      payment_method="transfer" if t.category in {"salary", "rent", "mortgage", "savings_transfer"} else "card",
                                                      source="synthetic", internal_transfer=t.category == "savings_transfer"))
        for m in range(1, 10):
            day = safe_date(2026, m, 31)
            past = [t for t in txs if t.date <= day]
            # The GBP source is an external account, and does not alter the EUR current account.
            balance = opening+sum(t.amount for t in past if t.counterparty != "London Shop")
            saved = 5000-sum(t.amount for t in past if t.category == "savings_transfer")
            if name == "declining_buffer":
                saved = 0
            for account, kind, value in [("current", "current", balance), ("savings", "savings", saved)]:
                put_account(conn, cid, AccountObservation(id=f"{account}:{day}", account_id=account,
                                                         kind=kind, observed_at=day, balance=round(value, 2), source="synthetic"))
            if name == "debt":
                put_account(conn, cid, AccountObservation(id=f"mortgage:{day}", account_id="mortgage", kind="loan",
                                                         observed_at=day, balance=190000-650*m, source="synthetic"))
        if users:
            db.insert_user(conn, f"state_{name}", password, "customer", cid)
    return IDS.copy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=db.DB_PATH)
    args = parser.parse_args()
    # Schema DDL is outside the seed transaction; a collision rolls back the whole seed.
    conn = db.connect(args.db)
    try:
        db.init_schema(conn)
        with conn:
            seed(conn, users=True)
    finally:
        conn.close()
    print(f"Added {len(IDS)} Customer State scenarios to {args.db}")


if __name__ == "__main__":
    main()
