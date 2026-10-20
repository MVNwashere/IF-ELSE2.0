"""The ecosystem engine's contract: goals, journeys, consent grants, partner events and the triple-win ledger.

Everything the API returns is one of these models. Identity always comes from the session (see api.py).
"""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

PLAYBOOK_ID_PATTERN = r"^[a-z_]{2,40}$"
STEP_ID_PATTERN = r"^[a-z_]{2,40}$"
PARTNER_ID_PATTERN = r"^[a-z0-9_]{2,40}$"
EVENT_ID_PATTERN = r"^[A-Za-z0-9_.:-]{6,80}$"

StepStatus = Literal["proposed", "approved", "in_progress", "done", "declined", "blocked"]
GoalStatus = Literal["active", "completed", "cancelled"]
GrantStatus = Literal["active", "revoked", "expired"]
ProviderKind = Literal["kbc", "partner"]
ValueShareModel = Literal["lead_fee", "revenue_share", "fee_per_completed_step", "subscription"]


# ---- reference data -----------------------------------------------------------------------------------------


class CatalogueItem(BaseModel):
    """One row of KBC_Ecosystems.xlsx: a KBC building block."""
    id: str
    ecosystem: str
    name: str
    service: str
    partner: str | None = None


class DataField(BaseModel):
    """A piece of customer data that may be shared with a partner, once the customer grants it."""
    field: str
    label: str
    sensitive: bool = False


class ValueShare(BaseModel):
    model: ValueShareModel
    amount_eur: float = 0.0          # fee per lead / completed step, or monthly subscription
    pct: float = 0.0                 # revenue share, as a fraction
    note: str = ""


class Partner(BaseModel):
    id: str = Field(pattern=PARTNER_ID_PATTERN)
    name: str
    kind: ProviderKind
    ecosystems: list[str]
    catalogue_ids: list[str]
    blurb: str
    allowed_fields: list[str]                 # the most this partner may EVER receive; grants narrow it further
    value_share: ValueShare
    vetting: list[str] = Field(default_factory=list)   # checks KBC did before admitting the partner
    sla_hours: int = 48
    integration: str = ""                     # which KBC integration surface it plugs into


class ProviderPublic(BaseModel):
    id: str
    name: str
    kind: ProviderKind
    blurb: str
    vetting: list[str]
    integration: str


# ---- goals and journeys ---------------------------------------------------------------------------------------


class Win(BaseModel):
    customer: str = ""
    kbc: str = ""
    partner: str = ""


class Estimates(BaseModel):
    """Illustrative, labelled as assumptions in the UI."""
    customer_eur: float = 0.0       # money saved or grants unlocked for the customer
    hours_saved: float = 0.0
    kbc_revenue_eur: float = 0.0    # yearly margin estimate for KBC
    partner_fee_eur: float = 0.0    # what KBC pays the partner when the step completes


class ProductRef(BaseModel):
    id: str
    name: str
    ecosystem: str
    partner: str | None = None


class Step(BaseModel):
    step_id: str
    order: int
    title: str
    description: str
    provider: ProviderPublic
    why_this_provider: str
    products: list[ProductRef]               # catalogue building blocks this step uses
    status: StepStatus
    data_shared: list[DataField]             # what the provider will see if the customer approves
    data_not_shared: list[str]               # plain-language reassurance ("your income", "your balance")
    consent_days: int
    win: Win
    estimates: Estimates
    result: str = ""                         # what came back (partner webhook or KBC service)
    ref: str = ""                            # provider's reference
    grant_id: int | None = None
    updated_at: dt.datetime | None = None
    already_held: bool = False               # the customer already has this at KBC: nothing to do


class Progress(BaseModel):
    done: int
    total: int


class WinTotals(BaseModel):
    customer_eur: float = 0.0
    hours_saved: float = 0.0
    kbc_revenue_eur: float = 0.0
    partner_fees_eur: float = 0.0
    kbc_products: list[str] = Field(default_factory=list)
    partner_leads: int = 0


class Goal(BaseModel):
    goal_id: int
    playbook_id: str
    title: str
    icon: str
    tagline: str
    ecosystems: list[str]
    status: GoalStatus
    created_on: dt.date
    target_date: dt.date | None = None
    origin: Literal["detected", "stated"]
    evidence: list[str]
    progress: Progress
    steps: list[Step]
    outcome: WinTotals                       # realised so far (done steps only)
    potential: WinTotals                     # if every step completes
    next_goal: str | None = None             # playbook id the engine suggests after this one


class GoalCandidate(BaseModel):
    """KBC noticed something. Nothing happens until the customer taps Start."""
    playbook_id: str
    title: str
    icon: str
    tagline: str
    ecosystems: list[str]
    confidence: float = Field(ge=0, le=1)
    evidence: list[str]
    why_now: str
    steps_preview: list[str]
    partners_preview: list[str]
    potential: WinTotals


class PlaybookSummary(BaseModel):
    playbook_id: str
    title: str
    icon: str
    tagline: str
    ecosystems: list[str]
    steps: int


class GoalsResponse(BaseModel):
    as_of: dt.date
    candidates: list[GoalCandidate]
    goals: list[Goal]
    holdings: list[ProductRef]
    playbooks: list[PlaybookSummary]         # every goal a customer can state themselves


# ---- consent passport -------------------------------------------------------------------------------------------


class ConsentGrant(BaseModel):
    grant_id: int
    partner_id: str
    partner_name: str
    goal_id: int
    goal_title: str
    step_id: str
    step_title: str
    fields: list[DataField]
    purpose: str
    granted_on: dt.date
    expires_on: dt.date
    status: GrantStatus
    revoked_on: dt.date | None = None


class ConsentsResponse(BaseModel):
    grants: list[ConsentGrant]
    partners_with_access: int
    fields_shared: int


# ---- requests ------------------------------------------------------------------------------------------------------


class StartGoalRequest(BaseModel):
    playbook_id: str = Field(pattern=PLAYBOOK_ID_PATTERN)


class StepDecisionRequest(BaseModel):
    decision: Literal["approve", "decline", "reset"]


class PartnerWebhook(BaseModel):
    """What a partner POSTs to /api/partners/{partner_id}/webhook. Signed, see webhooks.py."""
    event_id: str = Field(pattern=EVENT_ID_PATTERN)
    ref: str = Field(pattern=r"^[a-z0-9_-]{6,80}$")
    status: Literal["in_progress", "done", "failed"]
    result: str = Field(default="", max_length=300)

    model_config = {"extra": "forbid"}


# ---- KBC ecosystem console ----------------------------------------------------------------------------------------


class FunnelRow(BaseModel):
    playbook_id: str
    title: str
    icon: str
    detected: int            # customers in the synthetic portfolio with this candidate goal
    started: int
    steps_done: int
    completed: int
    projected_2_3m: int      # detected share × 2.3M customers


class PartnerRow(BaseModel):
    partner_id: str
    name: str
    ecosystems: list[str]
    value_share: ValueShare
    leads: int
    completed: int
    fees_eur: float
    avg_response_s: float | None = None


class EventRow(BaseModel):
    at: dt.datetime
    partner_id: str
    kind: str                # "outbound" (KBC → partner) or the webhook status
    summary: str
    verified: bool


class EcosystemOverview(BaseModel):
    catalogue_items: int
    ecosystems: int
    building_blocks_used: int
    partners: int
    funnel: list[FunnelRow]
    partner_rows: list[PartnerRow]
    events: list[EventRow]
    realised: WinTotals
    projection: dict[str, float]             # 2.3M projection of the triple win, with the assumptions spelled out
    assumptions: list[str]
    scoring_ms: float
