"""SQLite access. Bound parameters only; no string-formatted SQL, ever.

Both the API and the synthetic generator use this module so the schema lives in one place.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .schemas import (Customer, DeclaredSignalRow, FeedbackRow, LayoutPrefRow, Prefs, StylePrefs,
                      SuggestionDismissal, Transaction)

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.abspath(os.path.join(HERE, "..", "kbc.db"))
DB_PATH = os.environ.get("KBC_DB_PATH", DEFAULT_DB_PATH)

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
  id INTEGER PRIMARY KEY,
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  birth_year INTEGER NOT NULL,
  city TEXT NOT NULL,
  language TEXT NOT NULL CHECK (language IN ('nl','fr')),
  products TEXT NOT NULL DEFAULT '[]',
  consent_personalization INTEGER NOT NULL DEFAULT 1,
  ground_truth TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS accounts (
  customer_id INTEGER PRIMARY KEY REFERENCES customers(id),
  balance_today REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS transactions (
  id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  date TEXT NOT NULL,
  amount REAL NOT NULL,
  category TEXT NOT NULL,
  counterparty TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_tx_customer_date ON transactions(customer_id, date);
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('customer','advisor')),
  customer_id INTEGER REFERENCES customers(id)
);
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  card_key TEXT NOT NULL,
  card_type TEXT NOT NULL,
  decision TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_feedback_customer ON feedback(customer_id);
CREATE TABLE IF NOT EXISTS layout_prefs (
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  component TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('pinned','hidden')),
  created_at TEXT NOT NULL,
  position INTEGER,
  PRIMARY KEY (customer_id, component)
);
CREATE TABLE IF NOT EXISTS style_prefs (
  customer_id INTEGER PRIMARY KEY REFERENCES customers(id),
  data TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS declared_signals (
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  signal TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (customer_id, signal)
);
CREATE TABLE IF NOT EXISTS suggestion_dismissals (
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  component TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (customer_id, component)
);
CREATE TABLE IF NOT EXISTS visits (
  customer_id INTEGER PRIMARY KEY REFERENCES customers(id),
  last_visit TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY,
  at TEXT NOT NULL,
  user_id INTEGER NOT NULL,
  action TEXT NOT NULL,
  target TEXT NOT NULL
);
"""


def connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    migrate(conn)
    from .customer_state.storage import init_schema as init_customer_state
    init_customer_state(conn)


def migrate(conn: sqlite3.Connection) -> None:
    """Bring a database built by an older version up to date (new tables come from CREATE IF NOT EXISTS)."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(layout_prefs)").fetchall()}
    if "position" not in cols:
        conn.execute("ALTER TABLE layout_prefs ADD COLUMN position INTEGER")


@contextmanager
def tx(path: str | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ----------------------------------------------------------------------------------
# Reads
# ----------------------------------------------------------------------------------


def _row_to_customer(row: sqlite3.Row) -> Customer:
    return Customer(
        id=row["id"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        birth_year=row["birth_year"],
        city=row["city"],
        language=row["language"],
        products=json.loads(row["products"]),
        consent_personalization=bool(row["consent_personalization"]),
        ground_truth=json.loads(row["ground_truth"]),
    )


def get_customer(conn: sqlite3.Connection, customer_id: int) -> Customer | None:
    row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    return _row_to_customer(row) if row else None


def all_customer_ids(conn: sqlite3.Connection) -> list[int]:
    return [r["id"] for r in conn.execute("SELECT id FROM customers ORDER BY id")]


def get_balance_today(conn: sqlite3.Connection, customer_id: int) -> float:
    row = conn.execute("SELECT balance_today FROM accounts WHERE customer_id = ?", (customer_id,)).fetchone()
    return float(row["balance_today"]) if row else 0.0


def get_transactions(conn: sqlite3.Connection, customer_id: int) -> list[Transaction]:
    rows = conn.execute(
        "SELECT id, customer_id, date, amount, category, counterparty FROM transactions "
        "WHERE customer_id = ? ORDER BY date, id",
        (customer_id,),
    ).fetchall()
    return [
        Transaction(
            id=r["id"], customer_id=r["customer_id"], date=dt.date.fromisoformat(r["date"]),
            amount=r["amount"], category=r["category"], counterparty=r["counterparty"],
        )
        for r in rows
    ]


def get_prefs(conn: sqlite3.Connection, customer_id: int) -> Prefs:
    fb = conn.execute(
        "SELECT card_key, card_type, decision, created_at FROM feedback WHERE customer_id = ? ORDER BY id",
        (customer_id,),
    ).fetchall()
    lp = conn.execute(
        "SELECT component, state, position FROM layout_prefs WHERE customer_id = ? ORDER BY created_at, component",
        (customer_id,),
    ).fetchall()
    visit = conn.execute("SELECT last_visit FROM visits WHERE customer_id = ?", (customer_id,)).fetchone()
    style = conn.execute("SELECT data FROM style_prefs WHERE customer_id = ?", (customer_id,)).fetchone()
    declared = conn.execute(
        "SELECT signal, created_at FROM declared_signals WHERE customer_id = ? ORDER BY created_at", (customer_id,)
    ).fetchall()
    dismissed = conn.execute(
        "SELECT component, created_at FROM suggestion_dismissals WHERE customer_id = ?", (customer_id,)
    ).fetchall()
    return Prefs(
        feedback=[
            FeedbackRow(card_key=r["card_key"], card_type=r["card_type"], decision=r["decision"],
                        created_at=dt.date.fromisoformat(r["created_at"][:10]))
            for r in fb
        ],
        layout_prefs=[LayoutPrefRow(component=r["component"], state=r["state"], position=r["position"]) for r in lp],
        last_visit=dt.date.fromisoformat(visit["last_visit"][:10]) if visit else None,
        style=StylePrefs.model_validate_json(style["data"]) if style else StylePrefs(),
        declared=[DeclaredSignalRow(signal=r["signal"], created_at=dt.date.fromisoformat(r["created_at"][:10]))
                  for r in declared],
        dismissed_suggestions=[SuggestionDismissal(component=r["component"],
                                                   created_at=dt.date.fromisoformat(r["created_at"][:10]))
                               for r in dismissed],
    )


def get_user(conn: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def date_range(conn: sqlite3.Connection, customer_id: int) -> tuple[dt.date, dt.date] | None:
    row = conn.execute(
        "SELECT MIN(date) AS lo, MAX(date) AS hi FROM transactions WHERE customer_id = ?", (customer_id,)
    ).fetchone()
    if not row or row["lo"] is None:
        return None
    return dt.date.fromisoformat(row["lo"]), dt.date.fromisoformat(row["hi"])


# ----------------------------------------------------------------------------------
# Writes
# ----------------------------------------------------------------------------------


def add_feedback(conn: sqlite3.Connection, customer_id: int, card_key: str, card_type: str,
                 decision: str, at: dt.date) -> None:
    if decision == "reset":
        conn.execute("DELETE FROM feedback WHERE customer_id = ?", (customer_id,))
        return
    conn.execute(
        "INSERT INTO feedback (customer_id, card_key, card_type, decision, created_at) VALUES (?, ?, ?, ?, ?)",
        (customer_id, card_key, card_type, decision, at.isoformat()),
    )


def set_layout_pref(conn: sqlite3.Connection, customer_id: int, component: str, state: str, at: dt.date,
                    position: int | None = None) -> None:
    if state == "reset":
        conn.execute("DELETE FROM layout_prefs WHERE customer_id = ? AND component = ?", (customer_id, component))
        return
    # created_at orders pins; use the wall clock so the latest pin wins ties, whatever the time-travel date
    stamp = f"{at.isoformat()}T{dt.datetime.now(dt.timezone.utc).strftime('%H:%M:%S.%f')}"
    conn.execute(
        "INSERT INTO layout_prefs (customer_id, component, state, created_at, position) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(customer_id, component) DO UPDATE SET state = excluded.state, created_at = excluded.created_at, "
        "position = excluded.position",
        (customer_id, component, state, stamp, position if state == "pinned" else None),
    )


def unpin_heroes(conn: sqlite3.Connection, customer_id: int, heroes: tuple[str, ...]) -> None:
    """Only one hero can be pinned: pinning a new one releases the others."""
    conn.executemany(
        "DELETE FROM layout_prefs WHERE customer_id = ? AND component = ? AND state = 'pinned'",
        [(customer_id, h) for h in heroes],
    )


def reset_layout(conn: sqlite3.Connection, customer_id: int) -> None:
    conn.execute("DELETE FROM layout_prefs WHERE customer_id = ?", (customer_id,))
    conn.execute("DELETE FROM suggestion_dismissals WHERE customer_id = ?", (customer_id,))


def set_style(conn: sqlite3.Connection, customer_id: int, style: StylePrefs) -> None:
    conn.execute(
        "INSERT INTO style_prefs (customer_id, data) VALUES (?, ?) "
        "ON CONFLICT(customer_id) DO UPDATE SET data = excluded.data",
        (customer_id, style.model_dump_json()),
    )


def set_declared(conn: sqlite3.Connection, customer_id: int, signal: str, state: str, at: dt.date) -> None:
    if state == "clear":
        conn.execute("DELETE FROM declared_signals WHERE customer_id = ? AND signal = ?", (customer_id, signal))
        return
    conn.execute(
        "INSERT INTO declared_signals (customer_id, signal, created_at) VALUES (?, ?, ?) "
        "ON CONFLICT(customer_id, signal) DO UPDATE SET created_at = excluded.created_at",
        (customer_id, signal, at.isoformat()),
    )


def dismiss_suggestion(conn: sqlite3.Connection, customer_id: int, component: str, at: dt.date) -> None:
    conn.execute(
        "INSERT INTO suggestion_dismissals (customer_id, component, created_at) VALUES (?, ?, ?) "
        "ON CONFLICT(customer_id, component) DO UPDATE SET created_at = excluded.created_at",
        (customer_id, component, at.isoformat()),
    )


def set_consent(conn: sqlite3.Connection, customer_id: int, consent: bool) -> None:
    conn.execute("UPDATE customers SET consent_personalization = ? WHERE id = ?", (1 if consent else 0, customer_id))


def touch_visit(conn: sqlite3.Connection, customer_id: int, at: dt.date) -> None:
    conn.execute(
        "INSERT INTO visits (customer_id, last_visit) VALUES (?, ?) "
        "ON CONFLICT(customer_id) DO UPDATE SET last_visit = excluded.last_visit",
        (customer_id, at.isoformat()),
    )


def audit(conn: sqlite3.Connection, user_id: int, action: str, target: str) -> None:
    conn.execute(
        "INSERT INTO audit_log (at, user_id, action, target) VALUES (?, ?, ?, ?)",
        (dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), user_id, action, target),
    )


# ----------------------------------------------------------------------------------
# Bulk insert helpers for the synthetic generator
# ----------------------------------------------------------------------------------


def insert_customer(conn: sqlite3.Connection, c: Customer, balance_today: float) -> None:
    conn.execute(
        "INSERT INTO customers (id, first_name, last_name, birth_year, city, language, products, "
        "consent_personalization, ground_truth) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (c.id, c.first_name, c.last_name, c.birth_year, c.city, c.language, json.dumps(c.products),
         1 if c.consent_personalization else 0, json.dumps(c.ground_truth)),
    )
    conn.execute("INSERT INTO accounts (customer_id, balance_today) VALUES (?, ?)", (c.id, balance_today))


def insert_transactions(conn: sqlite3.Connection, txs: list[Transaction]) -> None:
    conn.executemany(
        "INSERT INTO transactions (id, customer_id, date, amount, category, counterparty) VALUES (?, ?, ?, ?, ?, ?)",
        [(t.id, t.customer_id, t.date.isoformat(), round(t.amount, 2), t.category, t.counterparty) for t in txs],
    )


def insert_user(conn: sqlite3.Connection, username: str, password_hash: str, role: str,
                customer_id: int | None) -> None:
    conn.execute(
        "INSERT INTO users (username, password_hash, role, customer_id) VALUES (?, ?, ?, ?)",
        (username, password_hash, role, customer_id),
    )
