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
ProviderKind = Literal["kbc", "partner", "advisor"]   # advisor: a KBC human (private banker, relationship manager)
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
    rating: float | None = Field(default=None, ge=0, le=5)          # customer rating, out of 5
    outcome_rate: float | None = Field(default=None, ge=0, le=1)    # share of leads that reached the outcome


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
    done_on: dt.date | None = None           # simulated date the step completed (time travel aware)
    fee: FeeDisclosure | None = None         # what KBC earns if the customer goes ahead
    alternatives: list[PartnerOption] = Field(default_factory=list)   # >1 when the customer can pick a partner
    source_hint: SourceHint | None = None    # a data source that would make this step more accurate
    booking: str = ""                        # advisor steps: the booked meeting
    fallback: FallbackOffer | None = None    # the partner declined or didn't answer: who can do it instead
    joint: bool = False                      # shared household goal: every member approves before data leaves KBC
    approved_by: list[str] = Field(default_factory=list)   # first names of members who approved (joint steps)
    waiting_for: list[str] = Field(default_factory=list)   # first names of members whose approval is still needed


class FallbackOffer(BaseModel):
    """A partner rejected the lead or missed its SLA. KBC proposes the next-ranked vetted partner; nothing is
    shared with it until the customer approves again (a fresh consent grant)."""
    reason: Literal["rejected", "timeout", "failed"]
    message: str
    partner_id: str | None = None            # None: no other vetted partner for this step
    partner_name: str | None = None


class FeeDisclosure(BaseModel):
    """Fee transparency: what KBC earns if the customer goes ahead, in plain words."""
    model: ValueShareModel | None = None
    amount_eur: float = 0.0
    pct: float = 0.0
    kbc_earns: str                           # "KBC earns €45 from Immoscoop if you go ahead"
    you_pay_extra: str = "You pay nothing extra because of it."


class PartnerOption(BaseModel):
    """One vetted partner that can do this step. Ranked by outcome rate and rating, never by fee."""
    provider: ProviderPublic
    rating: float | None = None
    outcome_rate: float | None = None
    rank: int
    recommended: bool = False
    chosen: bool = False
    fee: FeeDisclosure
    data_shared: list[DataField] = Field(default_factory=list)
    demoted: bool = False                    # repeatedly missed its SLA: ranked below the partners that answer
    tried: bool = False                      # already declined or timed out for this step


class SourceHint(BaseModel):
    """'Connect mypension.be for an exact number': a data source that would make this step more accurate."""
    source_id: str
    name: str
    prompt: str
    connected: bool = False


class MeasuredOutcome(BaseModel):
    """Journey step 5: the realised outcome, verified from the customer's own later transactions."""
    metric: str
    label: str
    status: Literal["verified", "pending", "not_met"]
    measured_eur: float | None = None        # what we measured (per year where it's a recurring saving)
    estimate_eur: float | None = None        # what the playbook estimated
    unit: str = "€"
    summary: str
    evidence: list[str] = Field(default_factory=list)
    check_on: dt.date | None = None          # pending: when KBC will look again
    step_id: str | None = None


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
    next_goal_title: str | None = None
    measured: list[MeasuredOutcome] = Field(default_factory=list)   # realised vs estimated (journey step 5)
    role: Literal["owner", "member"] = "owner"   # member: a household member the owner shared the goal with
    household: list[HouseholdMember] = Field(default_factory=list)
    paused: bool = False                     # paused by the customer: no nudges, no stall prompts
    stall: StallPrompt | None = None         # no progress for a month: one gentle "still want this?"


class HouseholdMember(BaseModel):
    first_name: str
    role: Literal["owner", "member"]
    status: Literal["invited", "active"]
    you: bool = False


class StallPrompt(BaseModel):
    since: dt.date                           # last progress
    days: int
    question: str
    options: list[Literal["keep", "pause", "stop"]] = Field(default_factory=lambda: ["keep", "pause", "stop"])


class HouseholdInvite(BaseModel):
    goal_id: int
    title: str
    icon: str
    from_name: str


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
    area: str = ""                                                 # life area, for grouping (ecosystem/fit.py)
    fit: Literal["suggested", "open", "unlikely"] = "open"
    fit_reason: str = ""


class GoalsResponse(BaseModel):
    as_of: dt.date
    candidates: list[GoalCandidate]
    goals: list[Goal]
    holdings: list[ProductRef]
    playbooks: list[PlaybookSummary]         # every goal a customer can state themselves
    invitations: list[HouseholdInvite] = Field(default_factory=list)   # goals a household member shared with you


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
    deletion_confirmed_at: dt.datetime | None = None    # partner confirmed (signed webhook) it deleted the data
    deletion_confirmed_by: str | None = None
    kbc_earns: str = ""                                  # fee transparency, as shown before approval


class SourceView(BaseModel):
    """An inbound data source: data KBC reads (with the customer's OK) to do a goal better."""
    source_id: str
    name: str
    provider: str
    kind: Literal["psd2", "government", "partner", "public", "utility"]
    reads: list[str]
    goals: list[str]
    sensitivity: Literal["low", "medium", "high"]
    needs_consent: bool
    consent_days: int
    why: str
    status: Literal["available", "connected", "expired", "public"]
    connected_on: dt.date | None = None
    expires_on: dt.date | None = None
    purpose: str = ""
    playbook_id: str | None = None
    values: dict[str, str | float] = Field(default_factory=dict)   # only when connected (or public)
    simulated: bool = True


class SourcesResponse(BaseModel):
    sources: list[SourceView]
    connected: int
    note: str = "Values are simulated from your synthetic profile: no real connection is made."


class ConsentsResponse(BaseModel):
    grants: list[ConsentGrant]
    partners_with_access: int
    fields_shared: int
    sources: list[SourceView] = Field(default_factory=list)   # inbound: data KBC reads with your OK


# ---- requests ------------------------------------------------------------------------------------------------------


class StartGoalRequest(BaseModel):
    playbook_id: str = Field(pattern=PLAYBOOK_ID_PATTERN)


class StepDecisionRequest(BaseModel):
    decision: Literal["approve", "decline", "reset"]
    partner_id: str | None = Field(default=None, pattern=PARTNER_ID_PATTERN)   # pick among the step's alternatives

    model_config = {"extra": "forbid"}


USERNAME_PATTERN = r"^[a-z0-9_]{2,40}$"


class HouseholdInviteRequest(BaseModel):
    username: str = Field(pattern=USERNAME_PATTERN)

    model_config = {"extra": "forbid"}


class HouseholdAnswerRequest(BaseModel):
    accept: bool

    model_config = {"extra": "forbid"}


class StallAnswerRequest(BaseModel):
    answer: Literal["keep", "pause", "resume", "stop"]

    model_config = {"extra": "forbid"}


class PartnerSimRequest(BaseModel):
    mode: Literal["done", "late", "reject", "fail", "timeout"]

    model_config = {"extra": "forbid"}


SOURCE_ID_PATTERN = r"^[a-z0-9_]{2,40}$"


class SourceConnectRequest(BaseModel):
    playbook_id: str = Field(pattern=PLAYBOOK_ID_PATTERN)     # purpose binding: the goal this data is for
    purpose: str = Field(default="", max_length=200, pattern=r"^[\w\s.,:;'()€%/&+-]*$")

    model_config = {"extra": "forbid"}


class PartnerWebhook(BaseModel):
    """What a partner POSTs to /api/partners/{partner_id}/webhook. Signed, see webhooks.py."""
    event_id: str = Field(pattern=EVENT_ID_PATTERN)
    ref: str = Field(pattern=r"^[a-z0-9_-]{6,80}$")
    # deleted: data erased after revoke/expiry; rejected: the partner declines the lead (result = the reason)
    status: Literal["in_progress", "done", "failed", "rejected", "deleted"]
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
    # live scorecard from the partner calls: first answer time, SLA misses, rejections, done / answered
    calls: int = 0
    sla_misses: int = 0
    rejections: int = 0
    failures: int = 0
    late_answers: int = 0
    outcome_rate_live: float | None = None
    sla_hours: int = 0
    demoted: bool = False
    sim_mode: str = "done"                   # demo: how the simulated partner answers


class EventRow(BaseModel):
    at: dt.datetime
    partner_id: str
    kind: str                # "outbound" (KBC → partner) or the webhook status
    summary: str
    verified: bool


class LearningRow(BaseModel):
    """Learning loop per goal: how often it is shown, started and completed, and how often its rule fires."""
    playbook_id: str
    title: str
    icon: str
    detected: int                # portfolio scan: customers the rule fires for
    hit_rate: float              # detected / customers scanned
    avg_confidence: float
    shown: int                   # customers who saw the candidate in the app
    started: int
    completed: int
    start_rate: float | None = None        # started / shown
    completion_rate: float | None = None   # completed / started


class RuleRow(BaseModel):
    playbook_id: str
    rule: str                    # the evidence pattern (numbers stripped)
    hits: int
    hit_rate: float


class OutcomeSummary(BaseModel):
    verified: int = 0
    pending: int = 0
    not_met: int = 0
    verified_eur: float = 0.0               # measured, from customers' own transactions
    estimated_eur_for_verified: float = 0.0  # what the playbooks estimated for those same outcomes


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
    customers_scored: int = 0                 # how many synthetic customers scoring_ms covers
    learning: list[LearningRow] = Field(default_factory=list)
    rules: list[RuleRow] = Field(default_factory=list)
    outcomes: OutcomeSummary = Field(default_factory=OutcomeSummary)


# ---- partner onboarding ---------------------------------------------------------------------------------------------


class WebhookContract(BaseModel):
    url: str = Field(pattern=r"^https://[A-Za-z0-9.-]{3,120}(/[A-Za-z0-9._~/-]{0,200})?$", max_length=330)
    events: list[Literal["in_progress", "done", "failed", "rejected", "deleted"]] = Field(min_length=1, max_length=5)

    model_config = {"extra": "forbid"}


class PartnerManifest(BaseModel):
    """What a partner submits to join the network. Validated with the same rules as partners.json."""
    id: str = Field(pattern=PARTNER_ID_PATTERN)
    name: str = Field(min_length=2, max_length=80)
    ecosystems: list[str] = Field(min_length=1, max_length=10)
    catalogue_ids: list[str] = Field(min_length=1, max_length=20)
    blurb: str = Field(default="", max_length=300)
    allowed_fields: list[str] = Field(min_length=1, max_length=20)
    value_share: ValueShare
    vetting: list[str] = Field(default_factory=list, max_length=10)
    integration: str = Field(default="KBC Partner Hub + application status webhooks", max_length=120)
    webhook: WebhookContract
    sla_hours: int = Field(ge=1, le=720)

    model_config = {"extra": "forbid"}


class SigningSetup(BaseModel):
    algorithm: str = "HMAC-SHA256"
    signed_string: str = "{X-KBC-Timestamp}.{raw body}"
    headers: list[str] = Field(default_factory=lambda: ["X-KBC-Timestamp", "X-KBC-Signature"])
    max_skew_s: int = 300
    secret_env: str
    key_fingerprint: str                      # sha256 prefix of the key: the key itself is never returned
    webhook_endpoint: str


class ManifestResult(BaseModel):
    valid: bool
    problems: list[str]
    warnings: list[str] = Field(default_factory=list)
    partner: ProviderPublic | None = None
    signing: SigningSetup | None = None
