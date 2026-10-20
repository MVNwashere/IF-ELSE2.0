"""The hand-crafted demo customers (docs/CUSTOMER-APP.md).

  lotte (9001)  2018 student in Leuven → 2021 first job → 2021-22 house hunt + mortgage → 2024 baby → Oct 2026 goes freelance (first invoice 4 days before TODAY)
  sara  (9002)  freelancer AND young mother; car insurance renews in 12 days; Netflix price increase
  jan   (9003)  71, retiree; duplicate charge; idle cash
  marc  (9004)  52, the investor: salary, mortgage nearly paid off, pension savings, €48k idle, a trip booked
  tom   (9005)  31, employed + a side business since Jul 2026 (side_job)
  els   (9006)  48, sandwich generation: eldest starts at UGent, mother moved into a care home (care_parent, study_start)
  amir  (9007)  34, newcomer since Jun 2026, four months of history, moving into a long-term flat (move_house)
  pieter(9008)  44, SME owner with two employees, German and Dutch clients since May 2026 (go_international)
  nina  (9009)  29, rising buy-now-pay-later, bounced direct debits, a bailiff (back_on_track; commercial goals quiet)

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

    # ---- 2021-10 → 2022-02: the leading signals of a house purchase, months before the deed (intent).
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

    # ---- Oct 2026: goes freelance (left Cronos at the end of September). The hero story starts here:
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
    """Demo persona: the 52-year-old investor. Good salary, mortgage almost paid off, two students at
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


def _tom() -> tuple[str, Customer, list[Transaction], float]:
    """Demo persona: the side-jobber. 31, employed at Materialise since 2021, rents a flat in Leuven, and since
    July 2026 builds websites on the side (bijberoep): registered at the enterprise counter, small client payments,
    a first quarterly contribution. The salary keeps coming: this is not go_freelance."""
    rng = random.Random(9005)
    start = D(2023, 1, 1)
    b = TxBuilder(9005, rng, start, TODAY)

    def salary(d: dt.date) -> float:
        return 2950 * (1.025 ** (d.year - 2023))

    b.monthly(start, TODAY, 28, salary, "salary", "Materialise NV")
    b.yearly(start, TODAY, 12, 20, lambda d: salary(d) * 0.85, "salary", "Materialise NV (eindejaarspremie)")
    b.monthly(start, TODAY, 2, 850, "rent", "Immo Rentiers Leuven")
    living_costs(b, start, TODAY, scale=1.0, subscription=("Spotify", 10.99, 12.99), increase_date=D(2025, 5, 14),
                 telecom=("Telenet", 55.0, 55.0))
    b.yearly(start, TODAY, 5, 1, 495, "insurance_car", "Baloise")

    # ---- side business (web design) since July 2026
    b.add(D(2026, 7, 3), 105.50, "other", "Ondernemingsloket Liantis (inschrijving KBO)")
    for d, amt, cp in [(D(2026, 7, 29), 650, "Bakkerij Wouters"), (D(2026, 8, 26), 1210, "Vzw Sportkring Heverlee"),
                       (D(2026, 9, 18), 480, "Bakkerij Wouters"), (D(2026, 10, 9), 1450, "Vzw Sportkring Heverlee")]:
        b.add(d, amt, "invoice_income", cp)
    b.add(D(2026, 9, 29), 96.40, "social_contribution", "Liantis (bijberoep)")
    b.add(D(2026, 7, 11), 89, "subscription", "Adobe Creative Cloud")
    b.monthly(D(2026, 8, 11), TODAY, 11, 69.99, "subscription", "Adobe Creative Cloud")

    # Savings sweeps only until four months ago: no "saving up for a house" pattern right now (buy_home stays quiet)
    until = TODAY - dt.timedelta(days=125)
    balance_today = calibrate_balance(b, 2500.0, fixed_band(1800, 5000, 2600), excess=SAVINGS, until=until)
    balance_today = round(balance_today + sum(t.amount for t in b.between(until + dt.timedelta(days=1), TODAY)), 2)

    customer = Customer(
        id=9005, first_name="Tom", last_name="Vandenberghe", birth_year=1995, city="Leuven", language="nl",
        products=["current", "savings"], consent_personalization=True,
        ground_truth={
            "personas": ["young_professional"],
            "events": [{"type": "first_invoice", "date": "2026-07-29"},
                       {"type": "goal:side_job", "date": "2026-07-29"}],
        },
    )
    return "tom", customer, b.txs, balance_today


def _els() -> tuple[str, Customer, list[Transaction], float]:
    """Demo persona: the sandwich generation. 48, two children, the eldest started at UGent in Sep 2026 (tuition
    plus a monthly transfer for his student room), and her mother moved into a care home in Aug 2026 after a few
    months of home care. Els tops up the care-home bill."""
    rng = random.Random(9006)
    start = D(2021, 1, 1)
    b = TxBuilder(9006, rng, start, TODAY)

    def salary(d: dt.date) -> float:
        return 3350 * (1.02 ** (d.year - 2021))

    b.monthly(start, TODAY, 27, salary, "salary", "Stad Gent")
    b.yearly(start, TODAY, 12, 20, lambda d: salary(d) * 0.88, "salary", "Stad Gent (eindejaarspremie)")
    b.monthly(start, TODAY, 5, 980, "mortgage", "KBC Woningkrediet")
    b.yearly(start, TODAY, 2, 10, 365, "insurance_home", KBC_INSURANCE)
    b.yearly(start, TODAY, 2, 10, 104, "insurance_family", KBC_INSURANCE)
    b.monthly(start, TODAY, 8, 356, "child_benefit", CHILD_BENEFIT_PAYER)
    b.scatter(start, TODAY, "school", ["Sint-Barbaracollege", "Studieshop.be", "Schoolfactuur Sint-Bavo"], 0.6, 25, 160)
    living_costs(b, start, TODAY, scale=1.4, subscription=("Netflix", 13.99, 17.99), increase_date=D(2026, 9, 14),
                 telecom=("Proximus", 79.0, 79.0))

    # ---- her mother: home care from March, a care home from August 2026 (Els pays the part the pension doesn't cover)
    b.monthly(D(2026, 3, 1), D(2026, 7, 31), 12, 185, "healthcare", "Familiehulp (thuiszorg)", jitter_amount=0.1)
    b.add(D(2026, 8, 5), 1300, "healthcare", "WZC Hof ter Linde (woonzorgcentrum)")    # first month + entry fee
    b.monthly(D(2026, 9, 5), TODAY, 5, 650, "healthcare", "WZC Hof ter Linde (woonzorgcentrum)")

    # ---- the eldest, Ruben, starts at UGent
    b.add(D(2026, 9, 25), 1153.80, "tuition", "UGent (inschrijvingsgeld)")
    b.monthly(D(2026, 9, 1), TODAY, 3, 425, "other", "Overschrijving Ruben (kot Gent)")
    b.add(D(2026, 9, 12), 389, "furniture", "IKEA Gent (kot Ruben)")

    balance_today = calibrate_balance(b, 6000.0, fixed_band(3500, 9000, 6000), excess=SAVINGS)

    customer = Customer(
        id=9006, first_name="Els", last_name="De Wilde", birth_year=1978, city="Gent", language="nl",
        products=["current", "savings", "mortgage", "home_insurance", "family_insurance"], consent_personalization=True,
        ground_truth={
            "personas": ["young_family"],
            "events": [{"type": "goal:care_parent", "date": "2026-08-05"},
                       {"type": "goal:study_start", "date": "2026-09-25"}],
        },
    )
    return "els", customer, b.txs, balance_today


def _amir() -> tuple[str, Customer, list[Transaction], float]:
    """Demo persona: the newcomer (cold start). 34, moved to Antwerp in June 2026 for a job at the port, only
    four months of history. Lived in a furnished short-stay flat, then signed a lease: rent deposit, movers,
    a month with two rents and a new energy contract."""
    rng = random.Random(9007)
    start = D(2026, 6, 15)
    b = TxBuilder(9007, rng, start, TODAY)

    # savings brought from abroad, then the first salaries
    b.add_signed(D(2026, 6, 16), 7500.0, "other", "Wise (overschrijving eigen rekening)")
    b.monthly(D(2026, 7, 25), TODAY, 25, 3150, "salary", "Port of Antwerp-Bruges")
    b.add(D(2026, 6, 17), 950, "rent", "Short Stay Antwerp")
    b.monthly(D(2026, 7, 1), D(2026, 10, 1), 1, 950, "rent", "Short Stay Antwerp")
    living_costs(b, start, TODAY, scale=0.9, telecom=("Orange Belgium", 30.0, 30.0))
    b.add(D(2026, 6, 20), 249, "other", "Stad Antwerpen (verblijfskaart)")

    # ---- moving into a long-term flat in October
    b.add(D(2026, 9, 25), 2400, "rent", "Huurwaarborg Immo Schelde")
    b.add(D(2026, 10, 1), 800, "rent", "Immo Schelde")
    b.add(D(2026, 10, 3), 420, "other", "Verhuizingen Peeters")
    b.add(D(2026, 10, 6), 120, "utilities", "Engie (nieuw contract)")
    b.add(D(2026, 10, 8), 680, "furniture", "IKEA Wilrijk")

    balance_today = calibrate_balance(b, 0.0, fixed_band(800, 9000, 6000), excess=SAVINGS)

    customer = Customer(
        id=9007, first_name="Amir", last_name="Haddad", birth_year=1992, city="Antwerpen", language="nl",
        products=["current"], consent_personalization=True,
        ground_truth={
            "personas": ["young_professional"],
            "events": [{"type": "first_salary", "date": "2026-07-25", "employer": "Port of Antwerp-Bruges"},
                       {"type": "goal:move_house", "date": "2026-09-25"}],
        },
    )
    return "amir", customer, b.txs, balance_today


def _pieter() -> tuple[str, Customer, list[Transaction], float]:
    """Demo persona: the SME owner. 44, runs an engineering firm as a sole trader since 2019 with two employees
    (payroll through a social secretariat). Since May 2026 clients in Germany and the Netherlands pay him too."""
    rng = random.Random(9008)
    start = D(2019, 1, 1)
    b = TxBuilder(9008, rng, start, TODAY)

    be_clients = ["Vandewiele NV", "Barco NV", "Picanol Group", "Stad Kortrijk", "Deceuninck NV", "Bekaert"]
    freelance_income(b, start, TODAY, be_clients, lo=2500, hi=6500, per_month=3.0,
                     social_fund="Acerta", social_amount=4200)
    # ---- going international: German and Dutch clients from May 2026
    for d, amt, cp in [(D(2026, 5, 22), 4800, "Northwind GmbH (DE)"), (D(2026, 6, 26), 5200, "Kanaal BV (NL)"),
                       (D(2026, 7, 24), 4950, "Northwind GmbH (DE)"), (D(2026, 8, 28), 3900, "Kanaal BV (NL)"),
                       (D(2026, 9, 25), 6100, "Northwind GmbH (DE)"), (D(2026, 10, 15), 4400, "Kanaal BV (NL)")]:
        b.add(d, amt, "invoice_income", cp)

    # ---- two employees since 2022 and 2024: net pay plus the social secretariat
    b.monthly(D(2022, 3, 1), TODAY, 28, 2350, "other", "Loon Jens Vandenberghe")
    b.monthly(D(2024, 2, 1), TODAY, 28, 2200, "other", "Loon Sofie Desmet")
    b.monthly(D(2022, 3, 1), TODAY, 5, lambda d: 2650 if d < D(2024, 2, 1) else 5100, "other",
              "Securex (loonadministratie)")
    b.monthly(start, TODAY, 3, 140, "subscription", "Exact Online")

    # ---- private life on the same account
    b.monthly(start, TODAY, 5, 1350, "mortgage", "KBC Woningkrediet")
    b.yearly(start, TODAY, 1, 15, 420, "insurance_home", KBC_INSURANCE)
    b.yearly(start, TODAY, 1, 15, 112, "insurance_family", KBC_INSURANCE)
    b.monthly(start, TODAY, 8, 356, "child_benefit", CHILD_BENEFIT_PAYER)
    living_costs(b, start, TODAY, scale=1.6, subscription=("Netflix", 13.99, 17.99), increase_date=D(2026, 9, 14),
                 telecom=("Proximus", 95.0, 95.0))

    balance_today = calibrate_balance(b, 25000.0, fixed_band(22000, 40000, 30000), excess=SAVINGS)

    customer = Customer(
        id=9008, first_name="Pieter", last_name="Verhaeghe", birth_year=1982, city="Kortrijk", language="nl",
        products=["current", "savings", "mortgage", "home_insurance", "family_insurance", "business_account"],
        consent_personalization=True,
        ground_truth={
            "personas": ["freelancer", "young_family"],
            "events": [{"type": "goal:go_international", "date": "2026-05-22"}],
        },
    )
    return "pieter", customer, b.txs, balance_today


def _nina() -> tuple[str, Customer, list[Transaction], float]:
    """Demo persona: financially vulnerable. 29, a modest salary, rent, and since spring more and more
    buy-now-pay-later instalments; two direct debits bounced and a bailiff's letter had to be paid. KBC should
    help her back on track and keep every commercial goal (investing, travel, a house) quiet."""
    rng = random.Random(9009)
    start = D(2024, 1, 1)
    b = TxBuilder(9009, rng, start, TODAY)

    b.monthly(start, TODAY, 26, 1950, "salary", "Colruyt Group")
    b.yearly(start, TODAY, 12, 20, 1650, "salary", "Colruyt Group (eindejaarspremie)")
    b.monthly(start, TODAY, 2, 780, "rent", "Immo Limburg")
    living_costs(b, start, TODAY, scale=0.85, subscription=("Disney+", 8.99, 11.99), increase_date=D(2025, 11, 14),
                 telecom=("Telenet", 45.0, 45.0))

    # ---- BNPL creeping up since March 2026: 1 → 4 instalments a month
    for month, n in [(3, 1), (4, 1), (5, 2), (6, 2), (7, 3), (8, 3), (9, 4), (10, 3)]:
        for _ in range(n):
            d = D(2026, month, rng.randint(1, 18 if month == 10 else 28))
            b.add(d, rng.uniform(35, 120), "other", "Klarna")
    # ---- two bounced direct debits (the debit, then the reversal) and a bailiff
    for d in (D(2026, 9, 10), D(2026, 10, 12)):
        b.add_signed(d - dt.timedelta(days=2), -45.0, "telecom", "Telenet (domiciliëring)")
        b.add_signed(d, 45.0, "other", "Storno domiciliëring Telenet")
    b.add(D(2026, 10, 14), 285, "other", "Gerechtsdeurwaarder Maes & Partners")

    # no savings sweeps: whatever is left over goes on clothes and going out
    excess = [("leisure", "Zalando"), ("leisure", "Brasserie Lamot"), ("other", "Action")]
    balance_today = calibrate_balance(b, 1500.0, fixed_band(1500, 2300, 1900), excess=excess, min_factor=0.4)

    customer = Customer(
        id=9009, first_name="Nina", last_name="Jacobs", birth_year=1997, city="Hasselt", language="nl",
        products=["current"], consent_personalization=True,
        ground_truth={
            "personas": ["young_professional"],
            "events": [{"type": "goal:back_on_track", "date": "2026-10-14"}],
        },
    )
    return "nina", customer, b.txs, balance_today


FUTURE_END = D(2028, 12, 31)
RESERVE = "KBC Reservepot (btw en sociale bijdragen)"
RESERVE_BACK = "KBC Reservepot (naar zichtrekening)"


def _lotte_future() -> tuple[list[dict], list[Transaction]]:
    """Lotte's life timeline after TODAY (docs/ECOSYSTEM.md), as simulated, future-dated transactions.

    NOT part of demo_customers(): time travel is clamped to DEMO_TODAY and the balance walk-back starts from the
    last stored transaction, so storing these would change what the app shows today. Returns chapters
    [{"date", "id", "title", "goal", "txs"}] in date order; each chapter's txs are Transactions for customer 9001.
    The reserve rule is the go_freelance playbook's: the VAT share plus 25% of the rest of every invoice moves to a
    reserve pot, and the VAT returns, contributions and the regularisation bill are paid back out of it.
    """
    rng = random.Random(90011)
    b = TxBuilder(9001, rng, TODAY + dt.timedelta(days=1), FUTURE_END)
    vat_share, tax_share = 21 / 121, 0.25

    def invoice(d: dt.date, amount: float, client: str) -> None:
        b.add(d, amount, "invoice_income", client)
        b.add(d, round(amount * (vat_share + (1 - vat_share) * tax_share), 2), "savings_transfer", RESERVE)

    def from_reserve(d: dt.date, amount: float, category: str, counterparty: str) -> None:
        b.add_signed(d, round(amount, 2), "savings_transfer", RESERVE_BACK)
        b.add(d, amount, category, counterparty)

    chapters: list[dict] = []

    def chapter(cid: str, title: str, goal: str | None, lo: dt.date, hi: dt.date) -> None:
        chapters.append({"id": cid, "date": lo.isoformat(), "title": title, "goal": goal,
                         "txs": sorted(b.between(lo, hi), key=lambda t: (t.date, t.counterparty))})

    # ---- Nov 2026 → Jan 2027: Peppol invoices through Billit, the reserve fills, the first VAT return is paid from it
    b.monthly(D(2026, 11, 3), D(2028, 12, 31), 3, 19.0, "subscription", "Billit (Peppol e-facturatie)")
    for d, amt, cp in [(D(2026, 11, 16), 4598, "Bright Agency"), (D(2026, 12, 15), 4598, "Bright Agency"),
                       (D(2026, 12, 22), 2420, "Studio Nord"), (D(2027, 1, 15), 4598, "Bright Agency")]:
        invoice(d, amt, cp)
    from_reserve(D(2026, 12, 20), 890, "social_contribution", "Xerius (voorlopige bijdrage Q4 2026)")
    q4 = sum(t.amount for t in b.between(D(2026, 10, 1), D(2026, 12, 31), "invoice_income")) + 4598   # + 16 Oct
    from_reserve(D(2027, 1, 20), q4 * vat_share, "vat_payment", "FOD Financiën (btw Q4 2026)")
    chapter("first_vat", "First Peppol invoices and the first VAT return, paid from the reserve", "go_freelance",
            D(2026, 10, 21), D(2027, 1, 31))

    # ---- 2027: steady freelance year; quarterly VAT and contributions out of the reserve
    clients = ["Bright Agency", "Studio Nord", "Gemeente Herent"]
    d = D(2027, 2, 12)
    while d <= D(2027, 8, 31):
        invoice(d, rng.uniform(3800, 5600), rng.choice(clients))
        d += dt.timedelta(days=rng.randint(20, 30))
    # ---- late 2027: more work than one person can do (invoices double, subcontractors) → first_employee
    while d <= D(2027, 12, 31):
        invoice(d, rng.uniform(7000, 10500), rng.choice(clients + ["Sofico BV", "Vzw Kompas"]))
        d += dt.timedelta(days=rng.randint(12, 18))
    for sd in (D(2027, 9, 14), D(2027, 10, 12), D(2027, 11, 9), D(2027, 12, 7)):
        b.add(sd, rng.uniform(1400, 2200), "other", "Onderaanneming Pixelwerk")
    for q, due in [(1, D(2027, 4, 20)), (2, D(2027, 7, 20)), (3, D(2027, 10, 20)), (4, D(2028, 1, 20))]:
        lo = D(2027, 3 * q - 2, 1)
        hi = add_months(lo, 3) - dt.timedelta(days=1)
        vat = sum(t.amount for t in b.between(lo, hi, "invoice_income")) * vat_share
        from_reserve(due, vat, "vat_payment", f"FOD Financiën (btw Q{q} 2027)")
    for due in (D(2027, 3, 20), D(2027, 6, 20), D(2027, 9, 20), D(2027, 12, 20)):
        from_reserve(due, 890, "social_contribution", "Xerius (voorlopige bijdrage)")

    # ---- summer 2027: a work trip abroad
    b.add(D(2027, 6, 10), 620, "leisure", "Brussels Airlines")
    b.add(D(2027, 6, 30), 19, "telecom", "Firsty (travel eSIM)")
    b.add(D(2027, 7, 2), 12, "transport", "Brussels Airport (Fast Lane)")
    b.add(D(2027, 6, 11), 34, "insurance_family", "KBC Verzekeringen (reisverzekering)")
    chapter("trip", "A work trip abroad: eSIM, travel insurance, Fast Lane", "travel", D(2027, 6, 1), D(2027, 7, 31))
    chapter("first_employee", "More work than one person: the engine proposes a first employee", "first_employee",
            D(2027, 9, 1), D(2027, 12, 31))

    # ---- 2028: the regularisation of 2027's social contributions arrives, already covered by the reserve
    invoices_2027 = sum(t.amount for t in b.between(D(2027, 1, 1), D(2027, 12, 31), "invoice_income"))
    net_taxable = invoices_2027 * (1 - vat_share) * 0.8                      # context.COST_RATIO = 0.20
    regularisation = max(0.0, net_taxable * 0.205 - 4 * 890)                 # context.SOCIAL_RATE, provisional paid
    from_reserve(D(2028, 11, 15), regularisation, "social_contribution", "Xerius (regularisatie 2027)")
    chapter("regularisation", "The regularisation bill arrives and is already covered by the reserve", "go_freelance",
            D(2028, 11, 1), D(2028, 11, 30))
    return chapters, sorted(b.txs, key=lambda t: (t.date, t.counterparty))


def lotte_future_chapters() -> list[dict]:
    """The chapters of `_lotte_future` (see there): [{"id", "date", "title", "goal", "txs"}]."""
    return _lotte_future()[0]


def lotte_future_transactions() -> list[Transaction]:
    """Every simulated transaction of Lotte after TODAY up to FUTURE_END, chapters and the months between them."""
    return _lotte_future()[1]


def demo_customers() -> list[tuple[str, Customer, list[Transaction], float]]:
    """Returns [(username, customer, transactions, balance_today), ...]."""
    return [_lotte(), _sara(), _jan(), _marc(), _tom(), _els(), _amir(), _pieter(), _nina()]
