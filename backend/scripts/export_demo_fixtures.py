"""Refresh the frontend's demo engine fixtures (frontend/src/demo-data/customers.json) from the backend.

`npm run dev:mock` and the browser tests run without a backend, on snapshots of what the API returned. When the home
composition changes, run this so the demo shows the same screens as the live app:

    py -3.12 -m scripts.export_demo_fixtures

For every customer and snapshot date already in the file it replaces the home screen and the goals list, and it
rebuilds the tile palette (props for every tile, used when the customer places one that the layout didn't pick).
Timeline, goal templates, nudges and data sources are left as they are. The database is only read: the transaction
is rolled back, so the goal-suggestion "shown" counters don't move.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from app import db, main
from app.ecosystem import service as ecosystem
from app.engine import layout
from app.engine.features import compute_features
from app.engine.persona import infer_persona_mix

FIXTURES = Path(__file__).resolve().parents[2] / "frontend" / "src" / "demo-data" / "customers.json"


def _keep(fresh: dict, old: dict) -> dict:
    """Only the keys the demo engine already knows: new API fields stay out of the frozen shape."""
    return {k: fresh[k] for k in old if k in fresh}


def _palette(conn, customer_id: int, at: dt.date, cards) -> dict:
    customer = db.get_customer(conn, customer_id)
    txs = db.get_transactions(conn, customer_id)
    prefs = db.get_prefs(conn, customer_id)
    features = compute_features(customer, txs, db.get_balance_today(conn, customer_id), at)
    mix = infer_persona_mix(features, prefs.declared, prefs.facts, prefs.corrections)
    ctx = {"features": features, "persona_mix": mix, "customer": customer, "txs": txs, "as_of": at, "cards": cards,
           "weights": {p.persona: p.weight for p in mix}}
    return {name: {"component": name, "size": entry["size"], "props": entry["props"](ctx), "pinned": False}
            for name, entry in layout.REGISTRY.items()}


def main_() -> None:
    data = json.loads(FIXTURES.read_text(encoding="utf-8"))
    conn = db.connect()
    try:
        for username, fixture in data.items():
            user = db.get_user(conn, username)
            if user is None:
                print(f"skip {username}: no such demo user")
                continue
            cid = user["customer_id"]
            declared = db.get_prefs(conn, cid).declared
            for snap in fixture["snapshots"]:
                at = dt.date.fromisoformat(snap["date"])
                home, _ = main._load_and_build(cid, at, touch=False)
                snap["home"] = _keep(json.loads(home.model_dump_json()), snap["home"])
                goals = ecosystem.goals_response(conn, cid, at, declared)
                conn.rollback()   # goals_response counts the suggestions as shown: an export must not
                snap["goals"] = _keep(json.loads(goals.model_dump_json()), snap["goals"])
            today, _ = main._load_and_build(cid, None, touch=False)
            fresh = _palette(conn, cid, today.as_of, today.feed.cards)
            fixture["tiles"] = {name: json.loads(json.dumps(section, default=str))
                                for name, section in fresh.items() if name in fixture["tiles"]}
            print(f"{username}: {len(fixture['snapshots'])} snapshots refreshed")
    finally:
        conn.rollback()
        conn.close()
    FIXTURES.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main_()
