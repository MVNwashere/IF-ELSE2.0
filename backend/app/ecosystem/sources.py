"""Inbound data sources: the data passport in the other direction. Data KBC reads, with the customer's OK.

Each source (sources.json) says what it reads, for which goals, how sensitive it is and how long access lasts.
Connecting is purpose-bound (one goal) and expires. The public company register (KBO) needs no consent but is
still shown. Values are SIMULATED from the customer's synthetic profile: no real connection is made.

Engine contract (for context.py and nudges):

    values_for(conn, customer_id, as_of) -> dict[str, str | float]

returns only values of sources that are connected and not expired at `as_of` (plus public ones). Keys are listed
per source in sources.json ("values").
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .. import db
from . import store
from .models import SOURCE_ID_PATTERN, PLAYBOOK_ID_PATTERN, SourceHint, SourcesResponse, SourceView

HERE = Path(__file__).resolve().parent


class SourceDef(BaseModel):
    id: str = Field(pattern=SOURCE_ID_PATTERN)
    name: str
    provider: str
    kind: Literal["psd2", "government", "partner", "public", "utility"]
    catalogue_id: str | None = None
    reads: list[str]
    goals: list[str]
    sensitivity: Literal["low", "medium", "high"]
    needs_consent: bool
    consent_days: int = Field(ge=0, le=730)
    why: str
    values: list[str]


class StepHintDef(BaseModel):
    playbook: str = Field(pattern=PLAYBOOK_ID_PATTERN)
    step: str
    source: str = Field(pattern=SOURCE_ID_PATTERN)
    prompt: str


@dataclass(frozen=True)
class SourceCatalogue:
    sources: dict[str, SourceDef]
    step_hints: dict[tuple[str, str], StepHintDef]


class SourceError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


@lru_cache(maxsize=1)
def catalogue() -> SourceCatalogue:
    raw = json.loads((HERE / "sources.json").read_text(encoding="utf-8"))
    sources = {s["id"]: SourceDef.model_validate(s) for s in raw["sources"]}
    hints = [StepHintDef.model_validate(h) for h in raw["step_hints"]]
    problems = [f"hint {h.playbook}/{h.step}: unknown source {h.source}" for h in hints if h.source not in sources]
    problems += [f"source {s.id}: needs consent but has no expiry" for s in sources.values()
                 if s.needs_consent and s.consent_days <= 0]
    if problems:
        raise ValueError("Invalid sources.json:\n  " + "\n  ".join(problems))
    return SourceCatalogue(sources=sources, step_hints={(h.playbook, h.step): h for h in hints})


# ---- simulated values ----------------------------------------------------------------------------------------------


def _simulate(source_id: str, customer, txs, as_of: dt.date) -> dict[str, str | float]:
    """Deterministic, plausible values derived from the customer's own synthetic data. Clearly not real."""
    txs = [t for t in txs if t.date <= as_of]
    seed = (customer.id * 7919) % 97
    recent = [t for t in txs if (as_of - t.date).days <= 365]
    income = sum(t.amount for t in recent if t.category in ("salary", "invoice_income", "pension") and t.amount > 0)
    utilities = -sum(t.amount for t in recent if t.category == "utilities" and t.amount < 0)
    invoices = [t for t in txs if t.category == "invoice_income" and t.amount > 0]
    age = as_of.year - customer.birth_year
    if source_id == "psd2_other_banks":
        return {"other_bank_accounts": 1 + seed % 2, "other_bank_balance_eur": float(2500 + seed * 140)}
    if source_id == "ebox":
        out: dict[str, str | float] = {"ebox_letters": 2 + seed % 4}
        if invoices:
            first = invoices[0].date
            yearly = sum(t.amount for t in invoices if (as_of - t.date).days <= 365)
            out["regularisation_eur"] = round(max(yearly, 12_000) * 0.205 * 0.6, -1)
            out["regularisation_due"] = (dt.date(first.year + 2, first.month, 1) + dt.timedelta(days=60)).isoformat()
        return out
    if source_id == "billit_invoices":
        if not invoices:
            return {"open_invoices_count": 0, "open_invoices_eur": 0.0, "overdue_invoices_count": 0}
        avg = sum(t.amount for t in invoices[-6:]) / len(invoices[-6:])
        n_open = 1 + seed % 3
        return {"open_invoices_count": n_open, "open_invoices_eur": round(avg * n_open, 2),
                "overdue_invoices_count": seed % 2}
    if source_id == "kbo":
        if not invoices:
            return {}
        return {"company_number": f"BE 07{customer.id % 100:02d}.{(seed * 37) % 1000:03d}.{(seed * 53) % 1000:03d}",
                "company_start_date": invoices[0].date.isoformat(), "company_activity": "Consultancy (NACE 70.229)"}
    if source_id == "mypension":
        statutory = round(min(max(income / 12 * 0.6, 1100), 2400), -1)
        return {"pension_statutory_monthly_eur": statutory,
                "pension_supplementary_eur": float(round(max(0, age - 25) * 1450 + seed * 50, -2)),
                "pension_date": dt.date(customer.birth_year + 65, 1, 1).isoformat()}
    if source_id == "epc_flanders":
        labels = "BCCDDDE"
        label = labels[seed % len(labels)]
        return {"epc_label": label, "epc_kwh_m2": {"B": 180, "C": 260, "D": 370, "E": 450}[label] + seed % 20}
    if source_id == "fluvius_meter":
        return {"electricity_kwh_year": round(max(utilities, 600) * 0.45 / 0.35 * 12 / 12, -1),
                "gas_kwh_year": round(max(utilities, 600) * 0.55 / 0.11, -2), "peak_kw": 2.5 + (seed % 30) / 10}
    return {}


def _status(row, src: SourceDef, as_of: dt.date) -> str:
    if not src.needs_consent:
        return "public"
    if not row or row["status"] != "active":
        return "available"
    if dt.date.fromisoformat(row["connected_on"]) > as_of:
        return "available"   # time travel: not connected yet at this date
    return "connected" if dt.date.fromisoformat(row["expires_on"]) >= as_of else "expired"


def _load(conn, customer_id: int):
    customer = db.get_customer(conn, customer_id)
    if not customer:
        raise SourceError(404, "Customer not found")
    return customer, db.get_transactions(conn, customer_id)


def values_for(conn, customer_id: int, as_of: dt.date) -> dict[str, str | float]:
    """Values of connected (not expired) and public sources at `as_of`. Nothing from a disconnected source."""
    cat = catalogue()
    rows = {r["source_id"]: r for r in store.sources(conn, customer_id)}
    live = [s for s in cat.sources.values() if _status(rows.get(s.id), s, as_of) in ("connected", "public")]
    if not live:
        return {}
    customer, txs = _load(conn, customer_id)
    out: dict[str, str | float] = {}
    for s in live:
        out.update(_simulate(s.id, customer, txs, as_of))
    return out


def connected_ids(conn, customer_id: int, as_of: dt.date) -> set[str]:
    cat = catalogue()
    rows = {r["source_id"]: r for r in store.sources(conn, customer_id)}
    return {s.id for s in cat.sources.values() if _status(rows.get(s.id), s, as_of) in ("connected", "public")}


def hint_for(playbook_id: str, step_id: str, connected: set[str]) -> SourceHint | None:
    cat = catalogue()
    h = cat.step_hints.get((playbook_id, step_id))
    if not h:
        return None
    return SourceHint(source_id=h.source, name=cat.sources[h.source].name, prompt=h.prompt,
                      connected=h.source in connected)


def sources_response(conn, customer_id: int, as_of: dt.date) -> SourcesResponse:
    cat = catalogue()
    rows = {r["source_id"]: r for r in store.sources(conn, customer_id)}
    customer, txs = None, None
    out = []
    for s in cat.sources.values():
        row = rows.get(s.id)
        status = _status(row, s, as_of)
        values: dict[str, str | float] = {}
        if status in ("connected", "public"):
            if customer is None:
                customer, txs = _load(conn, customer_id)
            values = _simulate(s.id, customer, txs, as_of)
        bound = row is not None and status in ("connected", "expired")
        out.append(SourceView(
            source_id=s.id, name=s.name, provider=s.provider, kind=s.kind, reads=s.reads, goals=s.goals,
            sensitivity=s.sensitivity, needs_consent=s.needs_consent, consent_days=s.consent_days, why=s.why,
            status=status,
            connected_on=dt.date.fromisoformat(row["connected_on"]) if bound else None,
            expires_on=dt.date.fromisoformat(row["expires_on"]) if bound else None,
            purpose=row["purpose"] if bound else "", playbook_id=row["playbook_id"] if bound else None,
            values=values,
        ))
    return SourcesResponse(sources=out, connected=sum(1 for v in out if v.status == "connected"))


def connect(conn, customer_id: int, source_id: str, playbook_id: str, purpose: str, as_of: dt.date) -> None:
    from .registry import registry
    cat = catalogue()
    src = cat.sources.get(source_id)
    if not src:
        raise SourceError(404, "Unknown data source")
    if not src.needs_consent:
        raise SourceError(409, "This is public data: there is nothing to connect")
    pb = registry().playbooks.get(playbook_id)
    if not pb:
        raise SourceError(404, "Unknown goal")
    if playbook_id not in src.goals:
        raise SourceError(422, f"{src.name} is not used for the goal '{pb.title}'")   # purpose binding
    text = purpose.strip() or f"{src.name} for your goal '{pb.title}'"
    store.insert_source(conn, customer_id, source_id, playbook_id, text[:200], as_of,
                        as_of + dt.timedelta(days=src.consent_days))


def disconnect(conn, customer_id: int, source_id: str, as_of: dt.date) -> None:
    if source_id not in catalogue().sources:
        raise SourceError(404, "Unknown data source")
    store.disconnect_source(conn, customer_id, source_id, as_of)
