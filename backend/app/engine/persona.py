"""Features → persona mix (weights, not a label). Every weight carries plain-English evidence."""
from __future__ import annotations

from ..schemas import PERSONAS, DeclaredSignalRow, Features, Persona, PersonaWeight
from .features import fmt_date, fmt_eur

# ---- tuning knobs -----------------------------------------------------------------
MIN_WEIGHT = 0.15                 # weights below this are dropped, then renormalised
STUDENT_MAX_AGE = 26
YOUNG_PRO_MAX_AGE = 36
RETIREE_AGE = 67
REGULAR_INCOME_CV = 0.25          # coefficient of variation below this = "steady salary"
FAMILY_SHARE_SCALE = 3.0          # family flows at a third of income already count as "fully family"
FREELANCER_RAMP_MONTHS = 12       # the invoice-share contribution ramps up over the first year self-employed
SCORE = {                         # raw-score contributions, capped at 1.0 per persona
    "student_age_and_signal": 0.7,
    "student_income": 0.2,
    "student_allowance": 0.2,
    "student_tuition": 0.2,
    "yp_salary": 0.6,
    "yp_steady": 0.2,
    "yp_age": 0.2,
    "yp_fallback": 0.3,
    "family_base": 0.3,            # any child signal
    "family_share": 0.7,           # × min(1, FAMILY_SHARE_SCALE × family cash flow / monthly income)
    "freelancer_base_strong": 0.4, # ≥2 clients or VAT payments
    "freelancer_base_weak": 0.2,   # a single invoice payer
    "freelancer_share": 0.6,       # × invoice share of income over 180 days
    "retiree_pension": 0.8,
    "retiree_age": 0.5,
    "declared": 0.6,               # the customer told Kate (e.g. "we're expecting"): strong, but not absolute
}
DECLARED_PERSONA: dict[str, Persona] = {
    "expecting_baby": "young_family",
    "going_freelance": "freelancer",
    "retiring": "retiree",
    "studying": "student",
}
DECLARED_PHRASE = {
    "expecting_baby": "you're expecting a baby",
    "going_freelance": "you're going freelance",
    "retiring": "you're retiring",
    "studying": "you're studying",
}


def _score_student(f: Features) -> tuple[float, list[str]]:
    s, ev = 0.0, []
    if f.age >= STUDENT_MAX_AGE or not f.has_student_signals:
        return 0.0, ev
    s += SCORE["student_age_and_signal"]
    ev.append(f"You're {f.age} and have student-typical money flows")
    inc = f.income_by_category_180d
    if inc.get("student_income", 0) > 0:
        s += SCORE["student_income"]
        ev.append(f"Student job income of {fmt_eur(inc['student_income'])} in the last 6 months")
    if inc.get("allowance_from_parents", 0) > 0:
        s += SCORE["student_allowance"]
        ev.append(f"Regular allowance of {fmt_eur(inc['allowance_from_parents'])} over 6 months")
    if f.has_student_signals and "tuition" in {r.category for r in f.recurring_payments}:
        s += SCORE["student_tuition"]
        ev.append("Yearly tuition payment")
    return s, ev


def _score_young_professional(f: Features) -> tuple[float, list[str]]:
    s, ev = 0.0, []
    if f.has_salary and not f.has_child_signals:
        s += SCORE["yp_salary"]
        ev.append(f"Monthly salary, about {fmt_eur(round(f.monthly_income_avg_90d))} per month")
        if f.income_regularity < REGULAR_INCOME_CV:
            s += SCORE["yp_steady"]
            ev.append("Income is very regular")
        if f.age < YOUNG_PRO_MAX_AGE:
            s += SCORE["yp_age"]
            ev.append(f"You're {f.age}")
    return s, ev


def _score_young_family(f: Features) -> tuple[float, list[str]]:
    ev: list[str] = []
    child_spend_30 = sum(v for k, v in f.spend_by_category_30d.items() if k in ("baby", "school"))
    family_flow = f.child_benefit_monthly_eur + f.childcare_monthly_eur + child_spend_30
    if family_flow <= 0 and not f.has_child_signals:
        return 0.0, ev
    if f.child_benefit_monthly_eur > 0:
        ev.append(f"Monthly child benefit (Groeipakket) of {fmt_eur(round(f.child_benefit_monthly_eur))}")
    if f.childcare_monthly_eur > 0:
        ev.append(f"Regular childcare payments, about {fmt_eur(round(f.childcare_monthly_eur))} per month")
    if child_spend_30 > 0:
        ev.append(f"{fmt_eur(child_spend_30)} on baby or school items this month")
    if not ev:
        ev.append("Family-related payments in the last 6 months")
    income = max(f.monthly_income_avg_90d, 1.0)
    share = min(1.0, FAMILY_SHARE_SCALE * family_flow / income)
    return SCORE["family_base"] + SCORE["family_share"] * share, ev


def _score_freelancer(f: Features) -> tuple[float, list[str]]:
    ev: list[str] = []
    if not (f.has_invoice_income or f.has_vat_payments or f.has_social_contributions):
        return 0.0, ev
    inc = f.income_by_category_180d
    total = sum(inc.values())
    invoice_share = inc.get("invoice_income", 0.0) / total if total > 0 else 0.0
    # income_sources_180d counts every payer; each non-invoice income category is ~one payer
    other_sources = sum(1 for k in inc if k != "invoice_income")
    payers = max(1, f.income_sources_180d - other_sources) if f.has_invoice_income else 0
    strong = payers >= 2 or f.has_vat_payments
    s = SCORE["freelancer_base_strong"] if strong else SCORE["freelancer_base_weak"]
    first_invoice = next((e for e in f.life_events if e.type == "first_invoice"), None)
    tenure = 1.0
    if first_invoice is not None:
        months = (f.as_of - first_invoice.date).days / 30
        tenure = min(1.0, months / FREELANCER_RAMP_MONTHS)
    s += SCORE["freelancer_share"] * invoice_share * tenure
    if payers >= 2:
        ev.append(f"Income from {payers} different clients in the last 6 months")
    elif f.has_invoice_income:
        ev.append("Invoice income in the last 6 months")
    if invoice_share > 0:
        ev.append(f"{round(invoice_share * 100)}% of your income comes from invoices")
    if first_invoice is not None and tenure < 1.0:
        ev.append(f"Self-employed since {fmt_date(first_invoice.date)}")
    if f.has_vat_payments:
        ev.append("Quarterly VAT payments to FOD Financiën")
    if f.has_social_contributions:
        ev.append("Quarterly social contributions as self-employed")
    return s, ev


def _score_retiree(f: Features) -> tuple[float, list[str]]:
    s, ev = 0.0, []
    if f.has_pension:
        s += SCORE["retiree_pension"]
        pension_start = next((e for e in f.life_events if e.type == "pension_start"), None)
        ev.append("Monthly pension" + (f" since {fmt_date(pension_start.date)}" if pension_start else ""))
    if f.age >= RETIREE_AGE:
        s += SCORE["retiree_age"]
        ev.append(f"You're {f.age}")
    return s, ev


_SCORERS = {
    "student": _score_student,
    "young_professional": _score_young_professional,
    "young_family": _score_young_family,
    "freelancer": _score_freelancer,
    "retiree": _score_retiree,
}


def _apply_declared(raw: dict[str, tuple[float, list[str]]], declared: list[DeclaredSignalRow],
                    as_of) -> dict[str, tuple[float, list[str]]]:
    """Things the customer told Kate count as signals too, from the day they said it (time travel respects it)."""
    out = dict(raw)
    for d in declared:
        if d.created_at > as_of:
            continue
        p = DECLARED_PERSONA[d.signal]
        s, ev = out[p]
        out[p] = (s + SCORE["declared"], [f"You told Kate on {fmt_date(d.created_at)} that {DECLARED_PHRASE[d.signal]}"] + ev)
    return out


def infer_persona_mix(features: Features, declared: list[DeclaredSignalRow] | None = None) -> list[PersonaWeight]:
    raw: dict[str, tuple[float, list[str]]] = {p: _SCORERS[p](features) for p in PERSONAS}
    if declared:
        raw = _apply_declared(raw, declared, features.as_of)
    total = sum(s for s, _ in raw.values())
    if total <= 0:
        return [PersonaWeight(persona="young_professional", weight=1.0,
                              evidence=["No strong signals yet, so we start from a general profile"])]
    weights = {p: s / total for p, (s, _) in raw.items()}
    kept = {p: w for p, w in weights.items() if w >= MIN_WEIGHT}
    if not kept:  # can't happen mathematically with ≤5 personas, but keep it safe
        top = max(weights, key=weights.get)
        kept = {top: weights[top]}
    norm = sum(kept.values())
    mix = [PersonaWeight(persona=p, weight=round(w / norm, 3), evidence=raw[p][1]) for p, w in kept.items()]
    mix.sort(key=lambda pw: (-pw.weight, PERSONAS.index(pw.persona)))
    # make weights sum to exactly 1.0 after rounding
    drift = round(1.0 - sum(pw.weight for pw in mix), 3)
    if drift and mix:
        mix[0].weight = round(mix[0].weight + drift, 3)
    return mix


def dominant(persona_mix: list[PersonaWeight]) -> Persona:
    return max(persona_mix, key=lambda pw: pw.weight).persona if persona_mix else "young_professional"
