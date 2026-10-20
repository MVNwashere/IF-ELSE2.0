"""SQLite storage for goals, steps, consent grants, partner events and the ledger. Bound parameters only.

Every customer-facing read and write takes the customer id from the session and filters on it, so a goal or
grant id from another customer simply isn't found (no IDOR).
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS eco_goals (
  id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  playbook_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active','completed','cancelled')),
  origin TEXT NOT NULL CHECK (origin IN ('detected','stated')),
  evidence TEXT NOT NULL DEFAULT '[]',
  created_on TEXT NOT NULL,
  target_date TEXT
);
CREATE INDEX IF NOT EXISTS ix_eco_goals_customer ON eco_goals(customer_id);
CREATE TABLE IF NOT EXISTS eco_steps (
  goal_id INTEGER NOT NULL REFERENCES eco_goals(id) ON DELETE CASCADE,
  step_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('proposed','approved','in_progress','done','declined','blocked')),
  already_held INTEGER NOT NULL DEFAULT 0,
  ref TEXT NOT NULL DEFAULT '',
  result TEXT NOT NULL DEFAULT '',
  grant_id INTEGER,
  started_at TEXT,
  updated_at TEXT,
  PRIMARY KEY (goal_id, step_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_eco_steps_ref ON eco_steps(ref) WHERE ref != '';
CREATE TABLE IF NOT EXISTS eco_grants (
  id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  goal_id INTEGER NOT NULL REFERENCES eco_goals(id) ON DELETE CASCADE,
  step_id TEXT NOT NULL,
  partner_id TEXT NOT NULL,
  fields TEXT NOT NULL,
  purpose TEXT NOT NULL,
  granted_on TEXT NOT NULL,
  expires_on TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active','revoked')),
  revoked_on TEXT
);
CREATE INDEX IF NOT EXISTS ix_eco_grants_customer ON eco_grants(customer_id);
CREATE TABLE IF NOT EXISTS eco_events (
  id INTEGER PRIMARY KEY,
  at TEXT NOT NULL,
  partner_id TEXT NOT NULL,
  event_id TEXT,
  customer_id INTEGER,
  goal_id INTEGER,
  step_id TEXT,
  kind TEXT NOT NULL,
  summary TEXT NOT NULL,
  verified INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_eco_events_idem ON eco_events(partner_id, event_id) WHERE event_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS eco_ledger (
  id INTEGER PRIMARY KEY,
  at TEXT NOT NULL,
  customer_id INTEGER NOT NULL,
  goal_id INTEGER NOT NULL,
  step_id TEXT NOT NULL,
  party TEXT NOT NULL CHECK (party IN ('customer','kbc','partner')),
  partner_id TEXT,
  metric TEXT NOT NULL,
  value REAL NOT NULL,
  label TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_eco_ledger_goal ON eco_ledger(goal_id);
CREATE TABLE IF NOT EXISTS eco_sources (
  id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  source_id TEXT NOT NULL,
  playbook_id TEXT NOT NULL,
  purpose TEXT NOT NULL,
  connected_on TEXT NOT NULL,
  expires_on TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active','disconnected')),
  disconnected_on TEXT
);
CREATE INDEX IF NOT EXISTS ix_eco_sources_customer ON eco_sources(customer_id);
CREATE TABLE IF NOT EXISTS eco_shown (
  customer_id INTEGER NOT NULL,
  playbook_id TEXT NOT NULL,
  first_shown TEXT NOT NULL,
  PRIMARY KEY (customer_id, playbook_id)
);
"""

# columns added after the first release: (table, column, type). Fixed identifiers, never user input.
_MIGRATIONS = (
    ("eco_steps", "partner_id", "TEXT"),      # the partner the customer picked among the step's alternatives
    ("eco_steps", "done_on", "TEXT"),         # simulated completion date (time travel aware)
    ("eco_grants", "deleted_at", "TEXT"),     # partner confirmed deletion after revoke/expiry (signed webhook)
)
_ALTER = {
    ("eco_steps", "partner_id"): "ALTER TABLE eco_steps ADD COLUMN partner_id TEXT",
    ("eco_steps", "done_on"): "ALTER TABLE eco_steps ADD COLUMN done_on TEXT",
    ("eco_grants", "deleted_at"): "ALTER TABLE eco_grants ADD COLUMN deleted_at TEXT",
}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    cols = {
        "eco_steps": {r[1] for r in conn.execute("PRAGMA table_info(eco_steps)")},
        "eco_grants": {r[1] for r in conn.execute("PRAGMA table_info(eco_grants)")},
    }
    for table, column, _ in _MIGRATIONS:
        if column not in cols[table]:
            conn.execute(_ALTER[(table, column)])


# ---- goals and steps ---------------------------------------------------------------------------------------------


def insert_goal(conn, customer_id: int, playbook_id: str, origin: str, evidence: list[str], created_on: dt.date,
                target_date: dt.date | None, steps: list[tuple[str, str, bool, str]]) -> int:
    """steps: (step_id, status, already_held, result)"""
    cur = conn.execute(
        "INSERT INTO eco_goals (customer_id, playbook_id, status, origin, evidence, created_on, target_date) "
        "VALUES (?, ?, 'active', ?, ?, ?, ?)",
        (customer_id, playbook_id, origin, json.dumps(evidence), created_on.isoformat(),
         target_date.isoformat() if target_date else None),
    )
    goal_id = int(cur.lastrowid)
    conn.executemany(
        "INSERT INTO eco_steps (goal_id, step_id, status, already_held, result, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        [(goal_id, sid, status, 1 if held else 0, result, now()) for sid, status, held, result in steps],
    )
    return goal_id


def goals(conn, customer_id: int, as_of: dt.date | None = None) -> list[sqlite3.Row]:
    if as_of is None:
        return conn.execute("SELECT * FROM eco_goals WHERE customer_id = ? ORDER BY id", (customer_id,)).fetchall()
    return conn.execute("SELECT * FROM eco_goals WHERE customer_id = ? AND created_on <= ? ORDER BY id",
                        (customer_id, as_of.isoformat())).fetchall()


def goal(conn, customer_id: int, goal_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM eco_goals WHERE id = ? AND customer_id = ?", (goal_id, customer_id)).fetchone()


def set_goal_status(conn, goal_id: int, status: str) -> None:
    conn.execute("UPDATE eco_goals SET status = ? WHERE id = ?", (status, goal_id))


def steps(conn, goal_id: int) -> dict[str, sqlite3.Row]:
    return {r["step_id"]: r for r in conn.execute("SELECT * FROM eco_steps WHERE goal_id = ?", (goal_id,))}


def update_step(conn, goal_id: int, step_id: str, *, status: str | None = None, ref: str | None = None,
                result: str | None = None, grant_id: int | None = None, started_at: str | None = None,
                partner_id: str | None = None, done_on: dt.date | None = None) -> None:
    """Only the given values change (None keeps the current value). One fixed statement, all values bound."""
    conn.execute(
        "UPDATE eco_steps SET status = COALESCE(?, status), ref = COALESCE(?, ref), result = COALESCE(?, result), "
        "grant_id = COALESCE(?, grant_id), started_at = COALESCE(?, started_at), partner_id = COALESCE(?, partner_id), "
        "done_on = COALESCE(?, done_on), updated_at = ? WHERE goal_id = ? AND step_id = ?",
        (status, ref, result, grant_id, started_at, partner_id, done_on.isoformat() if done_on else None, now(),
         goal_id, step_id),
    )


def set_step_done_on(conn, goal_id: int, step_id: str, done_on: dt.date) -> None:
    conn.execute("UPDATE eco_steps SET done_on = ? WHERE goal_id = ? AND step_id = ?",
                 (done_on.isoformat(), goal_id, step_id))


def step_by_ref(conn, ref: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT s.*, g.customer_id, g.playbook_id FROM eco_steps s JOIN eco_goals g ON g.id = s.goal_id "
        "WHERE s.ref = ?", (ref,)).fetchone()


def delete_customer_goals(conn, customer_id: int) -> None:
    ids = [r["id"] for r in conn.execute("SELECT id FROM eco_goals WHERE customer_id = ?", (customer_id,))]
    conn.executemany("DELETE FROM eco_steps WHERE goal_id = ?", [(i,) for i in ids])
    conn.executemany("DELETE FROM eco_ledger WHERE goal_id = ?", [(i,) for i in ids])
    conn.execute("DELETE FROM eco_grants WHERE customer_id = ?", (customer_id,))
    conn.execute("DELETE FROM eco_sources WHERE customer_id = ?", (customer_id,))
    conn.execute("DELETE FROM eco_events WHERE customer_id = ?", (customer_id,))
    conn.execute("DELETE FROM eco_goals WHERE customer_id = ?", (customer_id,))


# ---- consent grants ------------------------------------------------------------------------------------------------


def insert_grant(conn, customer_id: int, goal_id: int, step_id: str, partner_id: str, fields: list[str],
                 purpose: str, granted_on: dt.date, expires_on: dt.date) -> int:
    cur = conn.execute(
        "INSERT INTO eco_grants (customer_id, goal_id, step_id, partner_id, fields, purpose, granted_on, expires_on, "
        "status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')",
        (customer_id, goal_id, step_id, partner_id, json.dumps(fields), purpose, granted_on.isoformat(),
         expires_on.isoformat()),
    )
    return int(cur.lastrowid)


def grants(conn, customer_id: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM eco_grants WHERE customer_id = ? ORDER BY id DESC", (customer_id,)).fetchall()


def grant(conn, grant_id: int, customer_id: int | None = None) -> sqlite3.Row | None:
    if customer_id is None:
        return conn.execute("SELECT * FROM eco_grants WHERE id = ?", (grant_id,)).fetchone()
    return conn.execute("SELECT * FROM eco_grants WHERE id = ? AND customer_id = ?", (grant_id, customer_id)).fetchone()


def revoke_grant(conn, grant_id: int, on: dt.date) -> None:
    conn.execute("UPDATE eco_grants SET status = 'revoked', revoked_on = ? WHERE id = ? AND status = 'active'",
                 (on.isoformat(), grant_id))


# ---- partner events and ledger ----------------------------------------------------------------------------------


def insert_event(conn, partner_id: str, kind: str, summary: str, *, event_id: str | None = None,
                 customer_id: int | None = None, goal_id: int | None = None, step_id: str | None = None,
                 verified: bool = False) -> bool:
    """False if this (partner, event_id) was already processed: webhooks are idempotent."""
    try:
        conn.execute(
            "INSERT INTO eco_events (at, partner_id, event_id, customer_id, goal_id, step_id, kind, summary, verified) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (now(), partner_id, event_id, customer_id, goal_id, step_id, kind, summary[:300], 1 if verified else 0),
        )
        return True
    except sqlite3.IntegrityError:
        return False


def events(conn, limit: int = 40) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM eco_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def insert_ledger(conn, rows: list[tuple]) -> None:
    """rows: (customer_id, goal_id, step_id, party, partner_id, metric, value, label)"""
    conn.executemany(
        "INSERT INTO eco_ledger (at, customer_id, goal_id, step_id, party, partner_id, metric, value, label) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(now(),) + r for r in rows],
    )


def ledger(conn, goal_id: int | None = None) -> list[sqlite3.Row]:
    if goal_id is None:
        return conn.execute("SELECT * FROM eco_ledger").fetchall()
    return conn.execute("SELECT * FROM eco_ledger WHERE goal_id = ?", (goal_id,)).fetchall()


def all_steps_with_goals(conn) -> list[sqlite3.Row]:
    return conn.execute("SELECT s.*, g.playbook_id, g.status AS goal_status, g.customer_id FROM eco_steps s "
                        "JOIN eco_goals g ON g.id = s.goal_id").fetchall()


def confirm_deletion(conn, customer_id: int, goal_id: int, step_id: str, partner_id: str) -> int:
    """A partner confirmed it deleted the data of every revoked grant for this step."""
    cur = conn.execute(
        "UPDATE eco_grants SET deleted_at = ? WHERE customer_id = ? AND goal_id = ? AND step_id = ? AND partner_id = ? "
        "AND deleted_at IS NULL AND status = 'revoked'",
        (now(), customer_id, goal_id, step_id, partner_id),
    )
    return cur.rowcount


# ---- inbound data sources ----------------------------------------------------------------------------------------


def insert_source(conn, customer_id: int, source_id: str, playbook_id: str, purpose: str, connected_on: dt.date,
                  expires_on: dt.date) -> int:
    conn.execute("UPDATE eco_sources SET status = 'disconnected', disconnected_on = ? "
                 "WHERE customer_id = ? AND source_id = ? AND status = 'active'",
                 (connected_on.isoformat(), customer_id, source_id))
    cur = conn.execute(
        "INSERT INTO eco_sources (customer_id, source_id, playbook_id, purpose, connected_on, expires_on, status) "
        "VALUES (?, ?, ?, ?, ?, ?, 'active')",
        (customer_id, source_id, playbook_id, purpose, connected_on.isoformat(), expires_on.isoformat()),
    )
    return int(cur.lastrowid)


def sources(conn, customer_id: int) -> list[sqlite3.Row]:
    """The latest connection per source for this customer."""
    return conn.execute(
        "SELECT * FROM eco_sources WHERE customer_id = ? AND id IN "
        "(SELECT MAX(id) FROM eco_sources WHERE customer_id = ? GROUP BY source_id)",
        (customer_id, customer_id)).fetchall()


def disconnect_source(conn, customer_id: int, source_id: str, on: dt.date) -> int:
    cur = conn.execute("UPDATE eco_sources SET status = 'disconnected', disconnected_on = ? "
                       "WHERE customer_id = ? AND source_id = ? AND status = 'active'",
                       (on.isoformat(), customer_id, source_id))
    return cur.rowcount


# ---- learning loop -----------------------------------------------------------------------------------------------


def mark_shown(conn, customer_id: int, playbook_ids: list[str]) -> None:
    conn.executemany("INSERT OR IGNORE INTO eco_shown (customer_id, playbook_id, first_shown) VALUES (?, ?, ?)",
                     [(customer_id, p, now()) for p in playbook_ids])


def shown_counts(conn) -> dict[str, int]:
    return {r["playbook_id"]: r["n"] for r in
            conn.execute("SELECT playbook_id, COUNT(*) AS n FROM eco_shown GROUP BY playbook_id")}
