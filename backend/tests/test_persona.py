from __future__ import annotations

import datetime as dt

from app.engine.features import compute_features
from app.engine.persona import dominant, infer_persona_mix
from tests.test_features import END, TxBuilder, baseline, customer

D = dt.date


def lotte_history() -> tuple:
    """Student 2018 → first job 2021 → mortgage 2022 → baby 2024 → freelance 2026."""
    b = TxBuilder()
    baseline(b, D(2018, 9, 1), END)
    # student years
    b.monthly(D(2018, 9, 1), D(2021, 6, 30), 350, "allowance_from_parents", "Mama & Papa", day=1)
    b.monthly(D(2018, 9, 1), D(2021, 6, 30), 280, "student_income", "Randstad Student", day=20)
    b.yearly(D(2018, 9, 25), D(2020, 9, 25), -980, "tuition", "KU Leuven")
    b.monthly(D(2018, 9, 1), D(2021, 6, 30), -380, "rent", "Kot Naamsestraat", day=1)
    # first job
    b.monthly(D(2021, 7, 1), D(2025, 12, 31), 2400, "salary", "Acme NV", day=25)
    b.monthly(D(2021, 7, 1), D(2022, 3, 31), -750, "rent", "Immo Leuven", day=1)
    # mortgage
    b.add(D(2022, 3, 15), -6200, "notary", "Notaris Claes")
    b.monthly(D(2022, 4, 1), END, -1050, "mortgage", "KBC Woningkrediet", day=5)
    # baby
    b.add(D(2024, 2, 10), -240, "baby", "Dreambaby")
    b.monthly(D(2024, 3, 1), END, 175, "child_benefit", "Groeipakket", day=8)
    b.monthly(D(2024, 6, 1), END, -560, "childcare", "Kinderdagverblijf De Bijtjes", day=2)
    # freelance
    for i, (m, d, amt, cp) in enumerate([(1, 12, 2800, "Client A"), (2, 3, 1900, "Client B"), (2, 27, 3100, "Client C"),
                                         (3, 18, 2200, "Client A"), (4, 9, 2600, "Client D"), (5, 14, 3300, "Client B"),
                                         (6, 2, 1800, "Client C"), (7, 7, 2900, "Client A"), (8, 21, 2500, "Client D"),
                                         (9, 12, 3200, "Client B")]):
        b.add(D(2026, m, d), amt, "invoice_income", cp)
    b.add(D(2026, 4, 18), -1610, "vat_payment", "FOD Financiën")
    b.add(D(2026, 7, 18), -1720, "vat_payment", "FOD Financiën")
    b.add(D(2026, 4, 2), -880, "social_contribution", "Xerius")
    b.add(D(2026, 7, 2), -880, "social_contribution", "Xerius")
    return customer(birth_year=1999), b.txs


def mix_at(c, txs, as_of):
    return infer_persona_mix(compute_features(c, txs, 2500.0, as_of))


def test_lotte_changes_persona_over_time():
    c, txs = lotte_history()
    assert dominant(mix_at(c, txs, D(2019, 11, 15))) == "student"
    assert dominant(mix_at(c, txs, D(2022, 1, 15))) == "young_professional"
    assert dominant(mix_at(c, txs, D(2025, 3, 15))) == "young_family"
    late = mix_at(c, txs, END)
    assert dominant(late) == "freelancer"
    assert {pw.persona for pw in late} == {"freelancer", "young_family"}


def test_blend_has_two_weights_summing_to_one():
    c, txs = lotte_history()
    mix = mix_at(c, txs, END)
    assert len(mix) == 2
    assert abs(sum(pw.weight for pw in mix) - 1.0) < 1e-6
    assert all(pw.weight >= 0.15 for pw in mix)
    assert mix == sorted(mix, key=lambda pw: -pw.weight)
    assert any("clients" in e for e in mix[0].evidence)


def test_retiree():
    b = TxBuilder()
    baseline(b, D(2025, 1, 1), END)
    b.monthly(D(2025, 1, 1), END, 1850, "pension", "Federale Pensioendienst", day=3)
    mix = infer_persona_mix(compute_features(customer(birth_year=1955), b.txs, 14000.0, END))
    assert dominant(mix) == "retiree" and mix[0].weight == 1.0


def test_fallback_when_no_signals():
    b = TxBuilder()
    baseline(b, D(2026, 8, 1), END)
    mix = infer_persona_mix(compute_features(customer(birth_year=1990), b.txs, 500.0, END))
    assert dominant(mix) == "young_professional" and mix[0].weight == 1.0


def test_freelancer_weight_scales_with_invoice_share():
    def mix_for(invoice_eur):
        b = TxBuilder()
        baseline(b, D(2024, 1, 1), END)
        b.monthly(D(2024, 3, 1), END, 175, "child_benefit", "Groeipakket", day=8)
        b.monthly(D(2024, 6, 1), END, -540, "childcare", "Kinderdagverblijf", day=2)
        for m in range(1, 10):
            b.add(D(2026, m, 10), invoice_eur, "invoice_income", f"Client {m % 3}")
            b.add(D(2024, m, 10), invoice_eur, "invoice_income", f"Client {m % 3}")
        b.add(D(2026, 7, 18), -900, "vat_payment", "FOD Financiën")
        return {pw.persona: pw.weight for pw in infer_persona_mix(compute_features(customer(), b.txs, 3000.0, END))}
    small, big = mix_for(600), mix_for(3500)
    assert small["young_family"] > small["freelancer"]
    assert big["freelancer"] > big["young_family"]
    assert 0.55 <= big["freelancer"] <= 0.7
