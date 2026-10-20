"""Additive source tables and versioned, replaceable derived snapshots."""
from __future__ import annotations

import sqlite3

from .models import AccountObservation, CustomerState, TransactionDetails

SCHEMA = """
CREATE TABLE IF NOT EXISTS customer_state_transaction_details (
  transaction_id INTEGER PRIMARY KEY REFERENCES transactions(id) ON DELETE CASCADE,
  data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS customer_state_account_observations (
  customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  id TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  data TEXT NOT NULL,
  PRIMARY KEY (customer_id, id)
);
CREATE INDEX IF NOT EXISTS ix_state_account_date
  ON customer_state_account_observations(customer_id, observed_at);
CREATE TABLE IF NOT EXISTS customer_state_snapshots (
  customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  as_of TEXT NOT NULL,
  algorithm_version TEXT NOT NULL,
  source_hash TEXT NOT NULL,
  data TEXT NOT NULL,
  PRIMARY KEY (customer_id, as_of, algorithm_version)
);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def put_details(conn: sqlite3.Connection, transaction_id: int, details: TransactionDetails) -> None:
    conn.execute(
        "INSERT INTO customer_state_transaction_details VALUES (?, ?) "
        "ON CONFLICT(transaction_id) DO UPDATE SET data=excluded.data",
        (transaction_id, details.model_dump_json()),
    )


def put_account(conn: sqlite3.Connection, customer_id: int, observation: AccountObservation) -> None:
    conn.execute(
        "INSERT INTO customer_state_account_observations VALUES (?, ?, ?, ?) "
        "ON CONFLICT(customer_id, id) DO UPDATE SET observed_at=excluded.observed_at, data=excluded.data",
        (customer_id, observation.id, observation.observed_at.isoformat(), observation.model_dump_json()),
    )


def cached(conn, customer_id: int, as_of: str, version: str, source_hash: str) -> CustomerState | None:
    row = conn.execute(
        "SELECT data FROM customer_state_snapshots WHERE customer_id=? AND as_of=? "
        "AND algorithm_version=? AND source_hash=?", (customer_id, as_of, version, source_hash),
    ).fetchone()
    return CustomerState.model_validate_json(row["data"]) if row else None


def save(conn, state: CustomerState, version: str, source_hash: str) -> None:
    conn.execute(
        "INSERT INTO customer_state_snapshots VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(customer_id, as_of, algorithm_version) DO UPDATE SET "
        "source_hash=excluded.source_hash, data=excluded.data",
        (state.customer_id, state.as_of.isoformat(), version, source_hash, state.model_dump_json()),
    )
