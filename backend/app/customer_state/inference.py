"""Replaceable inference boundary. Rules express uncertainty, never customer-facing advice."""
from __future__ import annotations

import datetime as dt
from typing import Protocol

from .models import Condition, CustomerState, Evidence, Inference
from .patterns import stable_id


class InferenceProvider(Protocol):
    version: str

    def infer(self, state: CustomerState) -> list[Inference]: ...


class RuleInference:
    version = "rules-1"

    def infer(self, state: CustomerState) -> list[Inference]:
        result = []
        for p in state.patterns:
            if not p.active or p.category not in {"salary", "subscription"}:
                continue
            typ = "LIKELY_RECURRING_SALARY" if p.category == "salary" else "LIKELY_SUBSCRIPTION"
            dates = sorted({s.date for s in state.signals if s.transaction_id in p.evidence.transaction_ids})
            confirmed_at = dates[1 if p.cadence == "yearly" else 2]
            result.append(Inference(
                id=stable_id(typ, p.id), type=typ, value=p.entity, confidence=p.confidence,
                evidence=p.evidence.model_copy(update={"pattern_ids": [p.id]}), created_at=confirmed_at,
                updated_at=p.last_date, review_at=p.next_date,
            ))
        # Country evidence establishes foreign spending, not that a trip is planned or physically taken.
        foreign = [s for s in state.signals if s.profile_allowed and s.country not in {None, "BE"}
                   and s.kind == "expense" and (state.as_of-s.date).days <= 30]
        if len(foreign) >= 2:
            result.append(Inference(id=stable_id("travel", foreign[0].transaction_id),
                                    type="POSSIBLE_RECENT_TRAVEL", value="foreign_spending_cluster", confidence=.6,
                                    evidence=Evidence(transaction_ids=[s.transaction_id for s in foreign],
                                                      method="multiple_explicit_foreign_country_transactions"),
                                    created_at=foreign[1].date, updated_at=state.as_of,
                                    review_at=foreign[-1].date+dt.timedelta(days=30)))
        return result


def conditions(state: CustomerState) -> tuple[list[Condition], list[Condition]]:
    risks, opportunities = [], []
    cash = state.cash_flow
    if cash.liquidity_pressure in {"medium", "high"}:
        nxt = state.income.next_expected_income_date
        risks.append(Condition(type="LOW_PROJECTED_BALANCE", severity=cash.liquidity_pressure, confidence=.75,
                               data={"projected_balance": cash.lowest_projected_balance,
                                     "days_until_income": (nxt-state.as_of).days if nxt else None},
                               evidence=state.provenance["cash_flow.projection"]))
    if state.financial_position.overdraft and state.financial_position.overdraft > 0:
        risks.append(Condition(type="OBSERVED_OVERDRAFT", severity="high", confidence=1,
                               data={"amount": state.financial_position.overdraft},
                               evidence=state.provenance["financial_position"]))
    if state.debt.debt_service_ratio and state.debt.debt_service_ratio > .4:
        risks.append(Condition(type="HIGH_DEBT_SERVICE_RATIO", severity="medium", confidence=1,
                               data={"ratio": state.debt.debt_service_ratio},
                               evidence=state.provenance["debt.monthly_debt_service"]))
    for c in state.changes:
        if (c.type == "SUBSCRIPTION_PRICE_CHANGED" and (c.change_pct or 0) > 0
                and (state.as_of-c.detected_at).days <= 60):
            opportunities.append(Condition(type="SUBSCRIPTION_COST_INCREASE", confidence=c.confidence,
                                           data={"merchant": c.entity, "old_cost": c.previous_value,
                                                 "new_cost": c.current_value}, evidence=c.evidence))
    return risks, opportunities
