"""Offline evaluation against injected ground truth.

Run from backend/:  py -3.12 -m scripts.evaluate [--db path]

For every synthetic customer we compare, as of the last transaction date:
  - persona:  is the injected persona present in the persona mix (recall) / is the dominant persona injected (precision)
  - cards:    precision@5 and recall of card types against injected event scenarios
Also reports scoring throughput and the projection to 2.3M customers.
"""
from __future__ import annotations

import argparse
import datetime as dt
import time
from collections import Counter, defaultdict

from app import db
from app.engine import pipeline
from app.engine.persona import dominant

# scenario name (ground_truth) -> card types that should fire for it
EVENT_TO_CARD = {
    "insurance_renewal": {"insurance_renewal"},
    "price_increase": {"price_increase"},
    "duplicate_charge": {"duplicate_charge"},
    "cashflow_squeeze": {"cashflow_squeeze", "runway"},
    "idle_cash": {"idle_cash"},
}
NEUTRAL_CARD_TYPES = {"life_event", "scam_awareness", "vat_reserve",  # no injected ground truth: not scored
                      "pension_savings", "late_client", "protection_gap", "new_payee"}
PERSONA_SCENARIOS = {"student", "young_professional", "young_family", "freelancer", "retiree"}
PORTFOLIO = 2_300_000


INSURANCE_WINDOW_DAYS = 45   # the card only shows this close to the renewal date (cards.py)


def _scenarios(gt: dict, as_of: dt.date) -> tuple[set[str], set[str]]:
    """Return (personas, events) from a ground_truth dict, tolerant of shape.

    An insurance_renewal is only expected when its renewal date is within the card's window of as_of.
    """
    personas: set[str] = set()
    events: set[str] = set()
    for key in ("personas", "scenarios"):
        for s in gt.get(key, []) or []:
            name = s if isinstance(s, str) else s.get("type") or s.get("name")
            if name in PERSONA_SCENARIOS:
                personas.add(name)
            elif name in EVENT_TO_CARD:
                events.add(name)
    for s in gt.get("events", []) or []:
        name = s if isinstance(s, str) else s.get("type") or s.get("name")
        if name not in EVENT_TO_CARD:
            continue
        if name == "insurance_renewal" and isinstance(s, dict) and s.get("date"):
            days = (dt.date.fromisoformat(s["date"]) - as_of).days
            if not (0 <= days <= INSURANCE_WINDOW_DAYS):
                continue
        events.add(name)
    return personas, events


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()

    persona_hits = persona_total = dominant_hits = dominant_total = 0
    card_tp = card_fp = card_fn = 0
    per_event: dict[str, Counter] = defaultdict(Counter)
    n = 0
    started = time.perf_counter()
    with db.tx(args.db) as conn:
        db.init_schema(conn)  # migrate databases built by older versions
        for cid in db.all_customer_ids(conn):
            customer = db.get_customer(conn, cid)
            txs = db.get_transactions(conn, cid)
            if not customer or not txs or cid >= 9000:
                continue
            balance = db.get_balance_today(conn, cid)
            prefs = db.get_prefs(conn, cid)
            home = pipeline.build_home(customer, txs, balance, prefs, txs[-1].date)
            n += 1

            gt_personas, gt_events = _scenarios(customer.ground_truth, txs[-1].date)
            mix = {p.persona for p in home.persona_mix}
            for p in gt_personas:
                persona_total += 1
                persona_hits += p in mix
            if gt_personas:
                dominant_total += 1
                dominant_hits += dominant(home.persona_mix) in gt_personas

            shown = [c.card_type for c in home.feed.cards[: args.k]]
            expected_types = set().union(*(EVENT_TO_CARD[e] for e in gt_events)) if gt_events else set()
            for ev in gt_events:
                hit = any(t in EVENT_TO_CARD[ev] for t in shown)
                per_event[ev]["hit" if hit else "miss"] += 1
                card_tp += hit
                card_fn += not hit
            for t in shown:
                if t in NEUTRAL_CARD_TYPES:
                    continue  # not part of injected scenarios; neither right nor wrong
                if t not in expected_types:
                    card_fp += 1
    elapsed = time.perf_counter() - started

    print(f"customers scored: {n} in {elapsed*1000:.0f} ms ({elapsed/max(n,1)*1000:.2f} ms each)")
    print(f"projected for {PORTFOLIO:,} customers: {elapsed/max(n,1)*PORTFOLIO/60:.1f} min single-core")
    print()
    print(f"persona recall   : {persona_hits}/{persona_total} = {persona_hits/max(persona_total,1):.2f}")
    print(f"dominant precision: {dominant_hits}/{dominant_total} = {dominant_hits/max(dominant_total,1):.2f}")
    prec = card_tp / max(card_tp + card_fp, 1)
    rec = card_tp / max(card_tp + card_fn, 1)
    print(f"cards precision@{args.k}: {prec:.2f}   recall: {rec:.2f}")
    for ev, c in sorted(per_event.items()):
        print(f"  {ev:<20} hit {c['hit']:>4}  miss {c['miss']:>4}")


if __name__ == "__main__":
    main()
