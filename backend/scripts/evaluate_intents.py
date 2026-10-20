"""Offline evaluation of intent detection against the injected goal scenarios and near misses.

Run from backend/:  py -3.12 -m scripts.evaluate_intents [--n 1000] [--seed 42]

Generates the synthetic portfolio in memory (same generator and seed as the database), runs intent.detect() at
TODAY for every customer and compares with the ground truth:
  - "goal:<playbook_id>" events injected by synth/generate.py, and
  - "baby" events (birth in the last 330 days) as truth for new_baby, and
  - "idle_cash" events as truth for retire_well (age 50-64) and peace_of_mind (65+).
"near_miss:<playbook_id>" customers look like that goal but aren't: they are negatives for it, and the
near-miss false-positive rate shows how often the detector falls for the look-alike.
Goals without any injected truth are reported as detection counts only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import time
from collections import Counter

from app.ecosystem.context import build_context
from app.ecosystem.intent import DETECTORS, detect
from synth.demo_customers import demo_customers
from synth.generate import TODAY, make_regular

NO_TRUTH = {"get_paid"}   # late clients come from the base freelancer patterns, not from an injected scenario


def truth_for(gt: dict, as_of: dt.date, age: int | None = None) -> set[str]:
    out = set()
    for e in gt.get("events", []):
        name, date = e.get("type", ""), e.get("date")
        d = dt.date.fromisoformat(date) if date else as_of
        if name.startswith("goal:") and d <= as_of:
            out.add(name.split(":", 1)[1])
        elif name == "baby" and 0 <= (as_of - d).days <= 330:
            out.add("new_baby")
        elif name == "idle_cash" and age is not None:   # idle money: the wealth goals for the right age
            if 50 <= age <= 64:
                out.add("retire_well")
            elif age >= 65:
                out.add("peace_of_mind")
    return out


def near_misses_for(gt: dict, as_of: dt.date) -> set[str]:
    """Goals this customer only resembles (minus any goal that is also really true for them)."""
    return {e["type"].split(":", 1)[1] for e in gt.get("events", [])
            if e.get("type", "").startswith("near_miss:") and dt.date.fromisoformat(e["date"]) <= as_of}


def portfolio(n: int, seed: int):
    for cid in range(1, n + 1):
        yield make_regular(cid, seed)
    for _, c, txs, bal in demo_customers():
        yield c, txs, bal


def evaluate(n: int = 1000, seed: int = 42, as_of: dt.date = TODAY) -> dict:
    tp, fp, fn, detected, truth_n = Counter(), Counter(), Counter(), Counter(), Counter()
    near_n, near_fp = Counter(), Counter()
    goals_seen: set[str] = set(DETECTORS)
    customers = 0
    started = time.perf_counter()
    for customer, txs, balance in portfolio(n, seed):
        txs = sorted(txs, key=lambda t: (t.date, t.counterparty))
        for i, t in enumerate(txs):
            t.id = i + 1
        customers += 1
        found = {pid for pid, _ in detect(build_context(customer, txs, balance, as_of))}
        truth = truth_for(customer.ground_truth, as_of, as_of.year - customer.birth_year)
        near = near_misses_for(customer.ground_truth, as_of) - truth
        goals_seen |= truth | near
        for pid in goals_seen:
            hit, real = pid in found, pid in truth
            detected[pid] += hit
            truth_n[pid] += real
            tp[pid] += hit and real
            fp[pid] += hit and not real
            fn[pid] += real and not hit
            if pid in near:
                near_n[pid] += 1
                near_fp[pid] += hit
    ms = (time.perf_counter() - started) * 1000
    goals = {}
    for pid in sorted(goals_seen, key=lambda p: (p not in DETECTORS, p)):
        prec = tp[pid] / (tp[pid] + fp[pid]) if tp[pid] + fp[pid] else None
        rec = tp[pid] / truth_n[pid] if truth_n[pid] else None
        goals[pid] = {"detector": pid in DETECTORS, "detected": detected[pid], "truth": truth_n[pid],
                      "tp": tp[pid], "fp": fp[pid], "fn": fn[pid],
                      "precision": None if pid in NO_TRUTH or not truth_n[pid] else prec, "recall": rec,
                      "near_misses": near_n[pid], "near_miss_fp": near_fp[pid],
                      "near_miss_fp_rate": near_fp[pid] / near_n[pid] if near_n[pid] else None}
    return {"customers": customers, "as_of": as_of.isoformat(), "ms": round(ms), "goals": goals}


def _pct(x: float | None) -> str:
    return "   n/a" if x is None else f"{x * 100:5.1f}%"


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate intent detection against injected goal scenarios")
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    r = evaluate(args.n, args.seed)
    print(f"Intent detection at {r['as_of']} over {r['customers']} customers ({r['ms']} ms)")
    print(f"  {'goal':17s} {'detected':>8s} {'truth':>6s} {'TP':>4s} {'FP':>4s} {'FN':>4s} {'precision':>10s} "
          f"{'recall':>7s} {'near misses':>12s} {'fooled':>7s}")
    for pid, g in r["goals"].items():
        name = pid if g["detector"] else pid + "*"
        print(f"  {name:17s} {g['detected']:8d} {g['truth']:6d} {g['tp']:4d} {g['fp']:4d} {g['fn']:4d} "
              f"{_pct(g['precision']):>10s} {_pct(g['recall']):>7s} {g['near_misses']:12d} "
              f"{_pct(g['near_miss_fp_rate']):>7s}")
    print("  fooled = share of near-miss customers (look-alikes) the detector still flagged for that goal")
    print("  * = no detector yet; precision n/a = no injected truth")


if __name__ == "__main__":
    main()
