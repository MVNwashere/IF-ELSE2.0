"""Blind holdout evaluation of intent detection.

Runs app.ecosystem.intent.detect() on the hand-designed holdout set (synth/holdout.py, written without looking at the
detector rules) and reports per goal: precision, recall and the hard-negative false-positive rate (share of
`near_miss:<goal>` customers on which <goal> still fires), plus macro averages over the implemented goals.

Run from backend/:
    py -3.12 -m scripts.evaluate_holdout [--seed 7] [--out ../data/holdout_report.json]
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from app.ecosystem import intent
from app.ecosystem.context import build_context
from synth.holdout import AS_OF, GOALS, holdout_customers

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "data" / "holdout_report.json"


def _ids(result) -> set[str]:
    """detect() returns [(playbook_id, Detection), ...]; tolerate a dict with a 'detected' list too."""
    if isinstance(result, dict):
        result = result.get("detected", [])
    out = set()
    for item in result:
        if isinstance(item, (tuple, list)):
            out.add(item[0])
        elif isinstance(item, str):
            out.add(item)
        else:
            out.add(getattr(item, "playbook_id", None) or getattr(item, "id", None))
    return {x for x in out if x}


def _ratio(a: int, b: int) -> float | None:
    return round(a / b, 3) if b else None


def evaluate(seed: int = 7) -> dict:
    implemented = set(getattr(intent, "DETECTORS", {}).keys())
    data = holdout_customers(seed)
    tp, fp, fn, pos, near, near_fp = (Counter() for _ in range(6))
    errors = 0
    t0 = time.perf_counter()
    for customer, txs, balance in data:
        types = [e["type"] for e in customer.ground_truth.get("events", [])]
        truth = {t.split(":", 1)[1] for t in types if t.startswith("goal:")}
        nears = {t.split(":", 1)[1] for t in types if t.startswith("near_miss:")}
        try:
            found = _ids(intent.detect(build_context(customer, txs, balance, AS_OF)))
        except Exception:  # a crashing detector counts as "nothing found" for this customer
            errors += 1
            found = set()
        for g in GOALS:
            pos[g] += g in truth
            near[g] += g in nears
            if g in found and g in truth:
                tp[g] += 1
            elif g in found:
                fp[g] += 1
                near_fp[g] += g in nears
            elif g in truth:
                fn[g] += 1
    ms = round((time.perf_counter() - t0) * 1000)

    goals = {}
    for g in GOALS:
        row = {"implemented": g in implemented, "positives": pos[g], "hard_negatives": near[g],
               "tp": tp[g], "fp": fp[g], "fn": fn[g], "hard_negative_fp": near_fp[g],
               "precision": _ratio(tp[g], tp[g] + fp[g]), "recall": _ratio(tp[g], pos[g]),
               "hard_negative_fpr": _ratio(near_fp[g], near[g])}
        goals[g] = row
    impl = [r for r in goals.values() if r["implemented"]]

    def macro(key: str) -> float | None:
        # precision of a goal that never fires is undefined; count it as 0 so silence isn't rewarded
        vals = [(r[key] if r[key] is not None else 0.0) for r in impl]
        return round(sum(vals) / len(vals), 3) if vals else None

    return {"as_of": AS_OF.isoformat(), "seed": seed, "customers": len(data), "ms": ms, "errors": errors,
            "implemented": len(impl), "not_implemented": [g for g in GOALS if g not in implemented],
            "macro": {"precision": macro("precision"), "recall": macro("recall"),
                      "hard_negative_fpr": macro("hard_negative_fpr")},
            "goals": goals}


def _pct(x: float | None) -> str:
    return "   -" if x is None else f"{x * 100:4.0f}%"


def main() -> None:
    ap = argparse.ArgumentParser(description="Blind holdout evaluation of intent detection")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    r = evaluate(args.seed)
    print(f"Holdout at {r['as_of']}: {r['customers']} customers, {r['ms']} ms, {r['errors']} detector errors")
    print(f"  {'goal':17s} {'pos':>3s} {'hn':>3s} {'TP':>3s} {'FP':>3s} {'FN':>3s} {'prec':>5s} {'recall':>6s} {'HN-FPR':>6s}")
    for g, row in r["goals"].items():
        if not row["implemented"]:
            print(f"  {g:17s} {row['positives']:3d} {row['hard_negatives']:3d}  not implemented")
            continue
        print(f"  {g:17s} {row['positives']:3d} {row['hard_negatives']:3d} {row['tp']:3d} {row['fp']:3d} "
              f"{row['fn']:3d} {_pct(row['precision']):>5s} {_pct(row['recall']):>6s} "
              f"{_pct(row['hard_negative_fpr']):>6s}")
    m = r["macro"]
    print(f"  macro over {r['implemented']} implemented goals: precision {_pct(m['precision'])}, "
          f"recall {_pct(m['recall'])}, hard-negative FPR {_pct(m['hard_negative_fpr'])}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(r, indent=2), encoding="utf-8")
    print(f"  wrote {args.out}")


if __name__ == "__main__":
    main()
