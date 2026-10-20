"""Backend-only contracts; deliberately independent of the frontend contracts."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

Trend = Literal["increasing", "decreasing", "stable", "unknown"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, validate_assignment=True)


class TransactionDetails(Model):
    account_id: str = "current"
    currency: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")
    merchant_id: str | None = None
    subcategory: str | None = None
    canonical_category: str | None = None  # upstream taxonomy mapping, e.g. loan or restaurants
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    location: str | None = None
    booked_at: dt.datetime | None = None
    payment_method: str | None = None
    source: str = "bank"
    internal_transfer: bool = False
    sensitive: bool = False


class AccountObservation(Model):
    id: str
    account_id: str
    kind: Literal["current", "savings", "loan", "credit"]
    observed_at: dt.date
    balance: float  # debt balances are positive outstanding principal
    currency: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")
    source: str = "bank"


class RawTransaction(Model):
    id: int
    date: dt.date
    amount: float
    category: str
    counterparty: str
    details: TransactionDetails = Field(default_factory=TransactionDetails)


class Observations(Model):
    customer_id: int
    products: list[str]
    transactions: list[RawTransaction]
    accounts: list[AccountObservation]
    activity: dict[str, JsonValue] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class Signal(Model):
    id: str
    transaction_id: int
    account_id: str
    date: dt.date
    amount: float
    currency: str
    category: str
    entity: str | None
    kind: Literal["income", "expense", "savings", "transfer", "refund"]
    discretionary: bool
    essential: bool
    profile_allowed: bool
    country: str | None = None
    source: str
    payment_method: str | None = None


class Evidence(Model):
    transaction_ids: list[int] = Field(default_factory=list)
    account_observation_ids: list[str] = Field(default_factory=list)
    pattern_ids: list[str] = Field(default_factory=list)
    period_from: dt.date | None = None
    period_to: dt.date | None = None
    method: str


class Pattern(Model):
    id: str
    type: Literal["RECURRING_INCOME", "RECURRING_PAYMENT", "RECURRING_TRANSFER", "RECURRING_MERCHANT"]
    entity: str
    category: str
    kind: str
    cadence: Literal["weekly", "monthly", "quarterly", "yearly"]
    amount: float
    monthly_amount: float
    usual_day: int
    first_date: dt.date
    last_date: dt.date
    next_date: dt.date | None
    active: bool
    confidence: float = Field(ge=0, le=1)
    evidence: Evidence


ChangeType = Literal[
    "SALARY_CHANGED", "NEW_INCOME_SOURCE", "INCOME_DISAPPEARED",
    "RECURRING_BILL_APPEARED", "RECURRING_BILL_DISAPPEARED",
    "SUBSCRIPTION_APPEARED", "SUBSCRIPTION_DISAPPEARED", "SUBSCRIPTION_PRICE_CHANGED",
    "CATEGORY_SPENDING_INCREASED", "CATEGORY_SPENDING_DECREASED",
    "SAVINGS_BEHAVIOR_CHANGED", "DEBT_PAYMENT_CHANGED", "CASH_BUFFER_CHANGED",
    "UNUSUALLY_LARGE_TRANSACTION", "NEW_MERCHANT", "NEW_CATEGORY",
    "FOREIGN_SPENDING_APPEARED", "MONTHLY_CASH_FLOW_CHANGED",
]


class Change(Model):
    id: str
    type: ChangeType
    entity: str
    previous_value: float | None = None
    current_value: float | None = None
    change_pct: float | None = None
    detected_at: dt.date
    confidence: float = Field(ge=0, le=1)
    evidence: Evidence


class Inference(Model):
    id: str
    type: str
    value: str
    confidence: float = Field(ge=0, le=1)
    evidence: Evidence
    created_at: dt.date
    updated_at: dt.date
    review_at: dt.date | None = None


class Condition(Model):
    type: str
    severity: Literal["low", "medium", "high"] | None = None
    confidence: float = Field(ge=0, le=1)
    data: dict[str, JsonValue]
    evidence: Evidence


class Income(Model):
    estimated_monthly_income: float | None
    income_stability: float | None
    income_trend: Trend
    income_sources: int
    next_expected_income_date: dt.date | None
    next_expected_income_amount: float | None


class Expenses(Model):
    average_monthly_expenses: float | None
    average_fixed_expenses: float | None
    average_variable_expenses: float | None
    average_discretionary_expenses: float | None
    average_essential_expenses: float | None
    average_unclassified_expenses: float | None


class Position(Model):
    current_balance: float | None
    total_liquid_balance: float | None
    known_savings: float | None
    known_debt: float | None
    overdraft: float | None


class ExpectedFlow(Model):
    date: dt.date
    amount: float
    pattern_id: str


class CashFlow(Model):
    monthly: list[dict[str, JsonValue]]
    average_monthly_free_cash_flow: float | None
    cash_buffer_months: float | None
    upcoming_inflows: list[ExpectedFlow]
    upcoming_outflows: list[ExpectedFlow]
    expected_7_day_balance: float | None
    expected_30_day_balance: float | None
    lowest_projected_balance: float | None
    liquidity_pressure: Literal["low", "medium", "high", "unknown"]


class Savings(Model):
    balance: float | None
    transfers_to_savings: float
    withdrawals_from_savings: float
    average_monthly_savings: float | None
    savings_rate: float | None
    trend: Trend


class Debt(Model):
    total_known_debt: float | None
    monthly_debt_service: float | None
    debt_service_ratio: float | None
    trend: Trend


class Recurring(Model):
    count: int
    monthly_total: float
    items: list[Pattern]


class Spending(Model):
    trend: Trend
    volatility: float | None
    month_over_month_change: float | None
    top_categories: list[dict[str, JsonValue]]
    top_merchants: list[dict[str, JsonValue]]
    category_metrics: dict[str, dict[str, JsonValue]]


class CustomerState(Model):
    schema_version: str = "1"
    customer_id: int
    as_of: dt.date
    generated_at: dt.datetime
    currency: str = "EUR"
    data_period: dict[str, dt.date | None]
    freshness: dict[str, JsonValue]
    observations: Observations
    signals: list[Signal]
    financial_position: Position
    income: Income
    expenses: Expenses
    cash_flow: CashFlow
    savings: Savings
    debt: Debt
    recurring_payments: Recurring
    subscriptions: Recurring
    spending: Spending
    patterns: list[Pattern]
    changes: list[Change]
    events: list[Change]
    inferences: list[Inference]
    risks: list[Condition]
    opportunities: list[Condition]
    provenance: dict[str, Evidence]
