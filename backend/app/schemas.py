"""THE contracts. Mirrored in frontend/src/api.ts. Change only via a PR that updates both.

Everything the engine consumes or produces is a Pydantic model so that:
  - the API validates every input (patterns, enums, lengths),
  - the engine's output is schema-checked before it leaves the server,
  - the frontend has one typed source of truth.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# ----------------------------------------------------------------------------------
# Vocabularies
# ----------------------------------------------------------------------------------

Persona = Literal["student", "young_professional", "young_family", "freelancer", "retiree"]
PERSONAS: tuple[Persona, ...] = ("student", "young_professional", "young_family", "freelancer", "retiree")

Category = Literal[
    "salary", "invoice_income", "pension", "student_income", "allowance_from_parents",
    "child_benefit", "benefit", "rent", "mortgage", "utilities", "telecom", "subscription",
    "insurance_car", "insurance_home", "insurance_family", "groceries", "leisure", "transport",
    "childcare", "baby", "school", "tuition", "social_contribution", "vat_payment", "tax",
    "savings_transfer", "furniture", "notary", "healthcare", "other",
]
CATEGORIES: tuple[str, ...] = Category.__args__  # type: ignore[attr-defined]
INCOME_CATEGORIES = frozenset({
    "salary", "invoice_income", "pension", "student_income", "allowance_from_parents",
    "child_benefit", "benefit",
})

Family = Literal["deadline", "anomaly", "forecast", "opportunity", "milestone", "protection"]
Stage = Literal["early", "soon", "urgent", "info"]
LegacyCardType = Literal[
    "insurance_renewal", "vat_reserve", "price_increase", "duplicate_charge",
    "runway", "cashflow_squeeze", "idle_cash", "life_event", "scam_awareness",
    "pension_savings", "late_client", "protection_gap", "new_payee",
]
LEGACY_CARD_TYPES: tuple[str, ...] = LegacyCardType.__args__  # type: ignore[attr-defined]
CORE_CARD_TYPES: tuple[str, ...] = (
    "core_money", "core_spending", "core_coming_up", "core_unusual", "core_insurance",
    "core_goals", "core_investments", "core_debt", "core_cards", "core_health",
)
CATALOGUE_CARD_TYPES: tuple[str, ...] = tuple(
    f"catalog_{group.lower()}_{number:02d}"
    for group, count in (("YS", 10), ("EC", 10), ("FM", 10), ("HM", 10), ("TR", 10),
                         ("SV", 10), ("BZ", 8), ("RT", 10), ("EL", 10), ("LE", 12))
    for number in range(1, count + 1)
)
CARD_TYPES = LEGACY_CARD_TYPES  # the legacy ranker's affinity contract
FEEDBACK_CARD_TYPES = CARD_TYPES + CORE_CARD_TYPES + CATALOGUE_CARD_TYPES
CardType = str

Decision = Literal["dismiss", "snooze", "less", "accept", "reset"]
LayoutPrefState = Literal["pinned", "hidden", "reset"]

Component = Literal[
    "BalanceHero", "RunwayHero", "FamilyBudgetHero", "TaxReserveHero", "PensionHero",
    "ForYouFeed", "QuickActions", "UpcomingBills", "SplitBills", "InvoiceTracker",
    "SavingsGoal", "ScamShield", "AdvisorContact", "SpendingByCategory",
    "KateTile", "SubscriptionsTile",
]
COMPONENTS: tuple[str, ...] = Component.__args__  # type: ignore[attr-defined]
HERO_COMPONENTS: tuple[str, ...] = ("BalanceHero", "RunwayHero", "FamilyBudgetHero", "TaxReserveHero", "PensionHero")

Density = Literal["compact", "comfortable", "large"]
Tone = Literal["casual", "neutral", "warm", "business", "formal"]
Contrast = Literal["normal", "high"]
Size = Literal["hero", "full", "half"]
Appearance = Literal["light", "dark"]
Accent = Literal["blue", "teal", "purple", "amber", "navy"]

# Things a customer can tell Kate about themselves. Each maps to one persona (persona.py).
DeclaredSignal = Literal["expecting_baby", "going_freelance", "retiring", "studying"]

CARD_KEY_PATTERN = r"^[a-z0-9_:\-]{1,80}$"

# ----------------------------------------------------------------------------------
# Internal data (DB rows). Never returned to customers as-is.
# ----------------------------------------------------------------------------------


class Customer(BaseModel):
    id: int
    first_name: str
    last_name: str
    birth_year: int
    city: str
    language: Literal["nl", "fr"] = "nl"
    products: list[str] = Field(default_factory=list)  # e.g. ["current", "savings", "mortgage", "car_insurance"]
    consent_personalization: bool = True
    ground_truth: dict = Field(default_factory=dict)   # injected scenarios; NEVER sent to customers


class Transaction(BaseModel):
    id: int
    customer_id: int
    date: dt.date
    amount: float          # signed: > 0 income, < 0 spend
    category: Category
    counterparty: str = Field(max_length=80)


class FeedbackRow(BaseModel):
    card_key: str = Field(pattern=CARD_KEY_PATTERN)
    card_type: CardType
    decision: Decision
    created_at: dt.date


class LayoutPrefRow(BaseModel):
    component: Component
    state: Literal["pinned", "hidden"]
    position: int | None = None     # pinned only: slot index among the non-hero sections below the feed


class StylePrefs(BaseModel):
    """Customer overrides on the adaptive theme. None = "Auto" (the engine decides)."""
    density: Density | None = None
    contrast: Contrast | None = None
    tone: Tone | None = None
    appearance: Appearance | None = None
    accent: Accent | None = None
    reduce_motion: bool = False
    privacy: bool = False           # mask amounts until tapped


class DeclaredSignalRow(BaseModel):
    signal: DeclaredSignal
    created_at: dt.date


class SuggestionDismissal(BaseModel):
    component: Component
    created_at: dt.date


class Prefs(BaseModel):
    """Everything the customer has told us. Read from DB, passed into the pure engine."""
    feedback: list[FeedbackRow] = Field(default_factory=list)
    layout_prefs: list[LayoutPrefRow] = Field(default_factory=list)
    last_visit: dt.date | None = None
    style: StylePrefs = Field(default_factory=StylePrefs)
    declared: list[DeclaredSignalRow] = Field(default_factory=list)
    dismissed_suggestions: list[SuggestionDismissal] = Field(default_factory=list)


# ----------------------------------------------------------------------------------
# Engine intermediates
# ----------------------------------------------------------------------------------


class RecurringPayment(BaseModel):
    counterparty: str
    category: Category
    amount_eur: float              # latest amount, positive number
    previous_amount_eur: float | None = None   # amount before the latest one, if it changed
    period_days: int               # ~30 monthly, ~365 yearly
    last_date: dt.date
    next_date: dt.date             # last_date + period


class LifeEvent(BaseModel):
    type: Literal["first_salary", "first_invoice", "baby", "pension_start", "moved_house", "first_pension"]
    date: dt.date
    evidence: str


class Features(BaseModel):
    """Everything downstream modules may use. Computed once per (customer, as_of)."""
    as_of: dt.date
    age: int
    balance_eur: float

    # income
    monthly_income_avg_90d: float
    income_regularity: float                 # coefficient of variation of monthly income, 0 = perfectly regular
    income_sources_180d: int                 # distinct payers in the last 180 days
    income_by_category_180d: dict[str, float] = Field(default_factory=dict)
    next_income_date: dt.date | None = None
    next_income_eur: float | None = None
    quarter_income_eur: float = 0.0          # income in the current calendar quarter
    quarter_invoice_income_eur: float = 0.0
    # VAT reporting period: the most recently ended quarter while its return (20th of the next month) is still
    # due, otherwise the running quarter. Cards and the TaxReserveHero use these, never the raw calendar quarter.
    vat_period_label: str = ""               # e.g. "Q3 2026"
    vat_period_invoice_income_eur: float = 0.0
    vat_due_date: dt.date | None = None

    # spending
    monthly_spend_avg_90d: float
    spend_by_category_30d: dict[str, float] = Field(default_factory=dict)  # positive numbers
    variable_spend_change_30d: float = 0.0   # +0.8 means +80 % vs the previous 90-day monthly average
    runway_days: int | None = None           # days until balance < 0 at current burn; None if not falling
    idle_cash_eur: float = 0.0               # balance above 6× monthly spend when no savings product

    # flags
    has_salary: bool = False
    has_invoice_income: bool = False
    has_pension: bool = False
    has_student_signals: bool = False
    has_child_signals: bool = False
    has_vat_payments: bool = False
    has_social_contributions: bool = False
    has_mortgage: bool = False
    has_rent: bool = False
    has_savings_product: bool = False

    # family
    child_benefit_monthly_eur: float = 0.0
    childcare_monthly_eur: float = 0.0

    # structure
    recurring_payments: list[RecurringPayment] = Field(default_factory=list)
    life_events: list[LifeEvent] = Field(default_factory=list)
    first_tx_date: dt.date | None = None
    last_tx_date: dt.date | None = None


class PersonaWeight(BaseModel):
    persona: Persona
    weight: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)


# ----------------------------------------------------------------------------------
# Output: cards, layout, home
# ----------------------------------------------------------------------------------


class Cta(BaseModel):
    label: str = Field(max_length=40)
    action: str = Field(pattern=r"^[a-z_]{1,40}$")


class Card(BaseModel):
    card_key: str = Field(pattern=CARD_KEY_PATTERN)
    card_type: CardType
    family: Family
    stage: Stage
    title: str = Field(max_length=120)
    body: str = Field(max_length=400)
    eur_impact: float = 0.0
    due_date: dt.date | None = None
    confidence: float = Field(ge=0, le=1)
    commercial: bool = False
    evidence: list[str] = Field(default_factory=list)
    rank_explanation: str = ""
    score: float = 0.0
    cta: Cta | None = None
    details: dict = Field(default_factory=dict)   # structured extras for the UI (e.g. comparison table rows)

    @field_validator("card_type")
    @classmethod
    def known_card_type(cls, value: str) -> str:
        if value not in FEEDBACK_CARD_TYPES:
            raise ValueError("Unknown card type")
        return value


class Theme(BaseModel):
    density: Density
    tone: Tone
    contrast: Contrast
    appearance: Appearance = "light"
    accent: Accent | None = None      # None = the tone's accent colour
    reduce_motion: bool = False
    privacy: bool = False
    overrides: list[str] = Field(default_factory=list)   # theme keys the customer set themselves


class Section(BaseModel):
    component: Component
    size: Size
    props: dict = Field(default_factory=dict)
    pinned: bool = False


class Layout(BaseModel):
    version: int = 1
    theme: Theme
    sections: list[Section]
    explanations: dict[str, str] = Field(default_factory=dict)


class TileSuggestion(BaseModel):
    """"Your life changed, add this tile?" The system proposes; the customer decides."""
    component: Component
    title: str = Field(max_length=120)
    reason: str = Field(max_length=240)
    as_hero: bool = False


class GalleryItem(BaseModel):
    """Every registered tile, for the "Add tile" sheet. Ranked by planner score."""
    component: Component
    label: str
    description: str
    reason: str = ""
    score: float = 0.0
    suggested: bool = False
    state: Literal["shown", "available", "hidden"] = "available"
    is_hero: bool = False


class Feed(BaseModel):
    cards: list[Card]
    caught_up: bool = True
    hidden_count: int = 0


class FeedPersona(BaseModel):
    code: Literal["TEEN", "STU", "YPRO", "PAR", "HOME", "SELF", "INV", "PRE", "SEN"]
    weight: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)


class CustomerPublic(BaseModel):
    first_name: str
    language: Literal["nl", "fr"]
    consent_personalization: bool


class HomeResponse(BaseModel):
    as_of: dt.date
    customer: CustomerPublic
    persona_mix: list[PersonaWeight]
    feed_personas: list[FeedPersona] = Field(default_factory=list)
    layout: Layout
    feed: Feed
    generated_at: dt.datetime
    llm_copy: bool = False
    style: StylePrefs = Field(default_factory=StylePrefs)          # the customer's own settings (None = Auto)
    suggestions: list[TileSuggestion] = Field(default_factory=list)
    gallery: list[GalleryItem] = Field(default_factory=list)
    declared: list[DeclaredSignalRow] = Field(default_factory=list)


class Milestone(BaseModel):
    date: dt.date
    label: str


class TimelineResponse(BaseModel):
    min_date: dt.date
    max_date: dt.date
    milestones: list[Milestone]


# ----------------------------------------------------------------------------------
# Request bodies
# ----------------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str = Field(pattern=r"^[a-z0-9_]{1,32}$")
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    role: Literal["customer", "advisor"]
    username: str


class FeedbackRequest(BaseModel):
    card_key: str = Field(pattern=CARD_KEY_PATTERN)
    card_type: CardType
    decision: Decision

    @field_validator("card_type")
    @classmethod
    def known_card_type(cls, value: str) -> str:
        if value not in FEEDBACK_CARD_TYPES:
            raise ValueError("Unknown card type")
        return value


class LayoutPrefRequest(BaseModel):
    component: Component
    state: LayoutPrefState
    position: int | None = Field(default=None, ge=0, le=20)


class SuggestionRequest(BaseModel):
    component: Component
    decision: Literal["accept", "dismiss"]


class DeclareRequest(BaseModel):
    signal: DeclaredSignal
    state: Literal["set", "clear"] = "set"


# ---- Kate (conversational assistant) ------------------------------------------------

KateActionKind = Literal["pin_tile", "hide_tile", "add_tile", "snooze_card", "dismiss_card",
                         "set_style", "declare", "open_card", "reset_style"]


class KateAction(BaseModel):
    """A proposal. Kate never changes anything herself: the app shows a button, the customer taps it, and the
    app calls the regular validated endpoint."""
    kind: KateActionKind
    label: str = Field(max_length=60)
    component: Component | None = None
    card_key: str | None = Field(default=None, pattern=CARD_KEY_PATTERN)
    card_type: CardType | None = None
    style: StylePrefs | None = None
    signal: DeclaredSignal | None = None


class KateTurn(BaseModel):
    role: Literal["user", "kate"]
    text: str = Field(max_length=600)


class KateRequest(BaseModel):
    message: str = Field(default="", max_length=500)     # empty = "open the chat": Kate starts
    card_key: str | None = Field(default=None, pattern=CARD_KEY_PATTERN)   # "Ask Kate" from a card
    history: list[KateTurn] = Field(default_factory=list, max_length=12)


class KateReply(BaseModel):
    reply: str = Field(max_length=1200)
    actions: list[KateAction] = Field(default_factory=list, max_length=3)
    quick_replies: list[str] = Field(default_factory=list, max_length=4)
    source: Literal["rules", "llm"] = "rules"


class ConsentRequest(BaseModel):
    consent_personalization: bool


class AdvisorOverview(BaseModel):
    customers_scored: int
    scoring_ms: float
    projected_2_3m_seconds: float
    persona_distribution: dict[str, int]
    card_volume: dict[str, int]
    eur_impact_total: float
