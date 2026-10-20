"""Time-based and freelance signals derived from a CustomerContext: deadlines and forecasts.

Contract (consumed by nudges.py and the journeys; owned by the signals work):

    upcoming_deadlines(ctx, horizon_days=45) -> list[Deadline]   # sorted by date
    forecasts(ctx) -> list[Forecast]                             # e.g. the social-contribution regularisation gap

Pure functions, no I/O. Amounts are illustrative estimates from the customer's own data.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .context import CustomerContext


@dataclass
class Deadline:
    kind: str                 # "vat_return" | "advance_tax" | "insurance_renewal" | "pension_savings" | "trip" | ...
    date: dt.date
    title: str                # "Q3 VAT return"
    amount_eur: float | None = None
    shortfall_eur: float | None = None   # money missing for this deadline, if any (drives urgency)
    evidence: list[str] = field(default_factory=list)
    playbook_id: str | None = None       # the goal that takes care of it, if any


@dataclass
class Forecast:
    kind: str                 # "social_contribution_regularisation" | "client_concentration" | ...
    title: str
    amount_eur: float | None = None
    due: dt.date | None = None
    evidence: list[str] = field(default_factory=list)
    playbook_id: str | None = None


def upcoming_deadlines(ctx: CustomerContext, horizon_days: int = 45) -> list[Deadline]:
    return []


def forecasts(ctx: CustomerContext) -> list[Forecast]:
    return []
