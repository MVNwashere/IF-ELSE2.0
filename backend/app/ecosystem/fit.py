"""Which goals fit a customer: a life area per goal and a transparent fit rule, so the Goals tab can lead with what
matters and set aside what clearly doesn't ("Start as a freelancer" for someone who already invoices clients).

fit: "suggested" (KBC detected it: a GoalCandidate), "open" (could be relevant; the customer decides) or "unlikely"
(a stated rule says it doesn't match the customer's situation today). Unlikely goals stay available: the customer can
always state a goal themselves, KBC only stops putting it forward.
"""
from __future__ import annotations

from typing import Callable

from ..schemas import Features

AREAS = ("Work and business", "Home", "Family", "Money and safety", "Getting around")
AREA: dict[str, str] = {
    **dict.fromkeys(["go_freelance", "get_paid", "first_employee", "go_international", "side_job", "sell_business",
                     "farm_growth", "job_change"], "Work and business"),
    **dict.fromkeys(["buy_home", "move_house", "energy_upgrade", "together", "separation"], "Home"),
    **dict.fromkeys(["new_baby", "study_start", "care_parent", "inheritance"], "Family"),
    **dict.fromkeys(["back_on_track", "first_investment", "retire_well", "peace_of_mind"], "Money and safety"),
    **dict.fromkeys(["travel", "mobility", "ev_switch"], "Getting around"),
}

BUSINESS = "For people who run their own business"
Rule = Callable[[Features], str | None]
RULES: dict[str, Rule] = {
    "go_freelance": lambda f: "You already invoice clients" if f.has_invoice_income else None,
    "side_job": lambda f: ("You already work for yourself" if f.has_invoice_income and not f.has_salary
                           else "For people with a salaried job" if not f.has_salary else None),
    "get_paid": lambda f: None if f.has_invoice_income else BUSINESS,
    "first_employee": lambda f: None if f.has_invoice_income else BUSINESS,
    "go_international": lambda f: None if f.has_invoice_income else BUSINESS,
    "sell_business": lambda f: None if f.has_invoice_income and f.age >= 45 else BUSINESS + " and plan to hand it over",
    "farm_growth": lambda f: "For farmers and growers",   # only ever shown when the farm detector suggests it
    "job_change": lambda f: None if f.has_salary else "For people with a salaried job",
    "buy_home": lambda f: "You already own a home" if f.has_mortgage else None,
    "energy_upgrade": lambda f: "For home owners" if f.has_rent and not f.has_mortgage else None,
    "study_start": lambda f: None if f.has_child_signals and f.age >= 40 else "For parents of a student-to-be",
    "care_parent": lambda f: "Usually later in life" if f.age < 35 else None,
    "retire_well": lambda f: ("You're already retired" if f.has_pension and not f.has_salary
                              else "Makes most sense from your mid-forties" if f.age < 45 else None),
    "new_baby": lambda f: "Usually earlier in life" if f.age >= 50 else None,
}


def playbook_fit(playbook_id: str, f: Features, suggested: set[str]) -> tuple[str, str]:
    """(fit, reason). A detected goal is always suggested, whatever the static rule says."""
    if playbook_id in suggested:
        return "suggested", "KBC noticed this in your own transactions"
    rule = RULES.get(playbook_id)
    reason = rule(f) if rule else None
    return ("unlikely", reason) if reason else ("open", "")
