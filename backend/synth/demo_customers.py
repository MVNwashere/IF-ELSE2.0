"""The three hand-crafted demo customers (DESIGN.md §6.1).

  lotte (9001)  2018 student in Leuven → 2021 first job → 2022 moves in + mortgage → 2024 baby → 2026 freelance
  sara  (9002)  freelancer AND young mother; car insurance renews in 12 days; Netflix price increase
  jan   (9003)  71, retiree; duplicate charge; idle cash

Eight years of history so that yearly patterns and the time-travel slider work. The running balance of each
demo customer is calibrated per life era (see `calibrate_balance`) so that the walk-back
`balance(as_of) = balance_today − Σ amount(txs after as_of)` gives a sane number in every era.
"""
from __future__ import annotations

import datetime as dt
import random

from app.schemas import Customer, Transaction

from .generate import (
    BABY, CHILD_BENEFIT_PAYER, HEALTHCARE, KBC_INSURANCE, TODAY, TxBuilder, add_months, calibrate_balance,
    era_bands, fixed_band, freelance_income, living_costs, retiree_life, student_life,
)

DEMO_START = dt.date(2018, 9, 1)
D = dt.date
SAVINGS = ("savings_transfer", "KBC Spaarrekening")


def _lotte() -> tuple[str, Customer, list[Transaction], float]:
    rng = random.Random(9001)
    b = TxBuilder(9001, rng, DEMO_START, TODAY)

    # ---- 2018-09 → 2021-06: student in Leuven (net cash flow ≈ 0; parents cover tuition in October)
    student_end = D(2021, 5, 31)
    student_life(b, DEMO_START, student_end, kot_rent=300, allowance=400, tuition=979.60)
    living_costs(b, DEMO_START, student_end, scale=0.35, subscription=("Spotify Student", 4.99, 5.99),
                 increase_date=D(2019, 10, 14))
    # duplicate charge at the student restaurant, a few days before 1 Mar 2020
    b.add(D(2020, 2, 26), 7.80, "groceries", "Alma 2 Leuven")
    b.add(D(2020, 2, 26), 7.80, "groceries", "Alma 2 Leuven")

    # ---- 2021-07: first salary at Cronos Groep (started 1 June, paid on the 1st); rents a flat from August
    first_salary = D(2021, 7, 1)
    salary_end = D(2025, 12, 1)

    def salary(d: dt.date) -> float:
        return 2350 * (1.03 ** (d.year - 2021))

    b.monthly(first_salary, salary_end, 1, salary, "salary", "Cronos Groep")
    # Belgian 13th month every December; when she leaves at the end of 2025 the exit holiday pay is paid out too
    b.yearly(D(2021, 12, 1), D(2025, 12, 31), 12, 20, lambda d: salary(d) * 0.85, "salary", "Cronos Groep (eindejaarspremie)")
    b.add(D(2025, 12, 31), 1900, "salary", "Cronos Groep (vertrekvakantiegeld)")
    b.monthly(D(2021, 8, 1), D(2022, 3, 31), 1, 720, "rent", "Immo Vermeulen")
    living_costs(b, D(2021, 6, 1), D(2022, 3, 31), scale=0.9, subscription=("Netflix", 13.99, 13.99),
                 telecom=("Telenet", 52.0, 52.0))

    # ---- 2022-03: moves in with partner, buys a house (deposit comes back from her savings account)
    b.add_signed(D(2022, 3, 14), +12000.0, "savings_transfer", "KBC Spaarrekening (naar zichtrekening)")
    b.add(D(2022, 3, 15), 12500, "notary", "Notaris Van den Broeck")
    for d, amt, cp in [(D(2022, 3, 19), 1240, "IKEA Zaventem"), (D(2022, 4, 2), 850, "Weba"),
                       (D(2022, 4, 23), 430, "IKEA Zaventem"), (D(2022, 5, 7), 320, "Brico")]:
        b.add(d, amt, "furniture", cp)
    b.monthly(D(2022, 4, 5), TODAY, 5, 1050, "mortgage", "KBC Woningkrediet")
    b.yearly(D(2022, 4, 1), TODAY, 4, 12, 312, "insurance_home", KBC_INSURANCE)
    # Telenet price increase in September 2022
    living_costs(b, D(2022, 4, 1), D(2024, 1, 31), scale=1.15, subscription=("Netflix", 13.99, 13.99),
                 telecom=("Telenet", 52.0, 58.0), telecom_increase_date=D(2022, 9, 12))
    # gym membership, price bump in February 2025
    b.monthly(D(2023, 1, 20), TODAY, 20, lambda d: 29.99 if d >= D(2025, 2, 20) else 24.99, "subscription", "Basic-Fit")

    # ---- 2024-02: baby Noor
    baby = D(2024, 2, 10)
    b.scatter(baby - dt.timedelta(days=45), add_months(baby, 8), "baby", BABY, 4, 25, 160)
    b.monthly(D(2024, 3, 8), TODAY, 8, 178, "child_benefit", CHILD_BENEFIT_PAYER)
    b.monthly(D(2024, 6, 1), TODAY, 1, 520, "childcare", "Kinderdagverblijf De Speelboom", jitter_amount=0.06)
    b.scatter(baby, add_months(baby, 3), "healthcare", HEALTHCARE, 3, 20, 120)
    living_costs(b, D(2024, 2, 1), TODAY, scale=1.1, subscription=("Netflix", 13.99, 13.99),
                 telecom=("Telenet", 58.0, 58.0))
    b.yearly(D(2024, 3, 1), TODAY, 3, 20, 96, "insurance_family", KBC_INSURANCE)

    # ---- 2026-01: goes freelance (salary stops after Dec 2025); first invoice on 15 Jan.
    # Invoices are hand-picked and land early in the month (before the fixed costs), two per month, 4 clients.
    invoices = [
        (D(2026, 1, 15), 1850, "Bright Agency"), (D(2026, 1, 28), 1400, "Gemeente Herent"),
        (D(2026, 2, 4), 2150, "Vzw Kompas"), (D(2026, 2, 17), 1680, "Bright Agency"),
        (D(2026, 3, 5), 1920, "Dupont & Co"), (D(2026, 3, 18), 2300, "Gemeente Herent"),
        (D(2026, 4, 3), 1750, "Bright Agency"), (D(2026, 4, 16), 2050, "Vzw Kompas"),
        (D(2026, 5, 6), 2400, "Dupont & Co"), (D(2026, 5, 19), 1500, "Bright Agency"),
        (D(2026, 6, 4), 1980, "Gemeente Herent"), (D(2026, 6, 17), 2200, "Vzw Kompas"),
        (D(2026, 7, 3), 1650, "Bright Agency"), (D(2026, 7, 16), 2350, "Dupont & Co"),
        (D(2026, 8, 5), 2100, "Gemeente Herent"), (D(2026, 8, 18), 1450, "Vzw Kompas"),
        (D(2026, 9, 4), 2250, "Bright Agency"), (D(2026, 9, 17), 1900, "Dupont & Co"),
    ]
    for d, amt, cp in invoices:
        b.add(d, amt, "invoice_income", cp)
    # no random invoices (invoice_end before start), but quarterly VAT and social contributions
    freelance_income(b, D(2026, 1, 16), TODAY, ["Bright Agency"], invoice_end=D(2026, 1, 15),
                     social_fund="Xerius", social_amount=1150)

    # ---- balance path per era; some student month-ends deliberately low so the runway card fires
    # salary lands on the 1st, so the month-end balance is the monthly minimum: bands are daily bands
    bands = era_bands([
        (DEMO_START, (300, 900, 480)),
        (D(2021, 7, 1), (1600, 4500, 1900)),
        (D(2024, 2, 1), (2100, 5000, 2400)),
        (D(2025, 12, 1), (3200, 8000, 5500)),
    ])
    low_months = {(2019, 10): 250, (2020, 4): 250, (2020, 11): 260}
    balance_today = calibrate_balance(b, 420.0, bands, overrides=low_months, excess=SAVINGS)

    customer = Customer(
        id=9001, first_name="Lotte", last_name="Peeters", birth_year=1999, city="Leuven", language="nl",
        products=["current", "savings", "mortgage", "home_insurance"], consent_personalization=True,
        ground_truth={
            "personas": ["student", "young_professional", "young_family", "freelancer"],
            "events": [
                {"type": "student", "date": "2018-09-01"},
                {"type": "price_increase", "date": "2019-10-14", "counterparty": "Spotify Student", "from": 4.99, "to": 5.99},
                {"type": "duplicate_charge", "date": "2020-02-26", "counterparty": "Alma 2 Leuven", "amount": 7.80},
                {"type": "first_salary", "date": first_salary.isoformat(), "employer": "Cronos Groep"},
                {"type": "moved_house", "date": "2022-03-15"},
                {"type": "price_increase", "date": "2022-09-12", "counterparty": "Telenet", "from": 52.0, "to": 58.0},
                {"type": "baby", "date": baby.isoformat()},
                {"type": "price_increase", "date": "2025-02-20", "counterparty": "Basic-Fit", "from": 24.99, "to": 29.99},
                {"type": "first_invoice", "date": "2026-01-15"},
            ],
        },
    )
    return "lotte", customer, b.txs, balance_today


def _sara() -> tuple[str, Customer, list[Transaction], float]:
    rng = random.Random(9002)
    b = TxBuilder(9002, rng, DEMO_START, TODAY)

    # employee until end 2021, freelancer since 2022 with 6 clients (~€3,500–4,500 a month)
    b.monthly(DEMO_START, D(2021, 12, 31), 27, 2600, "salary", "Universiteit Gent", jitter_amount=0.01)
    clients = ["Studio Nord", "Bakkerij Peeters", "Vzw De Kring", "Atelier Vos", "Immo Verstraete", "Sofico BV"]
    freelance_income(b, D(2022, 1, 1), TODAY, clients, lo=800, hi=2500, per_month=2.5,
                     social_fund="Xerius", social_amount=1280, invoice_end=D(2026, 6, 30))
    # Q3 2026 invoices hand-picked: ≈ €9,000 so the VAT reserve is ≈ €1,900
    for d, amt, cp in [(D(2026, 7, 6), 1650, "Studio Nord"), (D(2026, 7, 21), 1180, "Vzw De Kring"),
                       (D(2026, 8, 4), 2100, "Immo Verstraete"), (D(2026, 8, 19), 940, "Bakkerij Peeters"),
                       (D(2026, 9, 3), 1820, "Sofico BV"), (D(2026, 9, 12), 1310, "Atelier Vos")]:
        b.add(d, amt, "invoice_income", cp)
    # a steady retainer client (monthly, around the 24th) who stopped paying after June: the late-client card
    b.monthly(D(2025, 1, 24), D(2026, 6, 30), 24, 650, "invoice_income", "Brouwerij Het Anker", jitter_amount=0.0)

    # house since mid-2019 (deposit from savings)
    b.monthly(DEMO_START, D(2019, 5, 31), 1, 780, "rent", "Immo De Smet")
    b.add_signed(D(2019, 5, 17), +14000.0, "savings_transfer", "KBC Spaarrekening (naar zichtrekening)")
    b.add(D(2019, 5, 20), 14800, "notary", "Notaris Lambrechts")
    b.monthly(D(2019, 6, 5), TODAY, 5, 1120, "mortgage", "KBC Woningkrediet")
    b.yearly(D(2019, 6, 1), TODAY, 6, 3, 298, "insurance_home", KBC_INSURANCE)

    # car insurance with an external insurer, renews 2026-10-12 (12 days after TODAY)
    for year, premium in [(2019, 548), (2020, 560), (2021, 571), (2022, 589), (2023, 589), (2024, 612), (2025, 612)]:
        b.add(D(year, 10, 12), premium, "insurance_car", "AG Insurance")

    # baby Noor, Feb 2024
    baby = D(2024, 2, 3)
    b.scatter(baby - dt.timedelta(days=40), add_months(baby, 7), "baby", BABY, 4, 25, 150)
    b.monthly(D(2024, 3, 8), TODAY, 8, 178, "child_benefit", CHILD_BENEFIT_PAYER)
    b.monthly(D(2024, 6, 1), TODAY, 1, 540, "childcare", "Kinderdagverblijf 't Nest", jitter_amount=0.05)
    b.yearly(D(2024, 4, 1), TODAY, 4, 15, 104, "insurance_family", KBC_INSURANCE)

    # savings habit, Netflix price increase on 2026-09-14
    b.monthly(D(2019, 1, 2), TODAY, 2, 75, "savings_transfer", "KBC Spaarrekening")
    living_costs(b, DEMO_START, D(2024, 1, 31), scale=1.0, subscription=("Netflix", 13.99, 13.99))
    living_costs(b, D(2024, 2, 1), TODAY, scale=1.3, subscription=("Netflix", 13.99, 17.99),
                 increase_date=D(2026, 9, 14))

    balance_today = calibrate_balance(b, 3600.0, fixed_band(3000, 8000, 5000), excess=SAVINGS)

    customer = Customer(
        id=9002, first_name="Sara", last_name="Maes", birth_year=1990, city="Gent", language="nl",
        products=["current", "savings", "mortgage"], consent_personalization=True,
        ground_truth={
            "personas": ["freelancer", "young_family"],
            "events": [
                {"type": "first_invoice", "date": "2022-01-01"},
                {"type": "baby", "date": baby.isoformat()},
                {"type": "insurance_renewal", "date": "2026-10-12", "counterparty": "AG Insurance", "amount": 612},
                {"type": "price_increase", "date": "2026-09-14", "counterparty": "Netflix", "from": 13.99, "to": 17.99},
                {"type": "late_client", "date": "2026-06-24", "counterparty": "Brouwerij Het Anker", "amount": 650},
            ],
        },
    )
    return "sara", customer, b.txs, balance_today


def _jan() -> tuple[str, Customer, list[Transaction], float]:
    rng = random.Random(9003)
    b = TxBuilder(9003, rng, DEMO_START, TODAY)

    # worked at Bekaert until March 2020 (turned 65), pension since April 2020
    b.monthly(DEMO_START, D(2020, 3, 31), 27, 2600, "salary", "Bekaert", jitter_amount=0.01)
    retiree_life(b, D(2020, 4, 1), TODAY, pension=1850)
    b.scatter(DEMO_START, D(2020, 3, 31), "healthcare", HEALTHCARE, 1.2, 12, 80)

    # owns the house: no rent/mortgage, but home + family insurance with KBC
    b.yearly(DEMO_START, TODAY, 2, 18, 341, "insurance_home", KBC_INSURANCE)
    b.yearly(DEMO_START, TODAY, 2, 18, 88, "insurance_family", KBC_INSURANCE)
    living_costs(b, DEMO_START, TODAY, scale=1.15, subscription=("Streamz", 12.99, 12.99))
    b.scatter(DEMO_START, TODAY, "leisure", ["Tuincentrum Aveve", "Petanqueclub Rivierenhof", "De Roma"], 1.5, 10, 60)
    b.scatter(DEMO_START, TODAY, "other", ["Cadeau kleinkinderen", "Standaard Boekhandel", "Hema"], 1.0, 20, 120)

    # duplicate charge: Colruyt €64.20 twice on 27 Sep 2026
    b.add(D(2026, 9, 27), 64.20, "groceries", "Colruyt")
    b.add(D(2026, 9, 27), 64.20, "groceries", "Colruyt")

    # first payment ever to an unknown payee ("was this you?"): a typical helpdesk-scam amount, two days before TODAY
    b.add(D(2026, 9, 28), 1250, "other", "Tech Support Services BV")

    # no savings product: the balance just sits on the current account (≈ €14,000 for years; the band is
    # €1,200 higher than it would otherwise be so the idle-cash story survives the €1,250 new-payee payment)
    trips = [("leisure", "Neckermann Reizen"), ("leisure", "TUI"), ("other", "Cadeau kleinkinderen"),
             ("furniture", "Weba"), ("transport", "Garage Peeters")]
    until = TODAY - dt.timedelta(days=91)
    balance_today = calibrate_balance(b, 13600.0, fixed_band(13400, 15000, 14000), excess=trips, until=until)
    balance_today = round(balance_today + sum(t.amount for t in b.between(until + dt.timedelta(days=1), TODAY)), 2)

    customer = Customer(
        id=9003, first_name="Jan", last_name="Willems", birth_year=1955, city="Antwerpen", language="nl",
        products=["current", "home_insurance"], consent_personalization=True,
        ground_truth={
            "personas": ["retiree"],
            "events": [
                {"type": "pension_start", "date": "2020-04-03"},
                {"type": "duplicate_charge", "date": "2026-09-27", "counterparty": "Colruyt", "amount": 64.20},
                {"type": "new_payee", "date": "2026-09-28", "counterparty": "Tech Support Services BV", "amount": 1250},
                {"type": "idle_cash", "date": TODAY.isoformat(), "balance": balance_today},
            ],
        },
    )
    return "jan", customer, b.txs, balance_today


def demo_customers() -> list[tuple[str, Customer, list[Transaction], float]]:
    """Returns [(username, customer, transactions, balance_today), ...]."""
    return [_lotte(), _sara(), _jan()]
