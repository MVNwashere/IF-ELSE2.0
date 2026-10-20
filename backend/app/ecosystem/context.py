"""What KBC already knows about a customer at a date, so the customer is never asked twice.

- `holdings`: the products the customer has at `as_of`, derived from transactions where possible (time travel
  must not show a 2022 mortgage in 2021), mapped onto KBC catalogue items.
- `values`: the data fields a partner may receive (only through a consent grant, see service.py).
- `vars`: numbers used to fill in step results. Illustrative and derived from the customer's own data.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from ..engine.cards import gen_late_client, gen_new_payee
from ..engine.features import compute_features, fmt_date, vat_period
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
# merchants where a freelancer typically buys work gear: on the private account that's a mixing signal
BUSINESS_MERCHANTS = ("coolblue", "mediamarkt", "vanden borre", "apple store", "dell ", "lenovo", "office depot",
                      "staples", "adobe", "microsoft 365", "boekhoud", "accountan")

GARAGES = ("garage", "carrosserie", "autoservice", "bandencentrale", "kwik-fit", "carglass", "midas", "autokeuring")
FUEL = ("q8", "shell", "totalenergies", "esso", "lukoil", "dats 24")
CAR_LEASE = ("lease", "arval", "athlon", "ayvens", "leaseplan")
ESTATE = ("nalatenschap", "erfenis", "succession", "héritage")
SUBCONTRACTORS = ("onderaanneming", "onderaannemer", "sous-traitance", "freelance")
INSURER_REFUND = ("schadevergoeding", "schadeuitkering", "indemnisation", "schadegeval")

# ---- detectors for the life-event and business goals ---------------------------------------------------------------
KBO_REGISTRATION = ("kbo", "ondernemingsloket", "guichet d'entreprises")
SIDE_JOB = ("bijberoep", "complémentaire", "complementaire")
FOREIGN_CLIENT = re.compile(r"\((DE|FR|NL|UK|US|LU|ES|IT)\)$")
EU_COUNTRIES = ("DE", "FR", "NL", "LU", "ES", "IT")   # reverse charge applies to EU business clients (verify)
CARE = ("woonzorgcentrum", "wzc ", "thuiszorg", "thuisverpleging", "familiehulp", "maison de repos", "aide familiale",
        "soins à domicile")
CARE_HOME = ("woonzorgcentrum", "wzc ", "maison de repos")
RENT_DEPOSIT = ("huurwaarborg", "garantie locative")
REMOVALS = ("verhuisfirma", "verhuizingen", "verhuizing", "déménagement", "demenagement")
NEW_CONTRACT = ("nieuw contract", "nouveau contrat")
BUSINESS_TRANSFER = ("bedrijfsrevisor", "(waardering)", "(overdracht)", "overname", "cession", "transmission",
                     "réviseur")
BNPL = ("klarna", "alma", "afterpay", "riverty", "in3")
FAILED_DEBIT = ("storno", "geweigerde domiciliëring", "rejet domiciliation")
BAILIFF = ("gerechtsdeurwaarder", "deurwaarder", "huissier")
FARM_AUCTION = ("belorta", "veiling", "réa ")
FARM_SUPPLIER = ("aveve", "agrofront", "boerenbond", "arvesta", "landbouwmachines")
EV_CHARGING = ("allego", "shell recharge", "ionity", "fastned", "tesla supercharger", "blue corner", "chargepoint",
               "electra")
BONUS = ("eindejaarspremie", "13de maand", "bonus", "prime de fin d'année")
PARTNER_CONTRIBUTION = ("bijdrage huur", "bijdrage", "contribution loyer")
WEDDING = ("(huwelijk)", "trouwzaal", "trouwfeest", "weddingplanner", "mariage")
JEWELLER = ("juwelier", "bijouterie")
SEPARATION = ("echtscheiding", "scheiding", "divorce", "séparation")


def has_any(t: Transaction, keywords: tuple[str, ...]) -> bool:
    cp = t.counterparty.lower()
    return any(k in cp for k in keywords)


# the provider name starts the counterparty ("Klarna", "Alma (…)") and no number follows it: "Salma" and the
# student restaurant "Alma 2 Leuven" are not buy-now-pay-later
_BNPL_RE = re.compile(r"^(" + "|".join(BNPL) + r")\b(?!\s*\d)")


def is_bnpl(t: Transaction) -> bool:
    """A buy-now-pay-later instalment."""
    return t.amount < 0 and bool(_BNPL_RE.search(t.counterparty.lower()))


def foreign_country(t: Transaction) -> str | None:
    """'Northwind GmbH (DE)' → 'DE' for client payments; refunds and other categories don't count."""
    if t.category != "invoice_income" or t.amount <= 0:
        return None
    m = FOREIGN_CLIENT.search(t.counterparty.strip())
    return m.group(1) if m else None


def landlord(t: Transaction) -> str:
    """The landlord of a rent payment, without the '(…)' note."""
    return t.counterparty.split(" (")[0].strip().lower()


def is_garage(t: Transaction) -> bool:
    return t.amount < 0 and any(g in t.counterparty.lower() for g in GARAGES)


def is_inheritance(t: Transaction) -> bool:
    cp = t.counterparty.lower()
    return t.amount > 0 and ("notari" in cp or "notaire" in cp) and any(e in cp for e in ESTATE)


def is_subcontractor(t: Transaction) -> bool:
    return t.amount < 0 and any(s in t.counterparty.lower() for s in SUBCONTRACTORS)


def invoice_growth(txs: list[Transaction], as_of: dt.date, days: int = 120) -> tuple[float, float, float]:
    """(recent total, previous total, monthly average recent) of invoice income over two windows of `days`."""
    mid, lo = as_of - dt.timedelta(days=days), as_of - dt.timedelta(days=2 * days)
    recent = sum(t.amount for t in txs if t.category == "invoice_income" and mid < t.date <= as_of)
    prev = sum(t.amount for t in txs if t.category == "invoice_income" and lo < t.date <= mid)
    return recent, prev, recent / (days / 30.4)


# ---- freelance assumptions (illustrative; every number is labelled "estimate, verify" in the UI) -------------------
VAT_RATE = 0.21                      # standard Belgian VAT; client payments are assumed to include it
COST_RATIO = 0.20                    # assumed share of business costs in revenue excl. VAT
SOCIAL_RATE = 0.205                  # main-occupation social contribution rate on net taxable income (verify ceilings)
STARTER_PROVISIONAL_QUARTER = 890.0  # provisional quarterly minimum for a starter in main occupation (verify 2026 amount)
INCOME_TAX_RATE = 0.25               # rough income-tax share after the tax-free allowance (illustrative)
REGULARISATION_LAG_DAYS = 730        # the regularisation on real income arrives about two years later (verify)
STARTER_YEARS = 3                    # first years: provisional contributions on a fictive minimum income (verify)
VAPZ_RATE, VAPZ_CAP = 0.0817, 3800.0  # supplementary pension for the self-employed: ~8.17% of net income, capped (verify)


@dataclass
class FreelanceEstimate:
    """A freelancer's year projected from the invoices paid so far. Illustrative, from the customer's own data."""
    first_invoice: dt.date
    first_client: str
    invoices: int
    invoiced_eur: float              # paid in over the last 365 days (incl. VAT)
    monthly_gross_eur: float         # run rate incl. VAT
    yearly_net_taxable_eur: float    # excl. VAT, after assumed costs
    social_due_year_eur: float       # contributions on the real income
    provisional_year_eur: float      # what is being paid now (or the starter minimum)
    regularisation_gap_eur: float    # due minus provisional, per year
    regularisation_due: dt.date
    income_tax_year_eur: float
    starter: bool
    registration: dt.date | None     # enterprise-counter (KBO) registration, if seen
    top_client: str
    top_client_share: float


def freelance_estimate(txs: list[Transaction], as_of: dt.date) -> FreelanceEstimate | None:
    """Project a freelancer's year from the invoices paid in the last 365 days (None if there are none)."""
    lo = as_of - dt.timedelta(days=365)
    all_inv = sorted((t for t in txs if t.category == "invoice_income" and t.amount > 0 and t.date <= as_of),
                     key=lambda t: t.date)
    inv = [t for t in all_inv if t.date > lo]
    if not inv:
        return None
    first = all_inv[0]
    invoiced = sum(t.amount for t in inv)
    months = max(1.0, (as_of - inv[0].date).days / 30.4)
    monthly = invoiced / months
    net = monthly * 12 / (1 + VAT_RATE) * (1 - COST_RATIO)
    social_due = net * SOCIAL_RATE
    social_paid = sorted((t for t in txs if t.category == "social_contribution" and lo < t.date <= as_of),
                         key=lambda t: t.date)
    starter = (as_of - first.date).days <= STARTER_YEARS * 365
    if social_paid and (as_of - social_paid[0].date).days >= 270:
        provisional = -sum(t.amount for t in social_paid)
    elif social_paid:
        provisional = -sum(t.amount for t in social_paid) / len(social_paid) * 4
    else:
        provisional = STARTER_PROVISIONAL_QUARTER * 4
    by_client: dict[str, float] = {}
    for t in inv:
        by_client[t.counterparty] = by_client.get(t.counterparty, 0.0) + t.amount
    top = max(by_client, key=lambda k: by_client[k])
    reg = next((t for t in txs if first.date - dt.timedelta(days=90) <= t.date <= as_of
                and "kbo" in t.counterparty.lower()), None)
    return FreelanceEstimate(
        first_invoice=first.date, first_client=first.counterparty, invoices=len(inv), invoiced_eur=round(invoiced, 2),
        monthly_gross_eur=round(monthly, 2), yearly_net_taxable_eur=round(net, 2),
        social_due_year_eur=round(social_due, 2), provisional_year_eur=round(provisional, 2),
        regularisation_gap_eur=round(max(0.0, social_due - provisional), 2),
        regularisation_due=first.date + dt.timedelta(days=REGULARISATION_LAG_DAYS),
        income_tax_year_eur=round(max(0.0, net - social_due) * INCOME_TAX_RATE, 2),
        starter=starter, registration=reg.date if reg else None,
        top_client=top, top_client_share=round(by_client[top] / invoiced, 3),
    )


def private_business_expenses(txs: list[Transaction], as_of: dt.date, since: dt.date) -> list[Transaction]:
    """Work purchases paid from the private account since `since` (e.g. 60 days before the first invoice)."""
    return [t for t in txs if since <= t.date <= as_of and t.amount <= -50
            and any(m in t.counterparty.lower() for m in BUSINESS_MERCHANTS)]


ADVANCE_TAX_DATES = ((4, 10), (7, 10), (10, 10), (12, 20))   # Belgian advance tax payment dates (verify each year)


def next_advance_tax_date(as_of: dt.date) -> dt.date:
    """Next advance tax payment date on or after `as_of`."""
    for m, d in ADVANCE_TAX_DATES:
        if dt.date(as_of.year, m, d) >= as_of:
            return dt.date(as_of.year, m, d)
    return dt.date(as_of.year + 1, *ADVANCE_TAX_DATES[0])


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
    return f"{max(step, round(eur / 1000 / step) * step):,}".replace(",", ".")


def _eur(x: float) -> str:
    """Belgian grouping, like every amount in the app: 1950 → '1.950'."""
    return f"{round(x):,}".replace(",", ".")


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
        # VAT inside the invoices paid since the oldest quarter not yet declared (on 20 Oct: Q3, due today, + October)
        "vat_reserve": _eur(sum(t.amount for t in txs if t.category == "invoice_income" and t.amount > 0
                                and vat_period(as_of)[0] <= t.date) * VAT_RATE),
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
        ctx.vars.update(late_client=d["client"], late_since=fmt_date(as_of - dt.timedelta(days=d["days_since_last"])),
                        open_total=_eur(d["open_eur"]))
    payee = gen_new_payee(f, customer, all_txs, as_of)
    if payee:
        ctx.vars["new_payee"] = payee[0].title.split(" to ", 1)[1].split(". Was")[0]

    _freelance_vars(ctx)
    _life_vars(ctx)

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
        "vehicle": "Petrol car, about 10 years old" if any(is_garage(t) for t in txs) else "One car",
        "commute": f"Commutes from {customer.city}, a few car trips a week",
        "company_name": f"{customer.first_name} {customer.last_name} Consultancy",
        "staffing_need": "1 flexible worker, about 2 days a week",
        "care_need": _care_need(txs, as_of),
        "debt_overview": _debt_overview(txs, as_of),
    }
    return ctx


def _care_need(txs: list[Transaction], as_of: dt.date) -> str:
    """'Residential care since 1 Aug 2026, about €1,850 a month', from the customer's own care payments."""
    care = sorted((t for t in txs if t.amount < 0 and has_any(t, CARE)), key=lambda t: t.date)
    if not care:
        return "No care payments seen yet"
    recent = [t for t in care if (as_of - t.date).days <= 120] or care[-1:]
    monthly = -sum(t.amount for t in recent) / max(1.0, (recent[-1].date - recent[0].date).days / 30.4 + 1)
    kind = "Residential care" if any(has_any(t, CARE_HOME) for t in recent) else "Care at home"
    return f"{kind} since {fmt_date(care[0].date)}, about €{_eur(monthly)} a month"


def _debt_overview(txs: list[Transaction], as_of: dt.date) -> str:
    """Buy-now-pay-later instalments, bounced direct debits and bailiff payments in the last 90 days."""
    lo = as_of - dt.timedelta(days=90)
    recent = [t for t in txs if t.date > lo]
    bnpl = [t for t in recent if is_bnpl(t)]
    failed = [t for t in recent if has_any(t, FAILED_DEBIT)]
    bailiff = [t for t in recent if t.amount < 0 and has_any(t, BAILIFF)]
    parts = []
    if bnpl:
        parts.append(f"{len(bnpl)} buy-now-pay-later instalments (€{_eur(-sum(t.amount for t in bnpl))})")
    if failed:
        parts.append(f"{len(failed)} bounced direct debit{'s' if len(failed) != 1 else ''}")
    if bailiff:
        parts.append(f"bailiff payments of €{_eur(-sum(t.amount for t in bailiff))}")
    return ("Last 3 months: " + ", ".join(parts)) if parts else "No arrears seen in the last 3 months"



def _freelance_vars(ctx: CustomerContext) -> None:
    """Numbers for the go_freelance results (illustrative; the playbook hedges the wording)."""
    as_of, txs = ctx.as_of, ctx.txs
    fe = freelance_estimate(txs, as_of)
    v = ctx.vars
    v.update(regularisation_gap="…", regularisation_due="…", regularisation_pct="…", reserve_pct="…",
             reserve_now="0", social_provisional_quarter=_eur(STARTER_PROVISIONAL_QUARTER), social_due_year="…",
             income_tax_year="…", advance_tax_quarter="…", advance_tax_next=fmt_date(next_advance_tax_date(as_of)),
             vapz_monthly="150", income_insured_monthly="2,000", first_invoice_date="…", first_client="your client",
             kbo_date="…", top_client="your main client", top_client_pct="…",
             private_expenses_total="0", private_expenses_items="no business purchases")
    if not fe:
        return
    gross_year = max(fe.monthly_gross_eur * 12, 1.0)
    reg_pct = fe.regularisation_gap_eur / gross_year * 100
    tax_pct = fe.income_tax_year_eur / gross_year * 100
    vat_pct = VAT_RATE / (1 + VAT_RATE) * 100
    reserve_pct = vat_pct + tax_pct + reg_pct
    paid_in = sum(t.amount for t in txs if t.category == "invoice_income" and t.amount > 0
                  and t.date > as_of - dt.timedelta(days=365))
    expenses = private_business_expenses(txs, as_of, fe.first_invoice - dt.timedelta(days=60))
    v.update(
        regularisation_gap=_eur(fe.regularisation_gap_eur),
        regularisation_due=fe.regularisation_due.strftime("%b %Y"),
        regularisation_pct=f"{reg_pct:.0f}",
        reserve_pct=f"{reserve_pct:.0f}",
        reserve_now=_eur(paid_in * reserve_pct / 100),
        social_provisional_quarter=_eur(fe.provisional_year_eur / 4),
        social_due_year=_eur(fe.social_due_year_eur),
        income_tax_year=_eur(fe.income_tax_year_eur),
        advance_tax_quarter=_eur(round(fe.income_tax_year_eur / 4, -1)),
        vapz_monthly=_eur(round(min(fe.yearly_net_taxable_eur * VAPZ_RATE, VAPZ_CAP) / 12, -1)),
        income_insured_monthly=_eur(max(1000.0, round(fe.yearly_net_taxable_eur / 12 * 0.7, -2))),
        first_invoice_date=fmt_date(fe.first_invoice),
        first_client=fe.first_client,
        kbo_date=fmt_date(fe.registration) if fe.registration else "…",
        top_client=fe.top_client,
        top_client_pct=f"{fe.top_client_share * 100:.0f}",
        private_expenses_total=_eur(-sum(t.amount for t in expenses)),
        private_expenses_items=", ".join(f"{t.counterparty.split(' (')[0]} on {fmt_date(t.date)}" for t in expenses[:3])
        or "no business purchases",
    )


def _life_vars(ctx: CustomerContext) -> None:
    """Numbers for the mobility, first_employee, inheritance, study_start and job_change results."""
    as_of, txs, f, v = ctx.as_of, ctx.txs, ctx.features, ctx.vars
    year_ago = as_of - dt.timedelta(days=365)
    repairs = -sum(t.amount for t in txs if is_garage(t) and t.date > year_ago)
    fuel = -sum(t.amount for t in txs if t.amount < 0 and t.date > year_ago and any(x in t.counterparty.lower() for x in FUEL))
    car_ins = -sum(t.amount for t in txs if t.category == "insurance_car" and t.date > year_ago)
    recent, prev, monthly = invoice_growth(txs, as_of)
    inheritance = sum(t.amount for t in txs if is_inheritance(t) and t.date > year_ago)
    tuition = [t for t in txs if t.category == "tuition" and t.date > year_ago]
    spend = max(f.monthly_spend_avg_90d, 500.0)
    v.update(
        car_repairs_total=_eur(repairs),
        car_monthly=_eur((repairs + fuel + car_ins) / 12 + 150),   # + an illustrative €150 a month depreciation
        invoice_growth_pct=f"{max(0.0, (recent / prev - 1) * 100) if prev > 0 else 0:.0f}",
        invoice_monthly=_eur(round(monthly, -1)),
        inheritance_k=_k(inheritance, 1) if inheritance else "…",
        tuition=_eur(-tuition[-1].amount) if tuition else "…",
        study_monthly=_eur(650),   # a student room plus living costs, illustrative
        buffer_months=f"{max(0.0, f.balance_eur) / spend:.1f}",
    )


def apply_sources(ctx: CustomerContext, source_values: dict[str, str | float]) -> CustomerContext:
    """Replace our own estimates with values from data sources the customer connected (sources.py), so a
    connected mypension.be or EPC record gives exact numbers instead of rules of thumb."""
    if not source_values:
        return ctx
    v = source_values
    ctx.vars["sources"] = ", ".join(sorted(v))
    if isinstance(v.get("pension_statutory_monthly_eur"), (int, float)):
        pension = float(v["pension_statutory_monthly_eur"])
        spend = max(ctx.features.monthly_spend_avg_90d, 500.0)
        ctx.vars["pension_est"] = _eur(pension)
        ctx.vars["pension_gap"] = _eur(max(200.0, spend * 0.8 - pension))
    if v.get("company_number"):
        ctx.values["company_number"] = str(v["company_number"])
    if v.get("epc_label"):
        kwh = f" ({v['epc_kwh_m2']} kWh/m²)" if v.get("epc_kwh_m2") else ""
        ctx.values["property_details"] = f"Terraced house, built 1978, 140 m², EPC label {v['epc_label']}{kwh}"
    if isinstance(v.get("electricity_kwh_year"), (int, float)):
        gas = f", {v['gas_kwh_year']:,.0f} kWh gas" if isinstance(v.get("gas_kwh_year"), (int, float)) else ""
        ctx.values["energy_use"] = f"{v['electricity_kwh_year']:,.0f} kWh electricity a year{gas} (digital meter)"
    if isinstance(v.get("open_invoices_eur"), (int, float)) and v["open_invoices_eur"] > 0:
        ctx.vars["open_total"] = _eur(float(v["open_invoices_eur"]))
    if isinstance(v.get("regularisation_eur"), (int, float)) and v["regularisation_eur"] > 0:
        ctx.vars["regularisation_gap"] = _eur(float(v["regularisation_eur"]))
    return ctx
