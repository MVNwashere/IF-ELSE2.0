"""Synthetic customers + transactions for the KBC Adaptive Home PoC.

Everything is fake and deterministic under a seed. Scenarios are injected and recorded in
`customers.ground_truth` (never returned to customers) so the engine can be evaluated.

Run from backend/:
    py -3.12 -m synth.generate --n 1000 --seed 42 [--db path/to/kbc.db]
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import os
import random
from collections import Counter

from app import db
from app.auth import hash_password
from app.schemas import CATEGORIES, INCOME_CATEGORIES, Customer, Transaction

TODAY = dt.date(2026, 9, 30)
REGULAR_HISTORY_DAYS = 400
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "demo")

# ----------------------------------------------------------------------------------
# Vocabulary (Belgian flavour)
# ----------------------------------------------------------------------------------

NL_FIRST = ["Lotte", "Sara", "Jan", "Wout", "Marie", "Lucas", "Emma", "Noor", "Arthur", "Lena", "Milan", "Fien",
            "Seppe", "Ilse", "Bram", "Els", "Tom", "An", "Pieter", "Greet", "Rik", "Hilde", "Dries", "Veerle",
            "Koen", "Nele", "Jef", "Mia", "Stijn", "Lore", "Bert", "Katrien", "Ward", "Tine"]
FR_FIRST = ["Camille", "Louis", "Chloé", "Hugo", "Manon", "Nathan", "Léa", "Théo", "Julie", "Maxime", "Inès",
            "Adrien", "Zoé", "Antoine", "Claire", "Julien", "Sophie", "Nicolas", "Amélie", "Pierre", "Céline",
            "Baptiste", "Elise", "Olivier", "Margaux", "Simon", "Laure", "Florian"]
NL_LAST = ["Peeters", "Janssens", "Maes", "Jacobs", "Mertens", "Willems", "Claes", "Goossens", "Wouters",
           "De Smet", "Vermeulen", "Van den Broeck", "De Backer", "Lambrechts", "Verhoeven", "Pauwels"]
FR_LAST = ["Dubois", "Lambert", "Martin", "Dupont", "Simon", "Leroy", "Laurent", "Lemaire", "Renard",
           "Fontaine", "Gérard", "Petit", "Bertrand", "Mercier"]
NL_CITIES = ["Leuven", "Gent", "Antwerpen", "Brugge", "Mechelen", "Hasselt", "Kortrijk", "Aalst", "Genk", "Roeselare"]
FR_CITIES = ["Liège", "Namur", "Charleroi", "Mons", "Wavre", "Tournai", "Arlon"]

GROCERS = ["Colruyt", "Delhaize", "Albert Heijn", "Lidl", "Carrefour Market", "Aldi", "Okay"]
LEISURE = ["Kinepolis", "Brasserie Lamot", "Frituur 't Hoekske", "Bol.com", "Decathlon", "Standaard Boekhandel",
           "Café Central", "Pizza Hut", "Zalando", "Fnac"]
TRANSPORT = ["De Lijn", "NMBS", "Q8", "TotalEnergies", "Shell", "TEC", "Cambio"]
OTHER = ["Kruidvat", "Action", "Brico", "Apotheek Lloyds", "bpost", "Hema"]
HEALTHCARE = ["Apotheek Lloyds", "Dr. Peeters huisarts", "AZ Monica", "Kinesist Van Dyck", "UZ Leuven", "Optiek Verlinden"]
BABY = ["Dreambaby", "Kruidvat Baby", "Prémaman", "Baby-Dump"]
SCHOOL = ["Basisschool De Regenboog", "Studieshop.be", "Schoolfactuur GO! Atheneum"]
UTILITIES = ["Engie", "Luminus", "Farys", "De Watergroep"]
TELECOM = ["Proximus", "Telenet", "Orange Belgium"]
EMPLOYERS = ["Colruyt Group", "Cronos Groep", "UZ Leuven", "Stad Gent", "Proximus NV", "Bekaert", "Solvay",
             "Delhaize Le Lion", "Barco", "Umicore", "AB InBev", "Vlaamse Overheid", "Materialise", "Deme"]
CLIENTS = ["Studio Nord", "Bright Agency", "Gemeente Herent", "Vzw Kompas", "Dupont & Co", "Bakkerij Peeters",
           "Atelier Vos", "Vzw De Kring", "Maes Consulting", "Boekhandel Limerick", "Brasserie Lamot",
           "Van Hool Design", "Immo Verstraete", "Dokters Van Wacht", "Sofico BV", "Greenpark NV"]
DAYCARES = ["Kinderdagverblijf De Speelboom", "Kinderdagverblijf 't Nest", "Crèche Les Petits Loups",
            "Kinderopvang Zonnebloem"]
EXTERNAL_INSURERS = ["AG Insurance", "Ethias", "Baloise"]
KBC_INSURANCE = "KBC Verzekeringen"
SUBSCRIPTIONS = [("Netflix", 13.99, 17.99), ("Spotify", 10.99, 12.99), ("Disney+", 8.99, 11.99),
                 ("Streamz", 12.99, 14.99)]
SOCIAL_FUNDS = ["Xerius", "RSVZ", "Liantis", "Acerta"]
PENSION_PAYER = "Federale Pensioendienst"
CHILD_BENEFIT_PAYER = "Fons (Groeipakket)"
TAX_OFFICE = "FOD Financiën"

VARIABLE_CATEGORIES = {"groceries", "leisure", "transport", "other"}

# ----------------------------------------------------------------------------------
# Date helpers
# ----------------------------------------------------------------------------------


def safe_date(y: int, m: int, d: int) -> dt.date:
    return dt.date(y, m, min(d, calendar.monthrange(y, m)[1]))


def add_months(d: dt.date, n: int) -> dt.date:
    m = d.month - 1 + n
    y = d.year + m // 12
    return safe_date(y, m % 12 + 1, d.day)


def months_between(start: dt.date, end: dt.date):
    """Yield (year, month) for every calendar month overlapping [start, end]."""
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        m += 1
        if m > 12:
            m, y = 1, y + 1


def quarter_of(d: dt.date) -> int:
    return (d.month - 1) // 3 + 1


# ----------------------------------------------------------------------------------
# Transaction builder
# ----------------------------------------------------------------------------------


class TxBuilder:
    """Accumulates transactions for one customer. Amounts are given as positive numbers;
    the sign is derived from the category (income +, everything else −)."""

    def __init__(self, customer_id: int, rng: random.Random, start: dt.date, end: dt.date):
        self.cid = customer_id
        self.rng = rng
        self.start = start
        self.end = end
        self.txs: list[Transaction] = []

    def add(self, d: dt.date, amount: float, category: str, counterparty: str) -> None:
        if d < self.start or d > self.end:
            return
        assert category in CATEGORIES, category
        signed = abs(amount) if category in INCOME_CATEGORIES else -abs(amount)
        self.txs.append(Transaction(id=0, customer_id=self.cid, date=d, amount=round(signed, 2),
                                    category=category, counterparty=counterparty[:80]))

    def add_signed(self, d: dt.date, signed_amount: float, category: str, counterparty: str) -> None:
        """Bypass the category sign rule (e.g. a transfer *from* savings into the current account)."""
        if d < self.start or d > self.end:
            return
        assert category in CATEGORIES, category
        self.txs.append(Transaction(id=0, customer_id=self.cid, date=d, amount=round(signed_amount, 2),
                                    category=category, counterparty=counterparty[:80]))

    def monthly(self, start: dt.date, end: dt.date, day: int, amount, category: str, counterparty: str,
                jitter_amount: float = 0.0, jitter_days: int = 0) -> None:
        """`amount` may be a number or a callable(date) -> number."""
        for y, m in months_between(start, end):
            d = safe_date(y, m, day)
            if jitter_days:
                d = d + dt.timedelta(days=self.rng.randint(-jitter_days, jitter_days))
            if d < start or d > end:
                continue
            a = amount(d) if callable(amount) else amount
            if jitter_amount:
                a = a * self.rng.uniform(1 - jitter_amount, 1 + jitter_amount)
            self.add(d, a, category, counterparty)

    def yearly(self, start: dt.date, end: dt.date, month: int, day: int, amount, category: str,
               counterparty: str) -> None:
        for y in range(start.year, end.year + 1):
            d = safe_date(y, month, day)
            if start <= d <= end:
                a = amount(d) if callable(amount) else amount
                self.add(d, a, category, counterparty)

    def scatter(self, start: dt.date, end: dt.date, category: str, counterparties: list[str],
                per_month: float, lo: float, hi: float) -> None:
        for y, m in months_between(start, end):
            n = max(0, int(round(self.rng.gauss(per_month, per_month * 0.35))))
            if per_month >= 1 and n == 0:
                n = 1
            for _ in range(n):
                d = safe_date(y, m, self.rng.randint(1, 28))
                if start <= d <= end:
                    self.add(d, self.rng.uniform(lo, hi), category, self.rng.choice(counterparties))

    def between(self, a: dt.date, b: dt.date, category: str | None = None) -> list[Transaction]:
        return [t for t in self.txs if a <= t.date <= b and (category is None or t.category == category)]


# ----------------------------------------------------------------------------------
# Reusable life patterns
# ----------------------------------------------------------------------------------


def living_costs(b: TxBuilder, start: dt.date, end: dt.date, scale: float = 1.0,
                 subscription: tuple[str, float, float] | None = None,
                 increase_date: dt.date | None = None,
                 telecom: tuple[str, float, float] | None = None,
                 telecom_increase_date: dt.date | None = None) -> None:
    """Groceries, utilities, telecom, leisure, transport, other, one subscription. Every month."""
    rng = b.rng
    b.scatter(start, end, "groceries", GROCERS, 8 * scale, 15, 95)
    b.monthly(start, end, 8, rng.uniform(110, 190) * scale, "utilities", rng.choice(UTILITIES), jitter_amount=0.15)
    if telecom:
        t_name, t_old, t_new = telecom

        def telecom_amount(d: dt.date) -> float:
            return t_new if (telecom_increase_date and d >= telecom_increase_date) else t_old

        b.monthly(start, end, 12, telecom_amount, "telecom", t_name)
    else:
        b.monthly(start, end, 12, rng.uniform(35, 70), "telecom", rng.choice(TELECOM))
    b.scatter(start, end, "leisure", LEISURE, 4 * scale, 8, 70)
    b.scatter(start, end, "transport", TRANSPORT, 3 * scale, 5, 60)
    b.scatter(start, end, "other", OTHER, 1.2, 10, 80)
    if subscription:
        name, old, new = subscription

        def sub_amount(d: dt.date) -> float:
            return new if (increase_date and d >= increase_date) else old

        b.monthly(start, end, 14, sub_amount, "subscription", name)


def freelance_income(b: TxBuilder, start: dt.date, end: dt.date, clients: list[str],
                     lo: float = 800, hi: float = 3500, per_month: float = 2.0,
                     social_fund: str = "Xerius", social_amount: float = 1150.0,
                     invoice_end: dt.date | None = None) -> None:
    """Irregular invoices from several clients, quarterly VAT (~20th Jan/Apr/Jul/Oct) and social contributions.
    `invoice_end` stops the random invoices early (so a caller can add hand-picked ones) while VAT and social
    contributions still run until `end`."""
    rng = b.rng
    invoice_end = invoice_end or end
    for y, m in months_between(start, invoice_end):
        n = max(1, int(round(rng.gauss(per_month, 0.8))))
        for _ in range(n):
            d = safe_date(y, m, rng.randint(2, 28))
            if start <= d <= invoice_end:
                b.add(d, rng.uniform(lo, hi), "invoice_income", rng.choice(clients))
    # VAT: due around the 20th of the month after each quarter, based on the previous quarter's invoices
    for y in range(start.year, end.year + 2):
        for qm in (1, 4, 7, 10):
            due = safe_date(y, qm, rng.randint(18, 22))
            if not (start <= due <= end):
                continue
            q_end = safe_date(y, qm, 1) - dt.timedelta(days=1)
            q_start = add_months(safe_date(q_end.year, q_end.month, 1), -2)
            invoiced = sum(t.amount for t in b.between(q_start, q_end, "invoice_income"))
            if invoiced > 0:
                b.add(due, invoiced * 0.21 * rng.uniform(0.7, 0.9), "vat_payment", TAX_OFFICE)
    # Social contributions: quarterly, ~20th of Mar/Jun/Sep/Dec
    for y in range(start.year, end.year + 1):
        for sm in (3, 6, 9, 12):
            due = safe_date(y, sm, rng.randint(18, 22))
            if start <= due <= end:
                b.add(due, social_amount * rng.uniform(0.95, 1.05), "social_contribution", social_fund)


def student_life(b: TxBuilder, start: dt.date, end: dt.date, kot_rent: float, allowance: float,
                 tuition: float = 1092.10) -> None:
    rng = b.rng
    # allowance lands on the 1st, kot rent goes out on the 3rd, so the balance never dips negative on day 1
    b.monthly(start, end, 1, allowance, "allowance_from_parents", "Mama & Papa")
    b.monthly(start, end, 3, kot_rent, "rent", "Kot " + rng.choice(["Dhr. Vermeulen", "Mevr. Claes", "Studentenhuis Ter Beke"]))
    b.scatter(start, end, "student_income", ["Randstad Student", "Colruyt studentenjob", "Tempo-Team Students"], 1.3, 80, 350)
    # parents cover the tuition: a top-up on 2 October, the fee itself a few days later
    b.yearly(start, end, 10, 2, tuition, "allowance_from_parents", "Mama & Papa (inschrijving)")
    b.yearly(start, end, 10, rng.randint(4, 12), tuition, "tuition", rng.choice(["KU Leuven", "UGent", "UCLouvain", "UAntwerpen"]))


def family_life(b: TxBuilder, start: dt.date, end: dt.date, kids: int = 1, daycare: str | None = None,
                childcare: float = 540.0, baby_until: dt.date | None = None, school: bool = False) -> None:
    b.monthly(start, end, 8, 178.0 * kids, "child_benefit", CHILD_BENEFIT_PAYER)
    if daycare:
        b.monthly(start, end, 1, childcare, "childcare", daycare, jitter_amount=0.08)
    if baby_until:
        b.scatter(start, min(end, baby_until), "baby", BABY, 3.5, 20, 140)
    if school:
        b.scatter(start, end, "school", SCHOOL, 0.5, 25, 180)


def retiree_life(b: TxBuilder, start: dt.date, end: dt.date, pension: float) -> None:
    b.monthly(start, end, 3, pension, "pension", PENSION_PAYER)
    b.scatter(start, end, "healthcare", HEALTHCARE, 2.8, 12, 95)


# ----------------------------------------------------------------------------------
# Balance calibration
# ----------------------------------------------------------------------------------

Band = tuple[float, float, float]  # (lo, hi, sweep_target)


def calibrate_balance(b: TxBuilder, start_balance: float, band_for,
                      overrides: dict[tuple[int, int], float] | None = None,
                      excess: tuple[str, str] | list[tuple[str, str]] = ("savings_transfer", "KBC Spaarrekening"),
                      until: dt.date | None = None, min_factor: float = 0.25) -> float:
    """Walk the running balance forward month by month and keep it inside a band.

    band_for(date) -> (lo, hi, target). At each month end:
      - above `hi` (or above an explicit per-month override target): sweep the excess out as `excess`
        (category, counterparty), e.g. a savings transfer, on the last day of the month;
      - below `lo`: scale down that month's variable spending (never below `min_factor`); no income is injected.
    Returns the running balance at `until` (default: the builder's end date), i.e. balance_today for the walk-back.
    """
    overrides = overrides or {}
    until = until or b.end
    excess_options = [excess] if isinstance(excess, tuple) else list(excess)
    bal = start_balance
    for y, m in months_between(b.start, until):
        month_end = min(until, safe_date(y, m, 31))
        month_txs = [t for t in b.txs if t.date.year == y and t.date.month == m and t.date <= until]
        lo, hi, target = band_for(month_end)
        end = bal + sum(t.amount for t in month_txs)
        if end < lo:
            var = [t for t in month_txs if t.category in VARIABLE_CATEGORIES and t.amount < 0]
            var_total = -sum(t.amount for t in var)
            if var_total > 0:
                factor = max(min_factor, 1 - (lo - end) / var_total)
                for t in var:
                    t.amount = round(t.amount * factor, 2)
                end = bal + sum(t.amount for t in month_txs)
        sweep_to = overrides.get((y, m))
        if sweep_to is not None and end > sweep_to:
            amount = end - sweep_to
        elif end > hi:
            amount = end - target
        else:
            amount = 0.0
        if amount >= 20:
            cat, cp = b.rng.choice(excess_options)
            b.add(month_end, amount, cat, cp)
            end -= amount
        bal = end
    return round(bal, 2)


def fixed_band(lo: float, hi: float, target: float):
    return lambda d: (lo, hi, target)


def era_bands(eras: list[tuple[dt.date, Band]]):
    """eras = [(start_date, (lo, hi, target)), ...] in date order; each band applies from its start date on."""
    def band_for(d: dt.date) -> Band:
        current = eras[0][1]
        for start, band in eras:
            if d >= start:
                current = band
        return current
    return band_for


# ----------------------------------------------------------------------------------
# Regular customers
# ----------------------------------------------------------------------------------

PERSONA_WEIGHTS = [("young_professional", 0.30), ("student", 0.12), ("young_family", 0.20),
                   ("freelancer", 0.18), ("retiree", 0.20)]


def pick_weighted(rng: random.Random, options: list[tuple[str, float]]) -> str:
    r = rng.random() * sum(w for _, w in options)
    for name, w in options:
        r -= w
        if r <= 0:
            return name
    return options[-1][0]


def make_regular(cid: int, seed: int) -> tuple[Customer, list[Transaction], float]:
    rng = random.Random(seed * 100003 + cid)
    end = TODAY
    start = TODAY - dt.timedelta(days=REGULAR_HISTORY_DAYS)

    nl = rng.random() < 0.65
    first = rng.choice(NL_FIRST if nl else FR_FIRST)
    last = rng.choice(NL_LAST if nl else FR_LAST)
    city = rng.choice(NL_CITIES if nl else FR_CITIES)

    primary = pick_weighted(rng, PERSONA_WEIGHTS)
    personas = [primary]
    if primary in ("young_professional", "freelancer") and rng.random() < 0.25:
        personas.append("young_family")
    if primary == "young_family" and rng.random() < 0.3:
        personas.append("freelancer")

    age = {"student": rng.randint(18, 25), "young_professional": rng.randint(24, 35),
           "young_family": rng.randint(27, 42), "freelancer": rng.randint(25, 55),
           "retiree": rng.randint(65, 85)}[primary]
    if "young_family" in personas and primary != "young_family":
        age = max(age, rng.randint(27, 38))
    birth_year = TODAY.year - age

    events: list[dict] = []
    event_types: list[str] = []
    candidates = [("insurance_renewal", 0.25), ("price_increase", 0.20), ("duplicate_charge", 0.15),
                  ("cashflow_squeeze", 0.12), ("idle_cash", 0.12)]
    for name, p in candidates:
        if len(event_types) >= 2:
            break
        if name in ("idle_cash", "insurance_renewal") and primary == "student":
            continue
        if name == "idle_cash" and "cashflow_squeeze" in event_types:
            continue
        if rng.random() < p:
            event_types.append(name)

    # products
    products = ["current"]
    if "idle_cash" not in event_types and primary != "student" and rng.random() < 0.55:
        products.append("savings")
    if "insurance_renewal" not in event_types and primary != "student" and rng.random() < 0.3:
        products.append("car_insurance")
    if primary != "student" and rng.random() < 0.4:
        products.append("home_insurance")
    if primary not in ("student",) and rng.random() < 0.15:
        products.append("investment_plan")

    b = TxBuilder(cid, rng, start, end)
    scale = 1.0
    subscription = rng.choice(SUBSCRIPTIONS) if rng.random() < 0.8 else None
    increase_date = None
    if "price_increase" in event_types:
        subscription = subscription or SUBSCRIPTIONS[0]
        increase_date = TODAY - dt.timedelta(days=rng.randint(5, 55))
        events.append({"type": "price_increase", "date": increase_date.isoformat(),
                       "counterparty": subscription[0], "from": subscription[1], "to": subscription[2]})

    # --- income / persona patterns
    pre_salary_living: dt.date | None = None
    if primary == "student":
        scale = 0.35
        student_life(b, start, end, kot_rent=rng.uniform(300, 420), allowance=rng.uniform(400, 600))
    if primary == "retiree":
        pension = rng.uniform(1400, 2200)
        scale = 0.9
        retiree_life(b, start, end, pension=pension)
        if rng.random() < 0.4:
            b.monthly(start, end, 1, rng.uniform(450, min(700, pension * 0.4)), "rent",
                      "Seniorie " + rng.choice(["Ter Linde", "Park Vaartland"]))
    if primary == "young_professional" or (primary == "young_family" and "freelancer" not in personas):
        # a family on one salary in the data stands for the household: give it a higher net salary
        salary = rng.uniform(2000, 3500) if primary == "young_professional" else rng.uniform(2700, 3900)
        employer = rng.choice(EMPLOYERS)
        salary_start = start
        if primary == "young_professional" and rng.random() < 0.2:
            # first job during the history window: student-ish before, salary after
            salary_start = TODAY - dt.timedelta(days=rng.randint(60, 300))
            student_life(b, start, salary_start - dt.timedelta(days=1), kot_rent=rng.uniform(300, 420),
                         allowance=rng.uniform(400, 600))
            events.append({"type": "first_salary", "date": salary_start.isoformat(), "employer": employer})
            pre_salary_living = salary_start
        b.monthly(salary_start, end, 27, salary, "salary", employer, jitter_amount=0.02)
    if primary == "freelancer" or "freelancer" in personas:
        clients = rng.sample(CLIENTS, rng.randint(3, 6))
        freelance_income(b, start, end, clients, per_month=rng.uniform(1.5, 2.5),
                         social_fund=rng.choice(SOCIAL_FUNDS), social_amount=rng.uniform(850, 1600))
    if "young_family" in personas:
        kids = 1 if rng.random() < 0.6 else 2
        daycare = rng.choice(DAYCARES)
        if rng.random() < 0.3:
            birth = TODAY - dt.timedelta(days=rng.randint(60, 330))
            family_life(b, add_months(birth, 1), end, kids=kids, daycare=daycare,
                        childcare=rng.uniform(400, 700), baby_until=add_months(birth, 8))
            b.scatter(birth, add_months(birth, 1), "baby", BABY, 5, 30, 200)
            events.append({"type": "baby", "date": birth.isoformat()})
        else:
            family_life(b, start, end, kids=kids, daycare=daycare, childcare=rng.uniform(400, 700),
                        school=kids == 2)
        if rng.random() < 0.5:
            b.yearly(start, end, rng.randint(1, 12), rng.randint(1, 28), rng.uniform(80, 120),
                     "insurance_family", KBC_INSURANCE)

    # --- housing
    if primary == "young_professional":
        if rng.random() < 0.6:
            b.monthly(start, end, 1, rng.uniform(650, 1000), "rent", "Immo " + rng.choice(NL_LAST + FR_LAST))
        else:
            products.append("mortgage")
    elif primary == "young_family":
        if rng.random() < 0.75:
            products.append("mortgage")
        else:
            b.monthly(start, end, 1, rng.uniform(800, 1100), "rent", "Immo " + rng.choice(NL_LAST + FR_LAST))
    elif primary == "freelancer":
        if rng.random() < 0.5:
            products.append("mortgage")
        else:
            b.monthly(start, end, 1, rng.uniform(650, 1000), "rent", "Immo " + rng.choice(NL_LAST + FR_LAST))
    if "mortgage" in products:
        b.monthly(start, end, 5, rng.uniform(850, 1400), "mortgage", "KBC Woningkrediet")

    # --- insurance
    if "car_insurance" in products:
        b.yearly(start, end, rng.randint(1, 12), rng.randint(1, 28), rng.uniform(450, 900), "insurance_car", KBC_INSURANCE)
    if "home_insurance" in products:
        b.yearly(start, end, rng.randint(1, 12), rng.randint(1, 28), rng.uniform(250, 450), "insurance_home", KBC_INSURANCE)
    if "insurance_renewal" in event_types:
        insurer = rng.choice(EXTERNAL_INSURERS)
        premium = round(rng.uniform(450, 900), 2)
        # a good share of renewals fall in the next 3–14 days so the demo has "soon" cards
        if rng.random() < 0.3:
            days_to_renewal = rng.randint(3, 14)
        else:
            days_to_renewal = rng.randint(15, 335)
        last_paid = TODAY - dt.timedelta(days=365 - days_to_renewal)
        b.add(last_paid, premium, "insurance_car", insurer)
        b.add(last_paid - dt.timedelta(days=365), premium * 0.96, "insurance_car", insurer)
        events.append({"type": "insurance_renewal", "date": (last_paid + dt.timedelta(days=365)).isoformat(),
                       "counterparty": insurer, "amount": premium})

    # --- savings habit
    if "savings" in products and rng.random() < 0.7:
        b.monthly(start, end, 2, rng.choice([50, 75, 100, 150, 200]), "savings_transfer", "KBC Spaarrekening")

    # --- everyday living (a first-salary customer lives like a student until the salary starts)
    living_from = start
    if primary == "young_professional" and pre_salary_living is not None:
        living_costs(b, start, pre_salary_living - dt.timedelta(days=1), scale=0.35, subscription=subscription)
        living_from = pre_salary_living
    living_costs(b, living_from, end, scale=scale, subscription=subscription, increase_date=increase_date)

    # --- anomalies
    if "duplicate_charge" in event_types:
        recent = b.between(TODAY - dt.timedelta(days=13), TODAY - dt.timedelta(days=1), "groceries")
        if not recent:
            d = TODAY - dt.timedelta(days=rng.randint(2, 10))
            b.add(d, rng.uniform(30, 90), "groceries", rng.choice(GROCERS))
            recent = b.between(d, d, "groceries")
        t = rng.choice(recent)
        dup_date = t.date + dt.timedelta(days=rng.choice([0, 1]))
        b.add(dup_date, abs(t.amount), t.category, t.counterparty)
        events.append({"type": "duplicate_charge", "date": dup_date.isoformat(), "counterparty": t.counterparty,
                       "amount": abs(t.amount)})
    if "cashflow_squeeze" in event_types:
        since = TODAY - dt.timedelta(days=30)
        for t in b.txs:
            if t.date >= since and t.category in VARIABLE_CATEGORIES:
                t.amount = round(t.amount * 1.8, 2)
        for _ in range(3):
            b.add(TODAY - dt.timedelta(days=rng.randint(1, 29)), rng.uniform(80, 250), "other",
                  rng.choice(["Brico", "Garage Vermeersch", "Tandarts De Wilde", "Zalando"]))
        events.append({"type": "cashflow_squeeze", "date": since.isoformat()})

    # --- balance path: keep the running balance in a sane band so time travel never shows absurd balances
    spend_90 = -sum(t.amount for t in b.between(TODAY - dt.timedelta(days=90), TODAY) if t.amount < 0)
    income_90 = sum(t.amount for t in b.between(TODAY - dt.timedelta(days=90), TODAY) if t.amount > 0)
    monthly_spend = max(300.0, spend_90 / 3)
    monthly_income = max(300.0, income_90 / 3)
    if "savings" in products:
        sweep = ("savings_transfer", "KBC Spaarrekening")
    else:
        sweep = [("leisure", "Neckermann Reizen"), ("other", "Brico"), ("furniture", "IKEA"), ("leisure", "Bol.com")]
    if primary == "student":
        band, start_bal = fixed_band(120, 900, 350), rng.uniform(150, 500)
    elif "idle_cash" in event_types:
        # the engine's measure: balance > 6 × average monthly TOTAL outflow (90 days, savings transfers excluded)
        window = b.between(TODAY - dt.timedelta(days=90), TODAY)
        outflow = max(300.0, -sum(t.amount for t in window if t.amount < 0 and t.category != "savings_transfer") / 3)
        net_90 = sum(t.amount for t in window)
        # the band lets the pre-window balance sit 10 % under target, so size the target for that floor
        idle = max(outflow * 8.5, outflow * 6 + 2500) / 0.9 * rng.uniform(1.0, 1.25)
        # calibrate only up to 91 days ago (so no sweep spending lands in the engine's window), then run free;
        # aim the pre-window balance so that today's balance ends at `idle` after the last 90 days of flows
        at_until = idle - net_90
        band, start_bal = fixed_band(at_until * 0.9, at_until * 1.1, at_until), at_until
        sweep = [("leisure", "Neckermann Reizen"), ("other", "Brico")]
    elif "cashflow_squeeze" in event_types:
        band = fixed_band(monthly_spend * 0.5, monthly_spend * 1.8, monthly_spend * 1.2)
        start_bal = monthly_spend * rng.uniform(0.8, 1.4)
    elif pre_salary_living is not None:
        band = era_bands([(start, (150, 900, 350)),
                          (pre_salary_living, (monthly_income * 0.3, monthly_income * 2.0, monthly_income * 1.2))])
        start_bal = rng.uniform(150, 500)
    else:
        band = fixed_band(monthly_income * 0.3, monthly_income * 2.0, monthly_income * 1.2)
        start_bal = monthly_income * rng.uniform(0.6, 1.5)
    # a cash-flow squeeze must stay visible: calibrate up to a month ago, then let the last 30 days run free
    until = TODAY
    if "cashflow_squeeze" in event_types:
        until = TODAY - dt.timedelta(days=31)
    elif "idle_cash" in event_types:
        until = TODAY - dt.timedelta(days=91)
    balance = calibrate_balance(b, start_bal, band, excess=sweep, until=until)
    if until < TODAY:
        balance = round(balance + sum(t.amount for t in b.between(until + dt.timedelta(days=1), TODAY)), 2)
    if "idle_cash" in event_types:
        # a customer whose fixed costs exceed income cannot be lifted by the band; a term deposit that matured
        # four months ago and was never reinvested is exactly the idle-cash story, so add that inflow
        shortfall = round(idle - balance, 2)
        if shortfall > 0:
            b.add_signed(TODAY - dt.timedelta(days=120), shortfall, "savings_transfer", "KBC Termijnrekening (vervaldag)")
            balance = round(balance + shortfall, 2)
        events.append({"type": "idle_cash", "date": TODAY.isoformat(), "balance": round(balance, 2)})

    customer = Customer(
        id=cid, first_name=first, last_name=last, birth_year=birth_year, city=city,
        language="nl" if nl else "fr", products=products,
        consent_personalization=rng.random() < 0.9,
        ground_truth={"personas": personas, "events": events},
    )
    return customer, b.txs, round(balance, 2)


# ----------------------------------------------------------------------------------
# Build
# ----------------------------------------------------------------------------------


def _remove_db(path: str) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        p = path + suffix
        if os.path.exists(p):
            os.remove(p)


def build(db_path: str, n: int = 1000, seed: int = 42, verbose: bool = True) -> dict:
    from .demo_customers import demo_customers  # local import: demo_customers uses helpers from this module

    _remove_db(db_path)
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = db.connect(db_path)
    db.init_schema(conn)

    pw_hash = hash_password(DEMO_PASSWORD)
    next_tx_id = 1
    scenario_counts: Counter[str] = Counter()
    n_tx = 0

    def store(customer: Customer, txs: list[Transaction], balance: float, username: str | None) -> None:
        nonlocal next_tx_id, n_tx
        txs = sorted(txs, key=lambda t: (t.date, t.counterparty))
        for t in txs:
            t.id = next_tx_id
            next_tx_id += 1
        db.insert_customer(conn, customer, balance)
        db.insert_transactions(conn, txs)
        if username:
            db.insert_user(conn, username, pw_hash, "customer", customer.id)
        n_tx += len(txs)
        for p in customer.ground_truth.get("personas", []):
            scenario_counts[p] += 1
        for e in customer.ground_truth.get("events", []):
            scenario_counts[e["type"]] += 1

    with conn:
        for cid in range(1, n + 1):
            c, txs, bal = make_regular(cid, seed)
            store(c, txs, bal, f"c{cid}")
        for username, c, txs, bal in demo_customers():
            store(c, txs, bal, username)
        db.insert_user(conn, "advisor", pw_hash, "advisor", None)
    conn.close()

    summary = {"customers": n + 3, "transactions": n_tx, "scenarios": dict(sorted(scenario_counts.items()))}
    if verbose:
        print(f"Built {db_path}")
        print(f"  customers:    {summary['customers']} ({n} regular + 3 demo)")
        print(f"  transactions: {n_tx}")
        print("  scenarios:")
        for k, v in summary["scenarios"].items():
            print(f"    {k:20s} {v}")
        print(f"  logins: lotte / sara / jan / c1..c{n} / advisor  (password: {DEMO_PASSWORD!r})")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate the synthetic KBC database")
    ap.add_argument("--n", type=int, default=1000, help="number of regular customers")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--db", default=db.DB_PATH)
    args = ap.parse_args()
    build(args.db, n=args.n, seed=args.seed)


if __name__ == "__main__":
    main()
