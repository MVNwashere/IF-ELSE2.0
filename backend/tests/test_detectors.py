"""Life-event and business detectors: each fires on its pattern and not on its near miss;
suppression in hard times; tightened existing detectors; new signals; cold start."""
from __future__ import annotations

import datetime as dt

from app.ecosystem.context import build_context
from app.ecosystem.intent import detect, detect_with_suppressed
from app.ecosystem.signals import forecasts, upcoming_deadlines
from app.schemas import Customer, Transaction

D = dt.date
TODAY = D(2026, 10, 20)


def _customer(age=40, products=("current",)):
    return Customer(id=1, first_name="Test", last_name="Klant", birth_year=TODAY.year - age, city="Gent", language="nl",
                    products=list(products), consent_personalization=True, ground_truth={})


def _txs(rows):
    return [Transaction(id=i + 1, customer_id=1, date=d, amount=a, category=c, counterparty=cp)
            for i, (d, a, c, cp) in enumerate(sorted(rows))]


def _monthly(start, end, day, amount, cat, cp):
    out, d = [], start.replace(day=day)
    while d <= end:
        out.append((d, amount, cat, cp))
        d = (d.replace(day=1) + dt.timedelta(days=32)).replace(day=day)
    return out


def _ctx(rows, age=40, products=("current",), balance=3000.0):
    return build_context(_customer(age, products), _txs(rows), balance, TODAY)


def _goals(rows, age=40, products=("current",), balance=3000.0):
    return dict(detect(_ctx(rows, age, products, balance)))


def _life(start=D(2025, 10, 1), salary=3000.0, rent=None):
    rows = _monthly(start, TODAY, 27, salary, "salary", "Barco") + \
        _monthly(start, TODAY, 5, -900.0, "groceries", "Colruyt")
    if rent:
        rows += _monthly(start, TODAY, 1, -rent, "rent", "Dhr. Vermeulen (huur)")
    return rows


# ---- new detectors -----------------------------------------------------------------------------------------------------


def test_side_job_needs_paperwork_and_a_salary_that_continues():
    invoices = [(D(2026, 7, 15), 800.0, "invoice_income", "Studio Nord"),
                (D(2026, 9, 10), 650.0, "invoice_income", "Vzw Kompas")]
    kbo = [(D(2026, 6, 20), -105.5, "other", "Ondernemingsloket Xerius (inschrijving KBO)")]
    social = [(D(2026, 7, 1), -180.0, "social_contribution", "Xerius (bijberoep)")]
    g = _goals(_life() + invoices + kbo + social)
    assert "side_job" in g and "go_freelance" not in g
    assert g["side_job"][0] >= 0.8 and any("bijberoep" not in e and "side business" in e for e in g["side_job"][1])
    # near miss: one invoice next to the salary, no registration → nothing at all
    g = _goals(_life() + invoices[:1])
    assert "side_job" not in g and "go_freelance" not in g
    # near miss: selling stuff online
    assert "side_job" not in _goals(_life() + [(D(2026, 9, 3), 140.0, "other", "Vinted uitbetaling")])


def test_go_international_from_country_tagged_clients():
    rows = [(D(2026, 5, 3), 3000.0, "invoice_income", "Studio Nord"),
            (D(2026, 8, 5), 4200.0, "invoice_income", "Northwind GmbH (DE)"),
            (D(2026, 9, 20), 3900.0, "invoice_income", "Kanaal BV (NL)")]
    g = _goals(rows)["go_international"]
    assert g[0] >= 0.8 and "DE, NL" in g[1][0]
    refund = [(D(2026, 9, 1), 89.0, "other", "Zalando SE (DE) terugbetaling")]
    assert "go_international" not in _goals(rows[:1] + refund)


def test_care_parent_from_care_home_payments():
    care = _monthly(D(2026, 8, 1), TODAY, 1, -1850.0, "healthcare", "WZC Hof ter Linde (woonzorgcentrum)")
    g = _goals(_life() + care, age=48)["care_parent"]
    assert g[0] >= 0.8 and "WZC Hof ter Linde" in g[1][0]
    assert "care_parent" not in _goals(_life() + care, age=30)
    assert "care_parent" not in _goals(_life() + [(D(2026, 9, 9), -640.0, "healthcare", "AZ Groeninge (ziekenhuisfactuur)")],
                                       age=48)


def test_move_house_but_not_rent_indexation():
    old = _monthly(D(2025, 10, 1), D(2026, 10, 1), 1, -850.0, "rent", "Dhr. Vermeulen (huur)")
    new = [(D(2026, 10, 1), -980.0, "rent", "Mevr. Claes (huur)"),
           (D(2026, 9, 15), -1960.0, "rent", "Huurwaarborg Mevr. Claes"),
           (D(2026, 10, 3), -650.0, "other", "Verhuisfirma De Kat"),
           (D(2026, 10, 4), -120.0, "utilities", "Engie (nieuw contract)")]
    g = _goals(_life() + old + new)["move_house"]
    assert g[0] >= 0.9 and any("Two rents in October 2026" in e for e in g[1])
    indexed = _monthly(D(2025, 10, 1), D(2026, 6, 1), 1, -850.0, "rent", "Dhr. Vermeulen (huur)") + \
        _monthly(D(2026, 7, 1), TODAY, 1, -872.0, "rent", "Dhr. Vermeulen (huur)")
    assert "move_house" not in _goals(_life() + indexed)


def test_sell_business_needs_a_transfer_adviser():
    inv = [(D(y, m, 10), 6000.0, "invoice_income", "Bakkerij Peeters") for y in range(2019, 2027) for m in (2, 5, 8)]
    adviser = [(D(2026, 9, 14), -2400.0, "other", "Bedrijfsrevisor Vandamme (waardering)")]
    g = _goals(inv + adviser, age=61)["sell_business"]
    assert any("Bedrijfsrevisor Vandamme" in e for e in g[1])
    assert "sell_business" not in _goals(inv + [(D(2026, 9, 14), -400.0, "other", "Boekhouder Peeters")], age=61)
    assert "sell_business" not in _goals(inv + adviser, age=45)


def test_back_on_track_and_suppression():
    bnpl = [(D(2026, m, d), -60.0, "other", "Klarna") for m, d in ((8, 2), (8, 28), (9, 12), (9, 30), (10, 14))]
    failed = [(D(2026, 9, 5), 52.0, "other", "Storno domiciliëring Proximus"),
              (D(2026, 10, 5), 89.0, "other", "Storno domiciliëring Engie")]
    bailiff = [(D(2026, 10, 8), -310.0, "other", "Gerechtsdeurwaarder Maes")]
    trip = [(D(2026, 10, 10), -640.0, "leisure", "Ryanair")]
    ctx = _ctx(_life() + bnpl + failed + bailiff + trip, age=29, balance=-120.0)
    kept, suppressed = detect_with_suppressed(ctx)
    kept = dict(kept)
    assert kept["back_on_track"][0] >= 0.9 and "travel" not in kept
    assert [p for p, _ in suppressed] == ["travel"] and "money trouble" in suppressed[0][1]
    assert "travel" in _goals(_life() + trip, age=29)   # without the trouble, the trip is proposed
    assert "back_on_track" not in _goals(_life() + bnpl[:1], age=29)


def test_job_loss_suppresses_commercial_goals():
    old = _monthly(D(2025, 9, 1), D(2026, 7, 31), 27, 2600.0, "salary", "Barco")
    trip = [(D(2026, 10, 10), -900.0, "leisure", "TUI")]
    kept, suppressed = detect_with_suppressed(_ctx(old + trip))
    assert "job_change" in dict(kept) and ("travel", ) == tuple(p for p, _ in suppressed)


def test_farm_growth_but_not_a_garden_purchase():
    rows = [(D(2026, m, 12), 5200.0, "invoice_income", "BelOrta (veiling)") for m in (5, 6, 7, 8, 9)] + \
           [(D(2026, m, 3), -900.0, "other", "Aveve") for m in (3, 5, 7, 9)] + \
           [(D(2026, 1, 15), -240.0, "other", "Boerenbond (lidgeld)"), (D(2026, 9, 20), -18000.0, "other", "Agrofront")]
    g = _goals(rows, age=45)["farm_growth"]
    assert g[0] >= 0.8 and any("investment" in e for e in g[1])
    assert "farm_growth" not in _goals(_life() + [(D(2026, 5, 2), -45.0, "other", "Aveve")])


def test_ev_switch_from_new_charging_not_a_holiday_charge():
    charging = [(D(2026, m, d), -24.0, "transport", cp)
                for m, d, cp in ((8, 4, "Allego"), (8, 30, "Shell Recharge"), (9, 18, "Allego"), (10, 9, "Fastned"))]
    g = _goals(_life() + charging)["ev_switch"]
    assert g[0] >= 0.6 and "Allego" in g[1][0]
    assert "ev_switch" not in _goals(_life() + [(D(2026, 8, 4), -31.0, "transport", "Ionity")])


def test_first_investment_but_not_when_house_hunting():
    saving = _monthly(D(2025, 10, 1), TODAY, 2, -900.0, "savings_transfer", "KBC Spaarrekening")
    bonus = [(D(2026, 7, 30), 2800.0, "salary", "Barco (eindejaarspremie)")]
    g = _goals(_life() + saving + bonus, age=29, balance=6000.0)
    assert "first_investment" in g and any("bonus" in e for e in g["first_investment"][1])
    search = [(D(2026, m, 1), -9.0, "property", "Immoweb (zoekertje)") for m in (7, 8, 9, 10)]
    assert "first_investment" not in _goals(_life() + saving + bonus + search, age=29, balance=6000.0)
    assert "first_investment" not in _goals(_life() + saving + bonus, age=29, balance=6000.0,
                                            products=("current", "investment_plan"))


def test_together_and_a_jewellery_present():
    chip = _monthly(D(2026, 8, 1), TODAY, 1, 450.0, "other", "Sam Peeters (bijdrage huur)")
    g = _goals(_life(rent=950.0) + chip, age=28)["together"]
    assert g[0] >= 0.6 and "Sam Peeters" in g[1][0]
    wedding = [(D(2026, 6, 1), -2500.0, "other", "Trouwzaal De Hoeve"), (D(2026, 9, 12), -150.0, "other", "Gemeente Gent (huwelijk)")]
    assert "together" in _goals(_life() + wedding, age=31)
    assert "together" not in _goals(_life() + [(D(2025, 12, 18), -650.0, "other", "Juwelier Slaets")], age=31)


def test_separation_but_not_a_traffic_lawyer():
    mortgage = _monthly(D(2025, 10, 1), TODAY, 1, -1100.0, "mortgage", "KBC Woonkrediet")
    rows = _life() + mortgage + [(D(2026, 9, 2), -1500.0, "other", "Advocaat Janssens (echtscheiding)")] + \
        _monthly(D(2026, 8, 1), TODAY, 1, -780.0, "rent", "Mevr. Wouters (huur)")
    g = _goals(rows, age=42, products=("current", "mortgage"))["separation"]
    assert g[0] >= 0.7
    near = _life() + mortgage + [(D(2026, 9, 2), -400.0, "other", "Advocaat Janssens (verkeersboete)")]
    assert "separation" not in _goals(near, age=42, products=("current", "mortgage"))


# ---- tightened existing detectors ----------------------------------------------------------------------------------


def test_salary_pause_that_resumes_is_no_goal():
    rows = _monthly(D(2025, 10, 1), D(2026, 5, 31), 27, 2800.0, "salary", "Barco") + \
        _monthly(D(2026, 9, 1), TODAY, 27, 2800.0, "salary", "Barco")   # unpaid leave in summer, then back
    g = _goals(rows)
    assert "job_change" not in g and "go_freelance" not in g


def test_property_sale_is_not_an_inheritance():
    assert "inheritance" not in _goals([(D(2026, 9, 2), 240000.0, "other", "Notaris Wouters (verkoop woning)")])


def test_landlord_browsing_immoweb_is_not_buying_a_home():
    search = [(D(2026, m, 1), -9.0, "property", "Immoweb (zoekertje)") for m in (7, 8, 9, 10)]
    income = _monthly(D(2025, 10, 1), TODAY, 3, 850.0, "rent", "Huurder Jacobs (huur)")
    assert "buy_home" in _goals(_life(rent=900.0) + search, age=32)
    assert "buy_home" not in _goals(_life(rent=900.0) + search + income, age=32)


def test_abandoned_house_hunt_asks_once_at_low_confidence():
    old_search = [(D(2026, m, 1), -9.0, "property", "Immoweb (zoekertje)") for m in (4, 5, 6)]
    conf, ev, why = _goals(_life(rent=900.0) + old_search, age=32)["buy_home"]
    assert conf == 0.5 and why.startswith("Still looking") and any("stopped" in e for e in ev)


def test_insured_accident_is_not_an_ageing_car():
    bills = [(D(2026, 3, 10), -900.0, "transport", "Carrosserie Mertens"),
             (D(2026, 8, 20), -1600.0, "transport", "Carrosserie Mertens")]
    refunds = [(D(2026, 4, 2), 900.0, "insurance_car", "KBC Verzekeringen (schadevergoeding)"),
               (D(2026, 9, 10), 1600.0, "insurance_car", "KBC Verzekeringen (schadevergoeding)")]
    assert "mobility" in _goals(bills)
    assert "mobility" not in _goals(bills + refunds)


def test_refunded_flight_is_not_a_trip():
    trip = [(D(2026, 10, 1), -480.0, "leisure", "Ryanair")]
    assert "travel" in _goals(trip)
    assert "travel" not in _goals(trip + [(D(2026, 10, 6), 480.0, "other", "Ryanair (terugbetaling)")])


def test_cold_start_newcomer_with_four_months_of_data():
    start = D(2026, 6, 20)
    rows = [(start, -1900.0, "rent", "Huurwaarborg Dhr. Lambert")] + \
        _monthly(D(2026, 7, 1), TODAY, 1, -950.0, "rent", "Dhr. Lambert (huur)") + \
        _monthly(D(2026, 7, 1), TODAY, 27, 3100.0, "salary", "Barco") + \
        _monthly(D(2026, 7, 1), TODAY, 5, -700.0, "groceries", "Colruyt")
    g = _goals(rows, age=34, balance=1500.0)
    assert len(g) <= 2, g.keys()


# ---- new signals ---------------------------------------------------------------------------------------------------


def test_new_forecasts_and_bnpl_calendar():
    care = _monthly(D(2026, 8, 1), TODAY, 1, -1850.0, "healthcare", "WZC Hof ter Linde (woonzorgcentrum)")
    old = _monthly(D(2025, 10, 1), D(2026, 9, 1), 1, -850.0, "rent", "Dhr. Vermeulen (huur)")
    move = [(D(2026, 9, 15), -1960.0, "rent", "Huurwaarborg Mevr. Claes"), (D(2026, 10, 1), -980.0, "rent", "Mevr. Claes (huur)")]
    eu = [(D(2026, 8, 5), 4200.0, "invoice_income", "Northwind GmbH (DE)")]
    fc = {f.kind: f for f in forecasts(_ctx(_life() + care + old + move + eu, age=48))}
    assert fc["care_cost"].playbook_id == "care_parent" and 20000 < fc["care_cost"].amount_eur < 25000
    dep = fc["rent_deposit_return"]
    assert dep.amount_eur == 1700.0 and dep.playbook_id == "move_house" and dep.illustrative
    assert fc["reverse_charge"].playbook_id == "go_international" and "verify" in fc["reverse_charge"].evidence[1]
    bnpl = [(D(2026, m, 14), -60.0, "other", "Klarna") for m in (7, 8, 9, 10)]
    ds = [d for d in upcoming_deadlines(_ctx(_life() + bnpl), 45) if d.kind == "bnpl_instalment"]
    assert ds and ds[0].playbook_id == "back_on_track" and D(2026, 11, 5) <= ds[0].date <= D(2026, 11, 20)


def test_first_investment_waits_while_a_business_starts():
    saving = _monthly(D(2025, 10, 1), TODAY, 2, -900.0, "savings_transfer", "KBC Spaarrekening")
    bonus = [(D(2025, 12, 20), 2800.0, "salary", "Barco (eindejaarspremie)")]
    side = [(D(2026, 7, 15), 800.0, "invoice_income", "Studio Nord"),
            (D(2026, 6, 20), -105.5, "other", "Ondernemingsloket Xerius (inschrijving KBO)")]
    kept, suppressed = detect_with_suppressed(_ctx(_life() + saving + bonus + side, age=29, balance=6000.0))
    assert "side_job" in dict(kept) and ("first_investment", ) == tuple(p for p, _ in suppressed)
