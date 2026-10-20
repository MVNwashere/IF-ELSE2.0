"""Synthetic customers + transactions for the KBC Takes Care proof of concept.

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

TODAY = dt.date(2026, 10, 20)
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


# ----------------------------------------------------------------------------------
# Goal scenarios (ground truth "goal:<playbook_id>") for the intent evaluation
# ----------------------------------------------------------------------------------
# A separate RNG decides and shapes them, so customers without a goal scenario are generated exactly as before.

GARAGE_NAMES = ["Garage Vermeersch", "Garage De Smet", "Autoservice Claes", "Garage Lambert", "Carrosserie Mertens"]
UNIVERSITIES = ["KU Leuven", "UGent", "UAntwerpen", "VUB", "UCLouvain", "ULiège", "Hogeschool PXL", "Odisee"]
NOTARIES = ["Notaris Van den Broeck", "Notaris Wouters", "Notaire Dubois", "Notaris Claes", "Notaire Lemaire"]
SUBCONTRACTOR_NAMES = ["Onderaanneming Maes BV", "Onderaanneming Pixelwerk", "Freelance Studio Noord", "Onderaannemer Jacobs"]


def pick_goal_scenario(g: random.Random, primary: str, personas: list[str], products: list[str], age: int,
                       first_job: bool, event_types: list[str]) -> str | None:
    """At most one goal scenario per customer, so each playbook is detectable for a few % of the portfolio."""
    if primary == "student" or {"idle_cash", "cashflow_squeeze"} & set(event_types):
        return None
    r, r2, r3 = g.random(), g.random(), g.random()
    if primary == "young_professional" and not first_job and "young_family" not in personas:
        if r < 0.11:
            return "go_freelance"
        if r < 0.22:
            return "job_change"
    if primary == "freelancer" and "young_family" not in personas:
        if r < 0.13:
            return "first_employee"
        if r < 0.29:
            return "retire_well"
        if r < 0.42:
            return "study_start"
    if "mortgage" in products and r2 < 0.09:
        return "energy_upgrade"
    if age < 70 and r3 < 0.04:
        return "mobility"
    if age >= 30 and 0.04 <= r3 < 0.065:
        return "inheritance"
    return None


def inject_goal_before_balance(g: random.Random, b: TxBuilder, goal: str, events: list[dict],
                               personas: list[str]) -> None:
    """Scenarios that reshape income: applied before the balance calibration."""
    if goal == "go_freelance":
        stop = TODAY - dt.timedelta(days=g.randint(45, 200))
        b.txs = [t for t in b.txs if not (t.category == "salary" and t.date > stop)]
        first = min(TODAY - dt.timedelta(days=3), stop + dt.timedelta(days=g.randint(12, 40)))
        b.add(stop + dt.timedelta(days=2), 105.50, "other", "Ondernemingsloket Xerius (inschrijving KBO)")
        clients = g.sample(CLIENTS, g.randint(1, 3))
        d = first
        while d <= TODAY:
            b.add(d, g.uniform(2500, 6000), "invoice_income", g.choice(clients))
            d += dt.timedelta(days=g.randint(26, 34))
        if "freelancer" not in personas:
            personas.append("freelancer")
        events.append({"type": "goal:go_freelance", "date": first.isoformat()})
    elif goal == "job_change":
        sal = sorted((t for t in b.txs if t.category == "salary"), key=lambda t: t.date)
        if not sal:
            return
        stop = TODAY - dt.timedelta(days=g.randint(60, 160))
        template = sal[-1]
        b.txs = [t for t in b.txs if not (t.category == "salary" and t.date > stop)]
        if g.random() < 0.5:
            new_employer = g.choice([e for e in EMPLOYERS if e != template.counterparty])
            start = stop + dt.timedelta(days=g.randint(20, 45))
            b.monthly(start, TODAY, 27, abs(template.amount) * g.uniform(1.0, 1.15), "salary", new_employer)
            first_new = min((t.date for t in b.txs if t.counterparty == new_employer), default=start)
            events.append({"type": "goal:job_change", "date": first_new.isoformat(), "kind": "new_employer"})
        else:
            # Belgian severance pay (opzegvergoeding) with the last pay slip, then unemployment benefit
            b.add(stop, abs(template.amount) * g.uniform(2, 3), "salary", template.counterparty + " (opzegvergoeding)")
            b.monthly(stop + dt.timedelta(days=35), TODAY, 15, g.uniform(1200, 1700), "benefit",
                      "HVW (werkloosheidsuitkering)")
            events.append({"type": "goal:job_change", "date": (stop + dt.timedelta(days=40)).isoformat(),
                           "kind": "job_loss"})
    elif goal == "first_employee":
        since = TODAY - dt.timedelta(days=120)
        for t in b.txs:
            if t.category == "invoice_income" and t.date > since:
                t.amount = round(t.amount * 2.4, 2)
        for _ in range(g.randint(3, 5)):
            b.add(TODAY - dt.timedelta(days=g.randint(10, 110)), g.uniform(800, 2200), "other",
                  g.choice(SUBCONTRACTOR_NAMES))
        events.append({"type": "goal:first_employee", "date": (TODAY - dt.timedelta(days=100)).isoformat()})


def inject_goal_after_balance(g: random.Random, b: TxBuilder, goal: str, events: list[dict], products: list[str],
                              age: int) -> float:
    """One-off scenarios added after calibration. Returns the net amount added (to shift balance_today)."""
    before = len(b.txs)
    if goal == "retire_well":
        window = b.between(TODAY - dt.timedelta(days=90), TODAY)
        spend = max(500.0, -sum(t.amount for t in window if t.amount < 0 and t.category != "savings_transfer") / 3)
        d = TODAY - dt.timedelta(days=g.randint(100, 200))
        b.add_signed(d, round(spend * g.uniform(11, 14) + 5000, 2), "savings_transfer", "KBC Termijnrekening (vervaldag)")
        events.append({"type": "goal:retire_well", "date": d.isoformat()})
        if "savings" not in products:
            events.append({"type": "idle_cash", "date": TODAY.isoformat()})
    elif goal == "energy_upgrade":
        util = sorted(-t.amount for t in b.txs if t.category == "utilities" and t.amount < 0) or [150.0]
        d = TODAY - dt.timedelta(days=g.randint(15, 120))
        b.add(d, max(util[len(util) // 2] * g.uniform(3.5, 5), 480), "utilities",
              g.choice(UTILITIES) + " (jaarafrekening)")
        events.append({"type": "goal:energy_upgrade", "date": d.isoformat()})
    elif goal == "mobility":
        garage = g.choice(GARAGE_NAMES)
        dates = [TODAY - dt.timedelta(days=g.randint(220, 320)), TODAY - dt.timedelta(days=g.randint(110, 190)),
                 TODAY - dt.timedelta(days=g.randint(32, 80))]
        for d, (lo, hi) in zip(dates, [(350, 600), (600, 1000), (950, 1700)]):
            b.add(d, g.uniform(lo, hi), "transport", garage)
        events.append({"type": "goal:mobility", "date": dates[-1].isoformat()})
    elif goal == "inheritance":
        d = TODAY - dt.timedelta(days=g.randint(10, 150))
        b.add_signed(d, round(g.uniform(25000, 150000), -2), "other", g.choice(NOTARIES) + " (nalatenschap)")
        events.append({"type": "goal:inheritance", "date": d.isoformat()})
    elif goal == "study_start":
        d = TODAY - dt.timedelta(days=g.randint(10, 100))
        b.add(d, g.choice([1092.10, 1153.80, 979.60]), "tuition", g.choice(UNIVERSITIES) + " (inschrijvingsgeld)")
        events.append({"type": "goal:study_start", "date": d.isoformat()})
    return round(sum(t.amount for t in b.txs[before:]), 2)


# ----------------------------------------------------------------------------------
# More goal scenarios and near misses (look-alikes that must not trigger a goal)
# ----------------------------------------------------------------------------------
# The new goals, and the four goals that only came from base patterns, get injected truth ("goal:<id>"). Near misses
# look like a goal but aren't one ("near_miss:<id>"), so the evaluation also counts false alarms. They use the same
# goal RNG, drawn only for customers without a first-draw goal, so earlier scenarios are generated exactly as before.

ENTERPRISE_COUNTERS = ["Xerius", "Liantis", "Acerta", "UCM"]
SIDE_JOB_FUNDS = ["Xerius (bijberoep)", "Liantis (bijberoep)"]
SIDE_JOB_CLIENTS = ["Bakkerij Claes", "Fotostudio Lens", "Vzw Sportkring", "Kapsalon Nova", "Webshop Bloem",
                    "Café De Hoek"]
FOREIGN_CLIENTS = ["Northwind GmbH (DE)", "Studio Lumière SARL (FR)", "Brightline Ltd (UK)", "Kanaal BV (NL)",
                   "Atlas Inc (US)"]
CARE_HOMES = ["WZC Hof ter Linde (woonzorgcentrum)", "WZC De Linde (woonzorgcentrum)"]
HOME_CARE = ["Familiehulp (thuiszorg)", "i-mens (thuisverpleging)"]
REMOVALS = ["Verhuisfirma De Kat", "Verhuizingen Peeters"]
AUDITORS = ["Bedrijfsrevisor Verhaegen (waardering)", "Bedrijfsrevisor Dumont (waardering)"]
TRANSFER_LAWYERS = ["Advocatenkantoor Lydian (overdracht)", "Advocatenkantoor Claeys (overdracht)"]
BOOKKEEPERS = ["Boekhouder Vandenberghe", "Boekhouder Fidu Plus"]
BNPL = ["Klarna", "Alma"]
BAILIFFS = ["Gerechtsdeurwaarder Maes", "Gerechtsdeurwaarder Leclercq"]
AUCTIONS = ["BelOrta (veiling)", "Veiling Hoogstraten"]
FARM_SUPPLIERS = ["Aveve", "Agrofront"]
CHARGERS = ["Allego", "Shell Recharge", "Ionity", "Fastned"]
WEDDING_VENUES = ["Trouwzaal Kasteel Ter Walle", "Trouwzaal Hof van Oost"]
JEWELLERS = ["Juwelier Slaets", "Juwelier Desmet"]
FAMILY_LAWYERS = ["Advocaat Van Damme (echtscheiding)", "Bemiddelaar Hermans (scheiding)"]
TRAVEL_BOOKINGS = ["Brussels Airlines", "TUI", "Sunweb", "Ryanair"]
PROPERTY_ALERTS = ["Immoweb zoekalert", "Zimmo Premium zoekalert"]
INSPECTORS = ["Bouwkundig Expertisebureau Vandamme", "Bouwkundig Expertisebureau Mertens"]
UNKNOWN_PAYEES = ["Hr. J. Vandamme", "Safe Account Services", "M. Dubois (veilige rekening)", "Bank Support Desk"]
STREETS = ["Kerkstraat", "Stationsstraat", "Molenstraat", "Rue de la Station", "Dorpsstraat"]

# near-miss pattern → the goals it must NOT be mistaken for
NEAR_MISS_LABELS: dict[str, tuple[str, ...]] = {
    "resale_income": ("side_job",), "webshop_refund": ("go_international",), "hospital_bill": ("care_parent",),
    "rent_indexation": ("move_house",), "bookkeeper_only": ("sell_business",), "single_bnpl": ("back_on_track",),
    "garden_purchase": ("farm_growth",), "holiday_charge": ("ev_switch",), "saving_for_house": ("first_investment",),
    "december_jewellery": ("together",), "traffic_lawyer": ("separation",),
    "salary_pause": ("go_freelance", "job_change"), "one_invoice": ("go_freelance", "side_job"),
    "property_sale": ("inheritance",), "landlord_search": ("buy_home",), "accident_repair": ("mobility",),
    "refunded_flight": ("travel",),
}
NEAR_MISS_SHARE = 0.17
NEAR_MISS_WEIGHT = {"salary_pause": 4.0, "one_invoice": 3.0, "webshop_refund": 6.0, "bookkeeper_only": 5.0,
                    "landlord_search": 2.0, "saving_for_house": 3.0, "rent_indexation": 1.5, "accident_repair": 1.5}
NEAR_MISS_BEFORE = {"rent_indexation", "bookkeeper_only", "saving_for_house", "salary_pause", "one_invoice",
                    "landlord_search"}


def _person(g: random.Random) -> str:
    return f"{g.choice(NL_FIRST + FR_FIRST)} {g.choice(NL_LAST + FR_LAST)}"


def _monthly_signed(b: TxBuilder, start: dt.date, end: dt.date, day: int, amount: float, category: str,
                    counterparty: str) -> None:
    """A monthly flow with an explicit sign (e.g. a partner's contribution booked as `other` income)."""
    for y, m in months_between(start, end):
        d = safe_date(y, m, day)
        if start <= d <= end:
            b.add_signed(d, amount, category, counterparty)


def _days_ago(g: random.Random, lo: int, hi: int) -> dt.date:
    return TODAY - dt.timedelta(days=g.randint(lo, hi))


def _rents(b: TxBuilder) -> list[Transaction]:
    return sorted((t for t in b.txs if t.category == "rent" and t.counterparty.startswith("Immo ")),
                  key=lambda t: t.date)


def _salaried(b: TxBuilder) -> bool:
    return any(t.category == "salary" and t.date > TODAY - dt.timedelta(days=60) for t in b.txs)


def _label(events: list[dict], goal: str, d: dt.date, **extra) -> None:
    events.append({"type": f"goal:{goal}", "date": d.isoformat(), **extra})


def pick_more_goal(g: random.Random, b: TxBuilder, primary: str, personas: list[str], products: list[str], age: int,
                   first_job: bool, event_types: list[str]) -> str | None:
    """A second draw for customers without a first-draw goal: the remaining goals and the base-pattern goals."""
    if primary == "student" or {"idle_cash", "cashflow_squeeze"} & set(event_types):
        return None
    renter, salaried = len(_rents(b)) >= 3, _salaried(b)
    family = "young_family" in personas
    options: list[tuple[str, float]] = []
    if primary == "retiree":
        options += [("peace_of_mind", 0.11), ("travel", 0.05)]
    else:
        if salaried and "freelancer" not in personas:
            options.append(("side_job", 0.08))
        if primary == "young_professional" and not first_job and age <= 38:
            options.append(("first_investment", 0.11))
        if primary == "freelancer":
            options += [("go_international", 0.18), ("farm_growth", 0.14), ("sell_business", 0.17)]
        if renter and salaried and not family:
            options.append(("buy_home", 0.20))
        if renter:
            options.append(("move_house", 0.12))
        if not family and age <= 40:
            options += [("together", 0.14), ("new_baby", 0.12)]
        if (family or "mortgage" in products) and age >= 28:
            options.append(("separation", 0.07))
        options += [("care_parent", 0.04), ("ev_switch", 0.05), ("travel", 0.03), ("back_on_track", 0.04)]
    r, acc = g.random(), 0.0
    for goal, p in options:
        acc += p
        if r < acc:
            return goal
    return None


def pick_near_miss(g: random.Random, b: TxBuilder, primary: str, personas: list[str], products: list[str], age: int,
                   first_job: bool) -> str | None:
    """About 17% of the customers without any goal get one look-alike pattern."""
    if g.random() >= NEAR_MISS_SHARE:
        return None
    student, retiree = primary == "student", primary == "retiree"
    salaried, renter = _salaried(b), len(_rents(b)) >= 3
    early_salary = any(t.category == "salary" and t.date < TODAY - dt.timedelta(days=330) for t in b.txs)
    eligible = {
        "resale_income": True, "single_bnpl": True, "refunded_flight": True, "holiday_charge": age < 70,
        "webshop_refund": "freelancer" in personas, "hospital_bill": not student and not retiree,
        "rent_indexation": renter, "bookkeeper_only": primary == "freelancer",
        "garden_purchase": "freelancer" not in personas,
        "saving_for_house": primary == "young_professional" and renter and salaried and not first_job and age <= 38,
        "december_jewellery": not retiree, "traffic_lawyer": not student,
        "salary_pause": early_salary and "freelancer" not in personas,
        "one_invoice": salaried and "freelancer" not in personas,
        "property_sale": not student, "landlord_search": "mortgage" in products,
        "accident_repair": not student and age < 70,
    }
    options = [k for k, ok in eligible.items() if ok]
    if not options:
        return None
    # the patterns with a narrow audience get more weight, so every near miss shows up a few times
    weights = [NEAR_MISS_WEIGHT.get(k, 1.0) for k in options]
    return g.choices(options, weights)[0]


def inject_more_goal(g: random.Random, b: TxBuilder, goal: str, events: list[dict], products: list[str],
                     city: str, phase: str) -> float:
    """Inject a pick_more_goal scenario. Phase 'before' reshapes flows ahead of the balance calibration; 'after' adds
    one-off payments and returns their net amount (to shift balance_today)."""
    before = len(b.txs)
    if phase == "before":
        if goal == "side_job":
            start = _days_ago(g, 60, 170)
            b.add(start - dt.timedelta(days=g.randint(3, 15)), 105.50, "other",
                  f"Ondernemingsloket {g.choice(ENTERPRISE_COUNTERS)} (inschrijving KBO)")
            clients, d = g.sample(SIDE_JOB_CLIENTS, g.randint(1, 2)), start
            while d <= TODAY:
                b.add(d, g.uniform(300, 1500), "invoice_income", g.choice(clients))
                d += dt.timedelta(days=g.randint(20, 45))
            fund = g.choice(SIDE_JOB_FUNDS)
            for y, m in months_between(start, TODAY):
                if m in (3, 6, 9, 12) and start <= safe_date(y, m, 20) <= TODAY:
                    b.add(safe_date(y, m, 20), g.uniform(85, 120), "social_contribution", fund)
            _label(events, goal, start)
        elif goal == "go_international":
            first = _days_ago(g, 50, 200)
            clients, d = g.sample(FOREIGN_CLIENTS, g.randint(1, 2)), first
            while d <= TODAY:   # intra-EU B2B: reverse charge, so no Belgian VAT on these
                b.add(d, g.uniform(2500, 7000), "invoice_income", g.choice(clients))
                d += dt.timedelta(days=g.randint(25, 50))
            _label(events, goal, first)
        elif goal == "care_parent":
            start = _days_ago(g, 45, 200)
            if g.random() < 0.6:
                b.monthly(start, TODAY, g.randint(3, 10), g.uniform(450, 1100), "healthcare", g.choice(CARE_HOMES))
            else:
                cp, amount = g.choice(HOME_CARE), g.uniform(120, 300)
                b.monthly(start, TODAY, 5, amount, "healthcare", cp)
                b.monthly(start, TODAY, 20, amount, "healthcare", cp)
            _label(events, goal, start)
        elif goal == "move_house":
            old = _rents(b)[-1]
            move = _days_ago(g, 20, 120)
            month_start = safe_date(move.year, move.month, 1)
            b.txs = [t for t in b.txs if not (t.counterparty == old.counterparty and t.category == "rent"
                                              and t.date > month_start)]
            new_cp = "Immo " + g.choice([n for n in NL_LAST + FR_LAST if "Immo " + n != old.counterparty])
            rent = -old.amount * g.uniform(0.9, 1.25)
            b.add(move - dt.timedelta(days=20), rent * g.choice([2, 3]), "rent", f"Huurwaarborg {new_cp}")
            b.monthly(move, TODAY, move.day, rent, "rent", new_cp)
            b.add(move, g.uniform(400, 1200), "other", g.choice(REMOVALS))
            b.add(move + dt.timedelta(days=5), g.uniform(80, 200), "utilities", f"{g.choice(UTILITIES)} (nieuw contract)")
            _label(events, goal, move)
        elif goal == "farm_growth":
            auction = g.choice(AUCTIONS)
            for y, m in months_between(b.start, TODAY):
                if 5 <= m <= 10:
                    b.add(safe_date(y, m, g.randint(5, 25)), g.uniform(2000, 6000), "invoice_income", auction)
            for _ in range(g.randint(4, 8)):
                b.add(_days_ago(g, 60, 390), g.uniform(150, 1200), "other", g.choice(FARM_SUPPLIERS))
            b.add(dt.date(2026, 1, 15), g.uniform(120, 180), "other", "Boerenbond (lidgeld)")
            big = _days_ago(g, 10, 60)
            b.add(big, g.uniform(3000, 9000), "other", "Agrofront")
            _label(events, goal, big)
        elif goal == "first_investment":
            if "investment_plan" in products:
                products.remove("investment_plan")
            if "savings" not in products:
                products.append("savings")
            b.monthly(b.start, TODAY, 3, g.uniform(500, 900), "savings_transfer", "KBC Spaarrekening")
            pay = max((t for t in b.txs if t.category == "salary"), key=lambda t: t.date)
            bonus = dt.date(2025, 12, 18)
            amount = pay.amount * g.uniform(0.9, 1.1)
            b.add(bonus, amount, "salary", f"{pay.counterparty} (eindejaarspremie)")
            b.add(bonus + dt.timedelta(days=2), amount * 0.8, "savings_transfer", "KBC Spaarrekening")
            _label(events, goal, bonus)
        elif goal == "together" and g.random() < 0.6:
            start = _days_ago(g, 60, 200)
            _monthly_signed(b, start, TODAY, g.randint(1, 5), round(g.uniform(400, 800), 2), "other",
                            f"{_person(g)} (bijdrage huur)")
            _label(events, goal, start, kind="moved_in")
        elif goal == "separation":
            sep = _days_ago(g, 30, 150)
            _monthly_signed(b, b.start, sep - dt.timedelta(days=1), 2, round(g.uniform(500, 900), 2), "other",
                            f"{_person(g)} (bijdrage gezin)")
            new_rent = sep + dt.timedelta(days=3)
            b.monthly(new_rent, TODAY, new_rent.day, g.uniform(650, 950), "rent",
                      "Immo " + g.choice(NL_LAST + FR_LAST))
            b.add(min(TODAY, sep + dt.timedelta(days=g.randint(5, 40))), g.uniform(400, 1500), "other",
                  g.choice(FAMILY_LAWYERS))
            _label(events, goal, sep)
        elif goal == "new_baby":
            first = _days_ago(g, 20, 110)
            b.add(first, g.uniform(40, 200), "baby", g.choice(BABY))
            for _ in range(g.randint(2, 7)):
                b.add(first + dt.timedelta(days=g.randint(0, (TODAY - first).days)), g.uniform(20, 200), "baby",
                      g.choice(BABY))
            birth = first + dt.timedelta(days=g.randint(20, 60))
            if g.random() < 0.5 and birth <= TODAY - dt.timedelta(days=10):
                b.monthly(birth, TODAY, 8, 178.0, "child_benefit", CHILD_BENEFIT_PAYER)
            _label(events, goal, first)
        elif goal == "buy_home":
            if "savings" not in products:
                products.append("savings")
            search = _days_ago(g, 45, 200)
            b.monthly(search, TODAY, search.day, 9.99, "property", g.choice(PROPERTY_ALERTS))
            if g.random() < 0.5:
                b.add(search + dt.timedelta(days=g.randint(20, (TODAY - search).days - 5)), g.uniform(300, 500),
                      "property", g.choice(INSPECTORS))
            if g.random() < 0.3:
                d, amount = _days_ago(g, 5, 40), round(g.uniform(15000, 35000), -2)
                b.add_signed(d - dt.timedelta(days=2), amount, "savings_transfer", "KBC Spaarrekening")
                b.add(d, amount, "property", f"{g.choice(NOTARIES)} (derdenrekening)")
            _label(events, goal, search)
        return 0.0
    if goal == "sell_business":
        d = _days_ago(g, 20, 120)
        b.add(d, g.uniform(1500, 4000), "other", g.choice(AUDITORS))
        if g.random() < 0.6:
            b.add(min(TODAY, d + dt.timedelta(days=g.randint(5, 30))), g.uniform(800, 2500), "other",
                  g.choice(TRANSFER_LAWYERS))
        _label(events, goal, d)
    elif goal == "back_on_track":
        start = TODAY - dt.timedelta(days=150)
        for k in range(5):   # buy-now-pay-later use rising month after month
            for _ in range(k + g.randint(1, 2)):
                b.add(start + dt.timedelta(days=30 * k + g.randint(0, 29)), g.uniform(40, 180), "other", g.choice(BNPL))
        debits = [t for t in b.txs if t.category in ("telecom", "utilities", "subscription")
                  and TODAY - dt.timedelta(days=60) <= t.date <= TODAY - dt.timedelta(days=3)]
        for t in g.sample(debits, min(len(debits), g.randint(1, 2))):
            b.add_signed(t.date + dt.timedelta(days=2), -t.amount, "other", f"Storno domiciliëring {t.counterparty}")
        b.add(_days_ago(g, 5, 45), g.uniform(150, 600), "other", g.choice(BAILIFFS))
        _label(events, goal, start + dt.timedelta(days=60))
    elif goal == "ev_switch":
        first = _days_ago(g, 20, 110)
        b.add(first, g.uniform(8, 45), "transport", g.choice(CHARGERS))
        for _ in range(g.randint(2, 7)):
            b.add(first + dt.timedelta(days=g.randint(0, (TODAY - first).days)), g.uniform(8, 45), "transport",
                  g.choice(CHARGERS))
        _label(events, goal, first)
    elif goal == "together" and not any(e["type"] == "goal:together" for e in events):
        d = _days_ago(g, 20, 150)
        b.add(d, g.uniform(50, 150), "other", f"Gemeente {city} (huwelijk)")
        b.add(d - dt.timedelta(days=g.randint(10, 60)), g.uniform(1500, 5000), "other", g.choice(WEDDING_VENUES))
        b.add(d - dt.timedelta(days=g.randint(5, 90)), g.uniform(800, 3500), "other", g.choice(JEWELLERS))
        _label(events, goal, d, kind="wedding")
    elif goal == "travel":
        d = _days_ago(g, 3, 40)
        b.add(d, g.uniform(300, 2500), "leisure", g.choice(TRAVEL_BOOKINGS))
        if g.random() < 0.4:
            b.add(d + dt.timedelta(days=g.randint(0, 2)), g.uniform(250, 900), "leisure", "Booking.com")
        _label(events, goal, d)
    elif goal == "peace_of_mind":
        d = _days_ago(g, 1, 12)
        b.add(d, g.uniform(500, 3000), "other", g.choice(UNKNOWN_PAYEES))
        _label(events, goal, d, kind="new_payee")
    return round(sum(t.amount for t in b.txs[before:]), 2)


def inject_near_miss(g: random.Random, b: TxBuilder, pattern: str, events: list[dict], products: list[str],
                     age: int, phase: str) -> float:
    """Inject a look-alike pattern, labelled near_miss:<goal> for each goal it must not trigger."""
    if (phase == "before") != (pattern in NEAR_MISS_BEFORE):
        return 0.0
    before = len(b.txs)
    d = _days_ago(g, 10, 150)
    if pattern == "resale_income":
        b.add_signed(d, round(g.uniform(20, 250), 2), "other", g.choice(["2dehands.be uitbetaling", "Vinted uitbetaling"]))
    elif pattern == "webshop_refund":
        b.add_signed(d, round(g.uniform(30, 150), 2), "other", "Zalando SE (DE) terugbetaling")
    elif pattern == "hospital_bill":
        b.add(d, g.uniform(150, 900), "healthcare", "AZ Groeninge (ziekenhuisfactuur)")
    elif pattern == "rent_indexation":
        rents = _rents(b)
        landlord = rents[-1].counterparty
        for t in rents:
            if t.counterparty == landlord and t.date >= d:
                t.amount = round(t.amount * (1 + g.uniform(0.02, 0.04)), 2)
    elif pattern == "bookkeeper_only":
        cp = g.choice(BOOKKEEPERS)
        for y, m in months_between(b.start, TODAY):
            if m in (1, 4, 7, 10):
                b.add(safe_date(y, m, 25), g.uniform(150, 400), "other", cp)
    elif pattern == "single_bnpl":
        b.add(d, g.uniform(30, 150), "other", g.choice(BNPL))
    elif pattern == "garden_purchase":
        b.add(d, g.uniform(20, 90), "other", "Aveve")
    elif pattern == "holiday_charge":
        d = dt.date(2026, g.choice([7, 8]), g.randint(1, 28))
        b.add(d, g.uniform(25, 45), "transport", "Ionity")
    elif pattern == "saving_for_house":
        if "savings" not in products:
            products.append("savings")
        b.monthly(b.start, TODAY, 3, g.uniform(500, 900), "savings_transfer", "KBC Spaarrekening")
        b.monthly(d, TODAY, d.day, 9.99, "property", g.choice(PROPERTY_ALERTS))
        _label(events, "buy_home", d)   # a real goal, just not the near-missed one
    elif pattern == "december_jewellery":
        d = dt.date(2025, 12, g.randint(5, 23))
        b.add(d, g.uniform(300, 1500), "other", g.choice(JEWELLERS))
    elif pattern == "traffic_lawyer":
        b.add(d, g.uniform(200, 600), "other", "Advocaat Van Damme (verkeersboete)")
    elif pattern == "salary_pause":
        # parental leave or a sabbatical: the same employer pays again afterwards
        d = _days_ago(g, 190, 300)
        back = d + dt.timedelta(days=g.randint(60, 140))
        b.txs = [t for t in b.txs if not (t.category == "salary" and d < t.date < back)]
        if g.random() < 0.6:
            b.monthly(d + dt.timedelta(days=10), back, 15, g.uniform(400, 900), "benefit", "RVA (ouderschapsverlof)")
    elif pattern == "one_invoice":
        b.add(d, g.uniform(300, 900), "invoice_income", g.choice(SIDE_JOB_CLIENTS))
    elif pattern == "property_sale":
        b.add_signed(d, round(g.uniform(40000, 120000), -2), "other", f"{g.choice(NOTARIES)} (verkoop woning)")
        if 50 <= age <= 64:   # a big inflow can make the wealth goals legitimately visible: label them
            _label(events, "retire_well", d)
        if age >= 65 and "savings" not in products:
            _label(events, "peace_of_mind", d)
    elif pattern == "landlord_search":
        _monthly_signed(b, b.start, TODAY, 4, round(g.uniform(600, 900), 2), "other",
                        f"Huur {g.choice(STREETS)} (huurder {_person(g)})")
        d = _days_ago(g, 60, 300)
        b.monthly(d, TODAY, d.day, 9.99, "property", "Immoweb zoekalert")
    elif pattern == "accident_repair":
        amount = round(g.uniform(800, 2500), 2)
        b.add(d, amount, "transport", g.choice(GARAGE_NAMES))
        b.add_signed(min(TODAY, d + dt.timedelta(days=g.randint(7, 25))), amount, "other",
                     f"{g.choice(EXTERNAL_INSURERS)} (schadevergoeding)")
    elif pattern == "refunded_flight":
        d, amount = _days_ago(g, 8, 40), round(g.uniform(300, 900), 2)
        b.add(d, amount, "leisure", "Brussels Airlines")
        b.add_signed(d + dt.timedelta(days=g.randint(3, 7)), amount, "leisure", "Brussels Airlines (terugbetaling)")
    for goal in NEAR_MISS_LABELS[pattern]:
        events.append({"type": f"near_miss:{goal}", "date": d.isoformat(), "pattern": pattern})
    return round(sum(t.amount for t in b.txs[before:]), 2)


def label_base_trips(b: TxBuilder, events: list[dict]) -> None:
    """The balance sweep books some surplus months as a Neckermann trip: a real booking in the data, so label it."""
    if any(e["type"] == "goal:travel" for e in events):
        return
    trip = next((t for t in sorted(b.txs, key=lambda t: t.date, reverse=True)
                 if t.counterparty == "Neckermann Reizen" and t.amount <= -250
                 and t.date > TODAY - dt.timedelta(days=45)), None)
    if trip:
        _label(events, "travel", trip.date, kind="base_sweep")


def top_up_if_overdrawn(g: random.Random, b: TxBuilder, balance: float, since: dt.date) -> float:
    """A goal scenario must not leave the account overdrawn: a summer tax refund covers the gap."""
    if balance >= 300:
        return balance
    amount = round(300 - balance + g.uniform(200, 900), 2)
    b.add_signed(max(b.start, since - dt.timedelta(days=3)), amount, "tax", TAX_OFFICE + " (terugbetaling)")
    return round(balance + amount, 2)


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

    # --- goal scenarios (own RNG: everyone else is generated exactly as before)
    g = random.Random(seed * 7919 + cid * 31 + 1)
    first_job = pre_salary_living is not None
    goal = pick_goal_scenario(g, primary, personas, products, age, first_job, event_types)
    more = near = None
    if goal is None:   # extra draws only here, so the earlier goal scenarios stay exactly as they were
        more = pick_more_goal(g, b, primary, personas, products, age, first_job, event_types)
        if more is None:
            near = pick_near_miss(g, b, primary, personas, products, age, first_job)
    if goal == "retire_well":
        age = g.randint(50, 62)
        birth_year = TODAY.year - age
    elif goal == "study_start":
        age = g.randint(45, 56)
        birth_year = TODAY.year - age
    elif more == "care_parent" or near == "hospital_bill":
        age = g.randint(42, 62)
        birth_year = TODAY.year - age
    elif more == "sell_business" or near == "bookkeeper_only":
        age = g.randint(56, 64)
        birth_year = TODAY.year - age
    if goal:
        inject_goal_before_balance(g, b, goal, events, personas)
    if more:
        inject_more_goal(g, b, more, events, products, city, "before")
    if near:
        inject_near_miss(g, b, near, events, products, age, "before")

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
    if goal:
        balance = round(balance + inject_goal_after_balance(g, b, goal, events, products, age), 2)
        goal_dates = [dt.date.fromisoformat(e["date"]) for e in events if e["type"].startswith("goal:")]
        balance = top_up_if_overdrawn(g, b, balance, min(goal_dates) - dt.timedelta(days=200))
        if goal == "inheritance":
            # a big inflow can make other goals legitimately visible too: label them, so they don't count as noise
            if 50 <= age <= 64:
                events.append({"type": "goal:retire_well", "date": events[-1]["date"]})
            if age >= 65 and "savings" not in products:
                events.append({"type": "goal:peace_of_mind", "date": events[-1]["date"]})
            if "savings" not in products:
                events.append({"type": "idle_cash", "date": TODAY.isoformat()})
    if more or near:
        added = (inject_more_goal(g, b, more, events, products, city, "after") if more
                 else inject_near_miss(g, b, near, events, products, age, "after"))
        balance = round(balance + added, 2)
        dates = [dt.date.fromisoformat(e["date"]) for e in events if e["type"].startswith(("goal:", "near_miss:"))]
        balance = top_up_if_overdrawn(g, b, balance, min(dates) - dt.timedelta(days=200))
    label_base_trips(b, events)

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
        demos = demo_customers()
        for username, c, txs, bal in demos:
            store(c, txs, bal, username)
        db.insert_user(conn, "advisor", pw_hash, "advisor", None)
    conn.close()

    summary = {"customers": n + len(demos), "transactions": n_tx, "scenarios": dict(sorted(scenario_counts.items()))}
    if verbose:
        print(f"Built {db_path}")
        print(f"  customers:    {summary['customers']} ({n} regular + {summary['customers'] - n} demo)")
        print(f"  transactions: {n_tx}")
        print("  scenarios:")
        for k, v in summary["scenarios"].items():
            print(f"    {k:20s} {v}")
        print(f"  logins: lotte / sara / jan / marc / tom / els / amir / pieter / nina / c1..c{n} / advisor  (password: {DEMO_PASSWORD!r})")
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
