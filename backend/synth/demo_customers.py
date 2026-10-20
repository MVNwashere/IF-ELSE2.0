"""The hand-crafted demo customers (DESIGN.md §6.1; marc added in round 2).

  lotte (9001)  2018 student in Leuven → 2021 first job → 2021-22 house hunt + mortgage → 2024 baby → Oct 2026 goes freelance (first invoice 4 days before TODAY)
  sara  (9002)  freelancer AND young mother; car insurance renews in 12 days; Netflix price increase
  jan   (9003)  71, retiree; duplicate charge; idle cash
  marc  (9004)  52, the investor: salary, mortgage nearly paid off, pension savings, €48k idle, a trip booked

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
    salary_end = D(2026, 10, 1)

    def salary(d: dt.date) -> float:
        return 2350 * (1.03 ** (d.year - 2021))

    b.monthly(first_salary, salary_end, 1, salary, "salary", "Cronos Groep")
    # Belgian 13th month every December; when she leaves at the end of Sep 2026 the pro-rata 13th month and the
    # exit holiday pay are paid out with the last pay slip
    b.yearly(D(2021, 12, 1), D(2025, 12, 31), 12, 20, lambda d: salary(d) * 0.85, "salary", "Cronos Groep (eindejaarspremie)")
    b.add(D(2026, 9, 30), salary(D(2026, 9, 30)) * 0.85 * 9 / 12, "salary", "Cronos Groep (eindejaarspremie pro rata)")
    b.add(D(2026, 9, 30), 2100, "salary", "Cronos Groep (vertrekvakantiegeld)")
    b.monthly(D(2021, 8, 1), D(2022, 3, 31), 1, 720, "rent", "Immo Vermeulen")
    living_costs(b, D(2021, 6, 1), D(2022, 3, 31), scale=0.9, subscription=("Netflix", 13.99, 13.99),
                 telecom=("Telenet", 52.0, 52.0))

    # ---- 2021-10 → 2022-02: the leading signals of a house purchase, months before the deed (round 2: intent).
    # A property-portal search alert, a pre-purchase building inspection, then the deposit at the preliminary
    # sales agreement, paid into the notary's escrow account (funded from savings).
    b.monthly(D(2021, 10, 6), D(2022, 2, 28), 6, 9.99, "property", "Zimmo Premium zoekalert")
    b.add(D(2022, 1, 18), 395, "property", "Bouwkundig Expertisebureau Vandamme")
    b.add_signed(D(2022, 2, 7), +15000.0, "savings_transfer", "KBC Spaarrekening (naar zichtrekening)")
    b.add(D(2022, 2, 8), 15000, "property", "Notaris Van den Broeck (derdenrekening)")

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
    # energy crisis: the yearly settlement bill for the new (uninsulated) house, and higher advances after it
    b.add(D(2022, 11, 14), 640, "utilities", "Engie (jaarafrekening)")
    b.monthly(D(2022, 12, 10), D(2023, 11, 30), 10, 95, "utilities", "Engie (voorschot verhoging)")
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

    # ---- Oct 2026: goes freelance (left Cronos at the end of September). The round 2 hero story starts here:
    # she registers her business at the enterprise counter, then her first client pays four days before TODAY.
    # Nothing else yet: the first VAT return (Jan 2027) and social contributions (Dec 2026) lie in the future.
    b.add(D(2026, 10, 2), 105.50, "other", "Ondernemingsloket Xerius (inschrijving KBO)")
    # a work laptop bought on the private account a week after registering (a business expense on the wrong account)
    b.add(D(2026, 10, 9), 1499, "furniture", "Coolblue (laptop)")
    # first invoice: 8 consultancy days at €475 excl. VAT = €3,800 + 21% VAT
    b.add(D(2026, 10, 16), 4598, "invoice_income", "Bright Agency")

    # ---- balance path per era; some student month-ends deliberately low so the runway card fires
    # salary lands on the 1st, so the month-end balance is the monthly minimum: bands are daily bands
    bands = era_bands([
        (DEMO_START, (300, 900, 480)),
        (D(2021, 7, 1), (1600, 4500, 1900)),
        (D(2024, 2, 1), (2100, 5000, 2400)),
        (D(2026, 9, 30), (3200, 8000, 5500)),
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
                {"type": "first_invoice", "date": "2026-10-16"},
                {"type": "goal:go_freelance", "date": "2026-10-16"},
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
    # VAT and contributions run until the end of September: the Q3 VAT return is due on TODAY and not paid yet
    freelance_income(b, D(2022, 1, 1), D(2026, 9, 30), clients, lo=800, hi=2500, per_month=2.5,
                     social_fund="Xerius", social_amount=1280, invoice_end=D(2026, 6, 30))
    # Q3 2026 invoices hand-picked: ≈ €9,000 so the VAT reserve is ≈ €1,900
    for d, amt, cp in [(D(2026, 7, 6), 1650, "Studio Nord"), (D(2026, 7, 21), 1180, "Vzw De Kring"),
                       (D(2026, 8, 4), 2100, "Immo Verstraete"), (D(2026, 8, 19), 940, "Bakkerij Peeters"),
                       (D(2026, 9, 3), 1820, "Sofico BV"), (D(2026, 9, 12), 1310, "Atelier Vos")]:
        b.add(d, amt, "invoice_income", cp)
    # Q4 has started: two invoices paid in October before TODAY
    for d, amt, cp in [(D(2026, 10, 5), 1740, "Studio Nord"), (D(2026, 10, 14), 1390, "Sofico BV")]:
        b.add(d, amt, "invoice_income", cp)
    # a steady retainer client (monthly, around the 24th) who stopped paying after June: the late-client card
    b.monthly(D(2025, 1, 24), D(2026, 6, 30), 24, 650, "invoice_income", "Brouwerij Het Anker", jitter_amount=0.0)

    # house since mid-2019 (deposit from savings)
    b.monthly(DEMO_START, D(2019, 5, 31), 1, 780, "rent", "Immo De Smet")
    b.add_signed(D(2019, 5, 17), +14000.0, "savings_transfer", "KBC Spaarrekening (naar zichtrekening)")
    b.add(D(2019, 5, 20), 14800, "notary", "Notaris Lambrechts")
    b.monthly(D(2019, 6, 5), TODAY, 5, 1120, "mortgage", "KBC Woningkrediet")
    b.yearly(D(2019, 6, 1), TODAY, 6, 3, 298, "insurance_home", KBC_INSURANCE)

    # car insurance with an external insurer, renews 2026-11-01 (12 days after TODAY)
    for year, premium in [(2019, 548), (2020, 560), (2021, 571), (2022, 589), (2023, 589), (2024, 612), (2025, 612)]:
        b.add(D(year, 11, 1), premium, "insurance_car", "AG Insurance")

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
                {"type": "insurance_renewal", "date": "2026-11-01", "counterparty": "AG Insurance", "amount": 612},
                {"type": "price_increase", "date": "2026-09-14", "counterparty": "Netflix", "from": 13.99, "to": 17.99},
                {"type": "late_client", "date": "2026-06-24", "counterparty": "Brouwerij Het Anker", "amount": 650},
                {"type": "goal:get_paid", "date": "2026-08-24"},
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

    # duplicate charge: Colruyt €64.20 twice on 17 Oct 2026
    b.add(D(2026, 10, 17), 64.20, "groceries", "Colruyt")
    b.add(D(2026, 10, 17), 64.20, "groceries", "Colruyt")

    # first payment ever to an unknown payee ("was this you?"): a typical helpdesk-scam amount, two days before TODAY
    b.add(D(2026, 10, 18), 1250, "other", "Tech Support Services BV")

    # no savings product: the balance just sits on the current account (≈ €14,000 for years; the band is
    # €1,800 higher than it would otherwise be so the idle-cash story survives the €1,250 new-payee payment)
    trips = [("leisure", "Neckermann Reizen"), ("leisure", "TUI"), ("other", "Cadeau kleinkinderen"),
             ("furniture", "Weba"), ("transport", "Garage Peeters")]
    until = TODAY - dt.timedelta(days=91)
    balance_today = calibrate_balance(b, 14200.0, fixed_band(14000, 15600, 14600), excess=trips, until=until)
    balance_today = round(balance_today + sum(t.amount for t in b.between(until + dt.timedelta(days=1), TODAY)), 2)

    customer = Customer(
        id=9003, first_name="Jan", last_name="Willems", birth_year=1955, city="Antwerpen", language="nl",
        products=["current", "home_insurance"], consent_personalization=True,
        ground_truth={
            "personas": ["retiree"],
            "events": [
                {"type": "pension_start", "date": "2020-04-03"},
                {"type": "duplicate_charge", "date": "2026-10-17", "counterparty": "Colruyt", "amount": 64.20},
                {"type": "new_payee", "date": "2026-10-18", "counterparty": "Tech Support Services BV", "amount": 1250},
                {"type": "idle_cash", "date": TODAY.isoformat(), "balance": balance_today},
                {"type": "goal:peace_of_mind", "date": "2026-10-18"},
            ],
        },
    )
    return "jan", customer, b.txs, balance_today


def _marc() -> tuple[str, Customer, list[Transaction], float]:
    """Round 2 persona: the 52-year-old investor. Good salary, mortgage almost paid off, two students at
    university, pension savings already at KBC, and about €48,000 doing nothing on the current account."""
    rng = random.Random(9004)
    b = TxBuilder(9004, rng, DEMO_START, TODAY)

    def salary(d: dt.date) -> float:
        return 4600 * (1.02 ** (d.year - 2018))

    b.monthly(DEMO_START, TODAY, 1, salary, "salary", "Barco NV")
    b.yearly(DEMO_START, TODAY, 12, 20, lambda d: salary(d) * 0.9, "salary", "Barco NV (eindejaarspremie)")
    b.monthly(DEMO_START, TODAY, 5, 1250, "mortgage", "KBC Woningkrediet")   # ends June 2027
    b.yearly(DEMO_START, TODAY, 3, 1, 395, "insurance_home", KBC_INSURANCE)
    b.yearly(DEMO_START, TODAY, 3, 1, 110, "insurance_family", KBC_INSURANCE)
    b.yearly(DEMO_START, TODAY, 12, 15, 1020, "savings_transfer", "KBC Pensioenspaarfonds")
    # two children at university in Ghent: a monthly transfer for their student room
    b.monthly(D(2022, 9, 1), TODAY, 3, 450, "other", "Overschrijving Lars (kot Gent)")
    b.monthly(D(2025, 9, 1), TODAY, 3, 450, "other", "Overschrijving Emma (kot Gent)")
    living_costs(b, DEMO_START, TODAY, scale=1.5, subscription=("Netflix", 13.99, 17.99),
                 telecom=("Proximus", 89.0, 89.0))
    b.scatter(DEMO_START, TODAY, "leisure", ["Restaurant De Vitrine", "Decathlon", "Kinepolis", "Fnac"], 2.0, 25, 140)
    # autumn trip to Lisbon booked in September 2026
    b.add(D(2026, 9, 8), 1180, "leisure", "Brussels Airlines")
    b.add(D(2026, 9, 9), 940, "leisure", "Booking.com")

    # no savings account: the surplus simply piles up on the current account (≈ €48,000 today). Calibrate until
    # three months before TODAY so no excess sweep (a big garage bill) lands in the 90-day spend window.
    trips = [("leisure", "TUI"), ("furniture", "Vanden Borre"), ("transport", "Garage D'Ieteren")]
    until = TODAY - dt.timedelta(days=91)
    balance_today = calibrate_balance(b, 30000.0, era_bands([
        (DEMO_START, (28000, 34000, 30000)),
        (D(2022, 1, 1), (36000, 44000, 40000)),
        (D(2025, 1, 1), (44000, 50000, 46000)),
    ]), excess=trips, until=until)
    balance_today = round(balance_today + sum(t.amount for t in b.between(until + dt.timedelta(days=1), TODAY)), 2)

    customer = Customer(
        id=9004, first_name="Marc", last_name="Claes", birth_year=1974, city="Mechelen", language="nl",
        products=["current", "mortgage", "home_insurance", "family_insurance", "pension_savings"],
        consent_personalization=True,
        ground_truth={
            "personas": ["young_professional"],
            "events": [{"type": "idle_cash", "date": TODAY.isoformat(), "balance": balance_today},
                       {"type": "goal:retire_well", "date": "2026-01-01"}],
        },
    )
    return "marc", customer, b.txs, balance_today


def demo_customers() -> list[tuple[str, Customer, list[Transaction], float]]:
    """Returns [(username, customer, transactions, balance_today), ...]."""
    return [_lotte(), _sara(), _jan(), _marc()]
