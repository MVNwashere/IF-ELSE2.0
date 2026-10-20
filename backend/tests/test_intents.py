"""Round 2 signals and intents: freelance deadlines and forecasts, new life-event detectors, playbooks, evaluation."""
from __future__ import annotations

import datetime as dt

import pytest

from app.ecosystem.context import build_context
from app.ecosystem.intent import DETECTORS, detect
from app.ecosystem.registry import registry
from app.ecosystem.signals import forecasts, upcoming_deadlines
from app.schemas import Customer, Transaction
from scripts.evaluate_intents import evaluate
from synth.demo_customers import demo_customers

D = dt.date
TODAY = D(2026, 10, 20)


@pytest.fixture(scope="module")
def demo():
    out = {}
    for username, customer, txs, balance in demo_customers():
        txs = sorted(txs, key=lambda t: (t.date, t.counterparty))
        for i, t in enumerate(txs):
            t.id = i + 1
        out[username] = (customer, txs, balance)
    return out


def _ctx(demo, username, as_of=TODAY):
    customer, txs, balance = demo[username]
    return build_context(customer, txs, balance, as_of)


# ---- Lotte, freelance since October 2026 -----------------------------------------------------------------------------


def test_lotte_forecasts_the_regularisation_gap(demo):
    fc = {f.kind: f for f in forecasts(_ctx(demo, "lotte"))}
    reg = fc["social_contribution_regularisation"]
    assert reg.amount_eur > 2000 and reg.due == D(2028, 10, 15) and reg.playbook_id == "go_freelance"
    assert any("20.5%" in e for e in reg.evidence)
    conc = fc["client_concentration"]
    assert "Bright Agency" in conc.evidence[0] and conc.title.startswith("100%")
    priv = fc["private_business_expenses"]
    assert priv.amount_eur == 1499 and "Coolblue" in priv.evidence[0]


def test_lotte_deadlines(demo):
    ctx = _ctx(demo, "lotte")
    assert upcoming_deadlines(ctx) == []          # nothing due in the next 45 days
    ds = upcoming_deadlines(ctx, 100)
    assert [(d.kind, d.date) for d in ds] == [("advance_tax", D(2026, 12, 20)),
                                               ("social_contribution", D(2026, 12, 31)),
                                               ("vat_return", D(2027, 1, 20))]
    vat = ds[-1]
    assert vat.amount_eur == round(4598 * 0.21, 2) and vat.playbook_id == "go_freelance"
    assert all(d.evidence for d in ds)


def test_lotte_go_freelance_evidence_and_filled_results(demo):
    ctx = _ctx(demo, "lotte")
    goals = dict(detect(ctx))
    score, ev, _ = goals["go_freelance"]
    assert score >= 0.8
    assert ev[0] == "Your salary from Cronos Groep stopped after 1 Oct 2026"
    assert any("enterprise counter on 2 Oct 2026" in e for e in ev)
    pb = registry().playbooks["go_freelance"]
    assert pb.next_goal == "first_employee"
    for step in pb.steps:
        assert "…" not in ctx.fill(step.result), step.id
    assert ctx.vars["regularisation_due"] == "Oct 2028" and ctx.vars["kbo_date"] == "2 Oct 2026"


def test_before_the_first_invoice_there_is_nothing_to_forecast(demo):
    ctx = _ctx(demo, "lotte", D(2026, 10, 10))
    assert forecasts(ctx) == [] and not [d for d in upcoming_deadlines(ctx, 120) if d.kind == "vat_return"]


# ---- Sara: Q3 VAT return due today ---------------------------------------------------------------------------------


def test_sara_vat_due_today_and_car_insurance(demo):
    ds = upcoming_deadlines(_ctx(demo, "sara"))
    vat = ds[0]
    assert (vat.kind, vat.date, vat.title) == ("vat_return", TODAY, "Q3 2026 VAT return")
    assert vat.amount_eur > 0 and vat.shortfall_eur is not None
    car = next(d for d in ds if d.kind == "insurance_renewal")
    assert car.date == D(2026, 11, 1) and car.amount_eur == 612 and car.playbook_id == "mobility"
    assert ds == sorted(ds, key=lambda d: (d.date, d.kind))
    # an established freelancer: no starter regularisation forecast
    assert "social_contribution_regularisation" not in {f.kind for f in forecasts(_ctx(demo, "sara"))}


def test_pension_savings_reminder_only_in_season(demo):
    nov = [d for d in upcoming_deadlines(_ctx(demo, "marc", D(2026, 11, 20)), 45) if d.kind == "pension_savings"]
    assert not [d for d in upcoming_deadlines(_ctx(demo, "marc"), 90) if d.kind == "pension_savings"]
    if nov:
        assert nov[0].date == D(2026, 12, 31) and nov[0].playbook_id == "retire_well"


# ---- new detectors on hand-made histories ---------------------------------------------------------------------------


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


def _goals(rows, age=40, products=("current",)):
    return dict(detect(build_context(_customer(age, products), _txs(rows), 3000.0, TODAY)))


def test_job_change_new_employer_and_job_loss():
    old = _monthly(D(2025, 9, 1), D(2026, 6, 30), 27, 2600.0, "salary", "Barco")
    new = _monthly(D(2026, 7, 15), TODAY, 27, 2800.0, "salary", "Umicore")
    hit = _goals(old + new)["job_change"]
    assert "Umicore" in hit[1][1]
    loss = _goals(old + _monthly(D(2026, 8, 1), TODAY, 15, 1400.0, "benefit", "HVW (werkloosheidsuitkering)"))
    assert any("HVW" in e for e in loss["job_change"][1])
    # salary replaced by invoices is go_freelance, not a job loss
    freelance = _goals(old + [(D(2026, 8, 20), 4000.0, "invoice_income", "Studio Nord")])
    assert "job_change" not in freelance and "go_freelance" in freelance
    assert "job_change" not in _goals(old + _monthly(D(2026, 7, 1), TODAY, 27, 2600.0, "salary", "Barco"))


def test_mobility_from_rising_garage_bills():
    bills = [(D(2026, 1, 10), -420.0, "transport", "Garage De Smet"), (D(2026, 5, 3), -780.0, "transport", "Garage De Smet"),
             (D(2026, 9, 1), -1350.0, "transport", "Garage De Smet")]
    hit = _goals(bills)["mobility"]
    assert hit[0] >= 0.6 and "3 garage bills" in hit[1][0]
    assert "mobility" not in _goals(bills[:1])
    assert "mobility" not in _goals([(D(2026, 9, 1), -180.0, "other", "Garage Vermeersch")] * 3)


def test_first_employee_from_growth_and_subcontractors():
    before = [(D(2026, 3, d), 1500.0, "invoice_income", c) for d, c in ((5, "A"), (20, "B"))] + \
             [(D(2026, 5, d), 1500.0, "invoice_income", c) for d, c in ((5, "A"), (20, "B"))]
    after = [(D(2026, m, d), 3800.0, "invoice_income", c) for m in (7, 8, 9, 10) for d, c in ((3, "A"), (17, "C"))]
    subs = [(D(2026, 8, 30), -1200.0, "other", "Onderaanneming Maes BV"),
            (D(2026, 9, 30), -1400.0, "other", "Onderaanneming Maes BV")]
    hit = _goals(before + after + subs)["first_employee"]
    assert any("subcontractors" in e for e in hit[1])
    assert "first_employee" not in _goals(before + after[:2])


def test_inheritance_and_study_start():
    inh = _goals([(D(2026, 9, 2), 64000.0, "other", "Notaris Wouters (nalatenschap)")])
    assert "inheritance" in inh
    assert "inheritance" not in _goals([(D(2026, 9, 2), 15000.0, "property", "Notaris Wouters (derdenrekening)")])
    fee = [(D(2026, 9, 25), -1092.10, "tuition", "KU Leuven (inschrijvingsgeld)")]
    assert "study_start" in _goals(fee, age=49)
    assert "study_start" not in _goals(fee, age=20)   # a student paying their own fee


# ---- configuration and evaluation -----------------------------------------------------------------------------------


def test_every_detector_has_a_valid_playbook():
    reg = registry()
    assert set(DETECTORS) <= set(reg.playbooks)
    for pid in ("mobility", "first_employee", "inheritance", "study_start", "job_change"):
        assert reg.playbooks[pid].steps
    assert {s.provider for s in reg.playbooks["mobility"].steps} >= {"movesmart", "cambio", "vab"}
    assert "nowjobs" in {s.provider for s in reg.playbooks["first_employee"].steps}


def test_intent_evaluation_smoke():
    r = evaluate(n=60, seed=42)
    assert r["customers"] == 64 and set(r["goals"]) == set(DETECTORS)
    for pid, g in r["goals"].items():
        if g["precision"] is not None and g["detected"] >= 3:
            assert g["precision"] >= 0.7, pid
