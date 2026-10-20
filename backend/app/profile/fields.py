"""The profile field registry: every fact a customer can tell us, and every purpose their data may serve.

Facts are closed vocabularies (enums, small integers, booleans, sets of enums). There is no free text, so nothing a
customer (or a prompt injection) types can end up stored and later replayed into Kate's model context. Special
categories of personal data (GDPR art. 9: health, religion, politics, sexual orientation, union membership) have no
field at all: KBC cannot store them, from a form or from a chat.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..schemas import FactValue, ProfileFactRow

# what the customer sees under "used for" on each field
USE_HOME = "your home and feed"
USE_KATE = "Kate's answers"
USE_ADVISOR = "your advisor"
USE_GOALS = "goal suggestions"


@dataclass(frozen=True)
class FieldDef:
    key: str
    label: str
    category: str          # household | work | home | money | contact
    kind: str              # enum | int | bool | set
    hint: str
    phrase: str            # "{v}" → the value label: how Kate and the evidence lines say it
    options: dict[str, str] = field(default_factory=dict)
    min: int | None = None
    max: int | None = None
    used_for: tuple[str, ...] = (USE_KATE, USE_ADVISOR)


FIELDS: dict[str, FieldDef] = {f.key: f for f in (
    FieldDef("partner", "Relationship", "household", "enum", "Shared costs and protection depend on it.",
             "you are {v}", {"single": "single", "partner": "living together", "married": "married"}),
    FieldDef("children", "Children living with you", "household", "int",
             "Your home shows family budget tools when you have children.", "you have {v}", min=0, max=12,
             used_for=(USE_HOME, USE_KATE, USE_ADVISOR)),
    FieldDef("cares_for_relative", "You care for a parent or relative", "household", "bool",
             "We can help with care costs and paperwork.", "you care for a relative",
             used_for=(USE_KATE, USE_ADVISOR, USE_GOALS)),
    FieldDef("employment", "Work", "work", "enum", "Freelancers see VAT and invoices; retirees see their pension.",
             "you are {v}", {"employee": "an employee", "self_employed": "self-employed",
                             "employee_side_job": "an employee with a side business", "student": "a student",
                             "job_seeker": "looking for work", "retired": "retired"},
             used_for=(USE_HOME, USE_KATE, USE_ADVISOR)),
    FieldDef("housing", "Where you live", "home", "enum", "Rent, a mortgage or your own home.", "you live {v}",
             {"renting": "in a rented home", "mortgage": "in your own home, with a mortgage",
              "own": "in your own home, paid off", "with_parents": "with your parents"}),
    FieldDef("risk_appetite", "Investment risk", "money", "enum", "How Kate and your advisor talk about investing.",
             "you prefer {v} investments", {"careful": "careful", "balanced": "balanced",
                                            "adventurous": "adventurous"}),
    FieldDef("contact_channel", "How we contact you", "contact", "enum", "Your advisor reaches out this way.",
             "you prefer contact {v}", {"app": "in the app", "phone": "by phone", "branch": "at the branch"}),
    FieldDef("avoid_topics", "No offers about", "contact", "set",
             "We hold back offers and goal suggestions on these topics. Alerts about your own contracts stay.",
             "you don't want offers about {v}", {"investing": "investing", "insurance": "insurance",
                                                 "credit": "loans and credit"},
             used_for=(USE_HOME, USE_KATE, USE_GOALS)),
)}


@dataclass(frozen=True)
class PurposeDef:
    purpose: str
    label: str
    description: str
    when_off: str


PURPOSE_DEFS: dict[str, PurposeDef] = {p.purpose: p for p in (
    PurposeDef("personalise_offers", "Offers based on my data",
               "KBC may use your transactions to pick the offers you see.",
               "You only see service messages and alerts, no offers."),
    PurposeDef("detect_life_events", "Spot life changes from my transactions",
               "KBC may notice changes like a move, a new job or a baby on the way, and suggest a plan.",
               "No goal suggestions from your transactions. Goals you start yourself still work."),
    PurposeDef("kate_memory", "Kate may remember what I tell her",
               "When you mention something about yourself, Kate offers to save it here. Nothing is saved "
               "without your tap.",
               "Kate won't offer to save anything you tell her."),
    PurposeDef("kate_ai", "Kate may use an AI model",
               "Kate's answers are written by an AI model (via OpenRouter, with providers that don't keep or "
               "train on your data). It sees the figures it needs for your question, never your full name.",
               "Kate answers with built-in rules only: shorter and less flexible, and nothing leaves KBC."),
    PurposeDef("advisor_view", "My advisor may see my profile",
               "Your KBC advisor can see what's on this page to prepare a conversation.",
               "Your advisor sees your products, not this profile."),
)}

# avoid_topics → playbooks KBC no longer suggests on its own, and words that mark an offer card as that topic
TOPIC_PLAYBOOKS: dict[str, frozenset[str]] = {
    "investing": frozenset({"first_investment", "retire_well"}),
    "insurance": frozenset({"travel"}),
    "credit": frozenset({"ev_switch", "mobility"}),
}
TOPIC_WORDS: dict[str, tuple[str, ...]] = {   # matched on a card's title
    "investing": ("invest", "index fund", "funds", "portfolio", "stock", "shares", "etf", "bolero", "beleg"),
    "insurance": ("insurance", "insure", "verzeker"),
    "credit": ("loan", "credit", "lease", "financing", "refinanc", "lening", "krediet"),
}


CHILD_BENEFIT_PER_CHILD_EUR = 178.0   # Groeipakket base amount, used only to propose a number to confirm


def suggestions(f) -> dict[str, tuple[FactValue, str]]:
    """Profile values the customer's own transactions point to: key → (value, the reason in plain words). They are
    shown as proposals ("We think: 1 child · Confirm") and only stored when the customer confirms. `f`: Features."""
    out: dict[str, tuple[FactValue, str]] = {}
    if f.has_child_signals:
        n = max(1, round(f.child_benefit_monthly_eur / CHILD_BENEFIT_PER_CHILD_EUR)) if f.child_benefit_monthly_eur else 1
        out["children"] = (min(n, 12), "You receive child benefit or pay for childcare")
    if f.has_pension and not f.has_salary:
        out["employment"] = ("retired", "Your pension is paid into your account")
    elif f.has_invoice_income and f.has_salary:
        out["employment"] = ("employee_side_job", "You receive a salary and invoice clients")
    elif f.has_invoice_income:
        out["employment"] = ("self_employed", "Clients pay your invoices")
    elif f.has_student_signals:
        out["employment"] = ("student", "Student job or tuition payments")
    elif f.has_salary:
        out["employment"] = ("employee", "You receive a monthly salary")
    if f.has_mortgage:
        out["housing"] = ("mortgage", "You pay off a home loan")
    elif f.has_rent:
        out["housing"] = ("renting", "You pay rent every month")
    return out


class FactError(ValueError):
    pass


def validate(key: str, value: FactValue) -> FactValue:
    """The stored form of `value` for `key`, or FactError. Sets are sorted and de-duplicated."""
    f = FIELDS.get(key)
    if f is None:
        raise FactError("Unknown profile field")
    if f.kind == "bool":
        if not isinstance(value, bool):
            raise FactError(f"{f.label}: expected yes or no")
        return value
    if f.kind == "int":
        if isinstance(value, bool) or not isinstance(value, int) or not (f.min <= value <= f.max):
            raise FactError(f"{f.label}: expected a number from {f.min} to {f.max}")
        return value
    if f.kind == "enum":
        if not isinstance(value, str) or value not in f.options:
            raise FactError(f"{f.label}: expected one of {', '.join(f.options)}")
        return value
    if not isinstance(value, list) or any(not isinstance(v, str) or v not in f.options for v in value):
        raise FactError(f"{f.label}: expected a list from {', '.join(f.options)}")
    return sorted(set(value))


def value_label(key: str, value: FactValue) -> str:
    f = FIELDS[key]
    if f.kind == "bool":
        return "yes" if value else "no"
    if f.kind == "int":
        return "no children" if value == 0 else f"{value} child{'ren' if value != 1 else ''}"
    if f.kind == "enum":
        return f.options.get(str(value), str(value))
    labels = [f.options.get(v, v) for v in value]
    return ", ".join(labels) if labels else "none"


def phrase(key: str, value: FactValue) -> str:
    """"you have 2 children", "you are self-employed": for evidence lines and Kate."""
    f = FIELDS[key]
    if f.kind == "bool":
        return f.phrase if value else f"you don't say {f.phrase}"
    return f.phrase.format(v=value_label(key, value))


def avoided(facts: list[ProfileFactRow]) -> set[str]:
    v = next((f.value for f in facts if f.key == "avoid_topics"), None)
    return set(v) if isinstance(v, list) else set()


def offer_topics(text: str) -> set[str]:
    low = text.lower()
    return {t for t, words in TOPIC_WORDS.items() if any(w in low for w in words)}


def held_back_playbooks(facts: list[ProfileFactRow]) -> set[str]:
    out: set[str] = set()
    for t in avoided(facts):
        out |= TOPIC_PLAYBOOKS.get(t, frozenset())
    return out
