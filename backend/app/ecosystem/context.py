"""What KBC already knows about a customer at a date, so the customer is never asked twice.

- `holdings`: the products the customer has at `as_of`, derived from transactions where possible (time travel
  must not show a 2022 mortgage in 2021), mapped onto KBC catalogue items.
- `values`: the data fields a partner may receive (only through a consent grant, see consent.py).
- `vars`: numbers used to fill in step results. Illustrative and derived from the customer's own data.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from ..engine.cards import gen_late_client, gen_new_payee
from ..engine.features import compute_features, fmt_date
from ..schemas import Customer, Features, Transaction

# internal product code → KBC catalogue item
HOLDING_CATALOGUE = {
    "current": "kbc-plus-account",
    "savings": "savings-accounts",
    "mortgage": "home-loan",
    "home_insurance": "home-insurance",
    "family_insurance": "family-insurance",
    "pension_savings": "pension-savings-fund",
    "business_account": "kbc-business-pro-account",
}
# products we can date from transactions; the others come from the customer record
DERIVABLE = {"savings", "mortgage", "home_insurance", "family_insurance", "pension_savings"}
TRAVEL_MERCHANTS = ("brussels airlines", "ryanair", "tui", "neckermann", "booking.com", "airbnb", "sunweb",
                    "expedia", "transavia", "corendon")
PROPERTY_SEARCH = ("zimmo", "immoweb", "immovlan", "immoscoop")


@dataclass
class CustomerContext:
    customer: Customer
    as_of: dt.date
    features: Features
    txs: list[Transaction]                          # up to and including as_of
    holdings: set[str] = field(default_factory=set)  # internal product codes
    values: dict[str, str] = field(default_factory=dict)
    vars: dict[str, str] = field(default_factory=dict)

    def fill(self, template: str) -> str:
        """Fill a playbook result template. Unknown placeholders stay readable instead of raising."""
        class _Safe(dict):
            def __missing__(self, key: str) -> str:
                return "…"
        return template.format_map(_Safe(self.vars))


def _k(eur: float, step: int = 5) -> str:
    """€187,400 → '185' (thousands, rounded to `step`)."""
    return f"{max(step, round(eur / 1000 / step) * step):,}"


def _eur(x: float) -> str:
    return f"{round(x):,}"


def holdings_at(customer: Customer, txs: list[Transaction], f: Features) -> set[str]:
    held = {p for p in customer.products if p not in DERIVABLE}
    cps = [(t.category, t.counterparty.lower()) for t in txs]
    if f.has_savings_product or any(c == "savings_transfer" and "spaarrekening" in cp for c, cp in cps):
        held.add("savings")
    if any(c == "mortgage" for c, _ in cps):
        held.add("mortgage")
    if any(c == "insurance_home" and "kbc" in cp for c, cp in cps):
        held.add("home_insurance")
    if any(c == "insurance_family" and "kbc" in cp for c, cp in cps):
        held.add("family_insurance")
    if any("pensioensparen" in cp or "pensioenspaar" in cp for _, cp in cps):
        held.add("pension_savings")
    return held


def _monthly(txs: list[Transaction], category: str, lo: dt.date, hi: dt.date) -> float:
    total = -sum(t.amount for t in txs if t.category == category and lo < t.date <= hi and t.amount < 0)
    return total / max(1.0, (hi - lo).days / 30.4)


def build_context(customer: Customer, all_txs: list[Transaction], balance_today: float,
                  as_of: dt.date) -> CustomerContext:
    f = compute_features(customer, all_txs, balance_today, as_of)
    txs = [t for t in all_txs if t.date <= as_of]
    ctx = CustomerContext(customer=customer, as_of=as_of, features=f, txs=txs)
    ctx.holdings = holdings_at(customer, txs, f)

    income = max(f.monthly_income_avg_90d, 0.0)
    spend = max(f.monthly_spend_avg_90d, 500.0)
    balance = f.balance_eur
    # housing budget: a third of income on repayments, 25 years at about 3% (annuity factor ≈ 211), plus own funds
    loan = income / 3 * 211
    own = max(0.0, balance - 3 * spend) + sum(-t.amount for t in txs if t.category == "property" and t.amount < -5000)
    budget = loan + own
    price = budget * 0.92
    children = f.has_child_signals
    utilities_recent = _monthly(txs, "utilities", as_of - dt.timedelta(days=120), as_of)
    utilities_before = _monthly(txs, "utilities", as_of - dt.timedelta(days=485), as_of - dt.timedelta(days=365))
    if utilities_before <= 0:
        utilities_before = utilities_recent
    trip = next((t for t in reversed(txs) if t.amount < -200
                 and any(m in t.counterparty.lower() for m in TRAVEL_MERCHANTS)), None)
    travel_date = (trip.date + dt.timedelta(days=30)) if trip else as_of + dt.timedelta(days=30)
    pension_est = min(income * 0.55, 2300.0)

    ctx.vars = {
        "first_name": customer.first_name,
        "region": customer.city,
        "budget_max_k": _k(budget),
        "buffer_k": _k(6 * spend, 1),
        "price_k": _k(price),
        "loan_k": _k(price * 0.8 + 28_500),
        "property_address": f"Kerkstraat 14, {customer.city}",
        "energy_before": _eur(utilities_before),
        "energy_after": _eur(max(utilities_recent, utilities_before)),
        "vat_reserve": _eur(f.vat_period_invoice_income_eur * 0.21),
        # childcare usually starts after maternity leave: assume a typical crèche bill until we see the real one
        "baby_monthly": _eur(max(f.childcare_monthly_eur, 450) + max(f.spend_by_category_30d.get("baby", 0), 120)),
        "destination": "Portugal",
        "travel_date": fmt_date(travel_date),
        "pension_est": _eur(pension_est),
        "pension_gap": _eur(max(200.0, spend * 0.8 - pension_est)),
        "invest_k": _k(max(0.0, balance - 6 * spend)),
        "idle_k": _k(max(1000.0, balance - 5000), 1),
        "late_client": "A client", "late_since": "a while", "open_total": "0",
        "new_payee": "an unknown company",
    }
    late = gen_late_client(f, customer, all_txs, as_of)
    if late:
        d = late[0].details
        name = late[0].title.split(" usually pays")[0]
        missed = max(1, round(d["days_since_last"] / max(d["median_gap_days"], 1)) - 1)
        ctx.vars.update(late_client=name, late_since=fmt_date(as_of - dt.timedelta(days=d["days_since_last"])),
                        open_total=_eur(late[0].eur_impact * missed))
    payee = gen_new_payee(f, customer, all_txs, as_of)
    if payee:
        ctx.vars["new_payee"] = payee[0].title.split(" to ", 1)[1].split(". Was")[0]

    first, last = customer.first_name.lower(), customer.last_name.lower()
    ctx.values = {
        "first_name": customer.first_name,
        "email": f"{first}.{last}@example.com",
        "region": customer.city,
        "budget_range": f"€{_k(budget * 0.8)}k–€{_k(budget)}k",
        "property_address": ctx.vars["property_address"],
        "property_details": "Terraced house, built 1978, 140 m², EPC label D",
        "household": "2 adults" + (", 1 child" if children else ""),
        "income": f"€{_eur(income)} a month",
        "balances": f"€{_eur(balance)}",
        "transactions": f"{len(txs)} transactions",
        "energy_use": f"about €{_eur(max(utilities_recent, utilities_before) * 12)} a year",
        "chosen_works": "Roof insulation, heat pump",
        "company_number": "BE 0712.345.678",
        "open_invoices": f"Open invoices to {ctx.vars['late_client']}, about €{ctx.vars['open_total']}",
        "travel_dates": f"from {fmt_date(travel_date)}",
        "destination": ctx.vars["destination"],
        "birth_year": str(customer.birth_year),
        "investor_profile": "Defensive, horizon 15 years",
        "family_situation": "Partner" + (", children" if children else ""),
    }
    return ctx

