"""On-demand, fingerprint-invalidated recalculation; callable without HTTP or frontend code."""
from __future__ import annotations

import datetime as dt
import hashlib
import json

from . import normalization, storage
from .inference import InferenceProvider, RuleInference, conditions
from .metrics import calculate
from .models import CustomerState
from .patterns import detect, transaction_events

ALGORITHM_VERSION = "customer-state-1"
DOMAINS = frozenset({"financial_position", "income", "expenses", "cash_flow", "savings", "debt", "spending",
                     "recurring_payments", "subscriptions", "patterns", "changes", "events", "inferences",
                     "risks", "opportunities"})


def get_state(conn, customer_id: int, as_of: dt.date, *, balance_reference: dt.date,
              provider: InferenceProvider | None = None) -> CustomerState:
    """Caller owns the DB transaction. Raw-source corrections invalidate the entire requested snapshot."""
    # Read all source tables and publish their derived snapshot atomically. SQLite has one
    # writer; reserve it before reading so concurrent rebuilds cannot publish mixed sources.
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    provider = provider or RuleInference()
    raw = normalization.load(conn, customer_id, as_of, balance_reference)
    source = {"observations": raw.model_dump(mode="json"), "balance_reference": balance_reference.isoformat()}
    fingerprint = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
    version = f"{ALGORITHM_VERSION}:{provider.version}"
    existing = storage.cached(conn, customer_id, as_of.isoformat(), version, fingerprint)
    if existing:
        return existing
    signals = normalization.normalize(raw)
    euro = [s for s in signals if s.currency == "EUR"]
    patterns, changes = detect(euro, as_of)
    metrics, metric_changes = calculate(raw, euro, patterns, as_of)
    events = transaction_events(euro)
    # IDs are based on source evidence, never recalculation time. Full history is replayable.
    changes = sorted({c.id: c for c in changes+metric_changes}.values(), key=lambda c: (c.detected_at, c.id))
    last = max((s.date for s in signals), default=None)
    last_account = max((a.observed_at for a in raw.accounts if a.source != "legacy_ledger_reconstruction"), default=None)
    freshness = {"latest_transaction_date": last.isoformat() if last else None,
                 "transaction_age_days": (as_of-last).days if last else None,
                 "latest_account_observation_date": last_account.isoformat() if last_account else None,
                 "source_hash": fingerprint, "algorithm_version": version,
                 "excluded_non_eur_transaction_count": len(signals)-len(euro),
                 "complete_month_count": len(metrics["cash_flow"].monthly),
                 "balance_reference": balance_reference.isoformat(),
                 "account_observation_age_days": {a.account_id: (as_of-a.observed_at).days for a in sorted(raw.accounts, key=lambda a: a.observed_at)
                                                    if a.source != "legacy_ledger_reconstruction"},
                 "legacy_balance_reference_age_days": max(0, (as_of-balance_reference).days),
                 "projection_is_estimate": True}
    state = CustomerState(customer_id=customer_id, as_of=as_of, generated_at=dt.datetime.now(dt.timezone.utc),
                          data_period={"from": min((s.date for s in signals), default=None), "to": last},
                          freshness=freshness, observations=raw, signals=signals, patterns=patterns,
                          changes=changes, events=events, inferences=[], risks=[], opportunities=[], **metrics)
    state.inferences = provider.infer(state)
    state.risks, state.opportunities = conditions(state)
    storage.save(conn, state, version, fingerprint)
    return state


def get_domain(state: CustomerState, domain: str):
    key = domain.replace("-", "_")
    key = {"overview": "financial_position", "recurring": "recurring_payments"}.get(key, key)
    if key not in DOMAINS:
        raise KeyError(domain)
    return {"customer_id": state.customer_id, "as_of": state.as_of, "generated_at": state.generated_at,
            "currency": state.currency, "freshness": state.freshness, "domain": key,
            "data": getattr(state, key), "provenance": state.provenance}
