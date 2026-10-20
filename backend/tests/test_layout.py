import datetime as dt

import pytest

from app.engine import layout
from app.schemas import (
    Card,
    Customer,
    Features,
    HERO_COMPONENTS,
    Layout,
    DeclaredSignalRow,
    LayoutPrefRow,
    LifeEvent,
    PersonaWeight,
    Prefs,
    RecurringPayment,
    StylePrefs,
    SuggestionDismissal,
    Transaction,
)

AS_OF = dt.date(2026, 9, 30)

REQUIRED_PROPS = {
    "BalanceHero": {"balance_eur", "monthly_income_eur", "monthly_spend_eur", "trend_30d_eur", "sparkline"},
    "RunwayHero": {"balance_eur", "runway_days", "next_income_date", "next_income_eur", "daily_budget_eur"},
    "FamilyBudgetHero": {"month_label", "month_income_eur", "month_spent_eur", "month_budget_eur",
                         "child_benefit_eur", "childcare_eur", "top_categories"},
    "TaxReserveHero": {"quarter_label", "quarter_income_eur", "reserve_eur", "reserve_pct", "vat_due_date", "days_to_due"},
    "PensionHero": {"balance_eur", "pension_eur", "pension_received_date", "next_pension_date",
                    "upcoming_bills_eur", "upcoming_bills_count"},
    "ForYouFeed": set(),
    "QuickActions": {"actions"},
    "UpcomingBills": {"bills", "total_eur"},
    "SplitBills": {"recent", "hint"},
    "InvoiceTracker": {"unpaid", "unpaid_eur", "paid_quarter_eur", "clients"},
    "SavingsGoal": {"goal_label", "saved_eur", "target_eur", "monthly_eur"},
    "ScamShield": {"tips", "hotline"},
    "AdvisorContact": {"advisor_name", "reason", "slots"},
    "SpendingByCategory": {"month_label", "total_eur", "categories"},
    "KateTile": {"prompt", "card_key", "quick_replies"},
    "SubscriptionsTile": {"monthly_total_eur", "count", "items"},
}


def customer(age=30, products=("current",)):
    return Customer(id=1, first_name="Test", last_name="Person", birth_year=AS_OF.year - age, city="Leuven",
                    products=list(products))


def features(age=30, **kw) -> Features:
    base = dict(
        as_of=AS_OF, age=age, balance_eur=1500.0, monthly_income_avg_90d=2500.0, income_regularity=0.05,
        income_sources_180d=1, monthly_spend_avg_90d=2000.0,
        spend_by_category_30d={"groceries": 400, "rent": 800, "leisure": 150, "transport": 60, "telecom": 30,
                               "utilities": 120, "other": 20},
    )
    base.update(kw)
    return Features(**base)


def mix(**weights) -> list[PersonaWeight]:
    return [PersonaWeight(persona=p, weight=w, evidence=["e"]) for p, w in weights.items()]


def txs(rows):
    return [Transaction(id=i, customer_id=1, date=d, amount=a, category=c, counterparty=cp)
            for i, (d, a, c, cp) in enumerate(rows, 1)]


def plan(f, m, prefs=None, t=None, cards=None, cust=None):
    return layout.plan_layout(f, m, prefs or Prefs(), cust or customer(f.age), t or [], AS_OF, cards or [])


def _components(lay: Layout):
    return [s.component for s in lay.sections]


# ------------------------------------------------------------------------------


def test_student_gets_runway_hero_compact_casual():
    f = features(age=21, balance_eur=212, monthly_income_avg_90d=600, monthly_spend_avg_90d=650,
                 has_student_signals=True, runway_days=40,
                 next_income_date=AS_OF + dt.timedelta(days=9), next_income_eur=300)
    lay = plan(f, mix(student=0.85, young_professional=0.15))
    comps = _components(lay)
    assert comps[0] == "RunwayHero"
    assert comps[1] == "ForYouFeed"
    assert lay.theme.density == "compact" and lay.theme.tone == "casual" and lay.theme.contrast == "normal"
    assert "SplitBills" in comps
    hero = lay.sections[0].props
    assert hero["daily_budget_eur"] == pytest.approx(212 / 9, abs=0.01)


def test_freelancer_gets_tax_reserve_hero():
    f = features(age=36, has_invoice_income=True, income_sources_180d=4, quarter_income_eur=8760,
                 quarter_invoice_income_eur=8760, vat_period_label="Q3 2026",
                 vat_period_invoice_income_eur=8760, vat_due_date=dt.date(2026, 10, 20))
    lay = plan(f, mix(freelancer=0.58, young_family=0.42))
    comps = _components(lay)
    assert comps[0] == "TaxReserveHero"
    hero = lay.sections[0].props
    assert hero["quarter_label"] == "Q3 2026"
    assert hero["vat_due_date"] == "2026-10-20"
    assert hero["days_to_due"] == 20
    assert hero["reserve_eur"] == pytest.approx(8760 * 0.21, abs=0.01)
    assert lay.theme.tone == "business"
    assert "InvoiceTracker" in comps
    assert "VAT" in lay.explanations["TaxReserveHero"]
    assert "58%" in lay.explanations["TaxReserveHero"]
    assert "20 days" in lay.explanations["TaxReserveHero"]


def test_tax_hero_uses_vat_reporting_period_not_calendar_quarter():
    # 5 Oct: Q3 return still open (due 20 Oct) -> period is Q3 even though calendar quarter is Q4
    as_of = dt.date(2026, 10, 5)
    f = features(age=36, as_of=as_of, has_invoice_income=True, quarter_income_eur=900,
                 quarter_invoice_income_eur=900, vat_period_label="Q3 2026",
                 vat_period_invoice_income_eur=8760, vat_due_date=dt.date(2026, 10, 20))
    lay = layout.plan_layout(f, mix(freelancer=1.0), Prefs(), customer(36), [], as_of, [])
    hero = lay.sections[0].props
    assert lay.sections[0].component == "TaxReserveHero"
    assert hero["quarter_label"] == "Q3 2026"
    assert hero["quarter_income_eur"] == 8760
    assert hero["reserve_eur"] == pytest.approx(8760 * 0.21, abs=0.01)
    assert hero["vat_due_date"] == "2026-10-20" and hero["days_to_due"] == 15
    assert "15 days" in lay.explanations["TaxReserveHero"]


def test_tax_hero_falls_back_to_calendar_quarter_without_vat_fields():
    f = features(age=36, has_invoice_income=True, vat_period_invoice_income_eur=1000)
    lay = plan(f, mix(freelancer=1.0))
    hero = lay.sections[0].props
    assert hero["quarter_label"] == "Q3 2026" and hero["vat_due_date"] == "2026-10-20" and hero["days_to_due"] == 20
    assert hero["reserve_eur"] == 210


def test_family_gets_family_budget_hero():
    f = features(age=34, has_child_signals=True, child_benefit_monthly_eur=170, childcare_monthly_eur=540)
    lay = plan(f, mix(young_family=0.7, young_professional=0.3))
    comps = _components(lay)
    assert comps[0] == "FamilyBudgetHero"
    assert lay.theme.tone == "warm" and lay.theme.density == "comfortable"
    assert "UpcomingBills" in comps
    assert lay.sections[0].props["month_label"] == "September 2026"
    assert lay.sections[0].props["child_benefit_eur"] == 170


def test_family_hero_prefers_latest_child_benefit_transaction():
    # benefit started last month: 90-day average is diluted (59), the real monthly amount is 177.
    f = features(age=34, has_child_signals=True, child_benefit_monthly_eur=59)
    t = txs([(dt.date(2026, 9, 8), 177.0, "child_benefit", "Fons Groeipakket")])
    lay = plan(f, mix(young_family=0.7, young_professional=0.3), t=t)
    assert lay.sections[0].component == "FamilyBudgetHero"
    assert lay.sections[0].props["child_benefit_eur"] == 177
    # no recent transaction -> feature value
    old = txs([(dt.date(2026, 6, 8), 177.0, "child_benefit", "Fons Groeipakket")])
    lay = plan(f, mix(young_family=0.7, young_professional=0.3), t=old)
    assert lay.sections[0].props["child_benefit_eur"] == 59


def test_retiree_gets_pension_hero_large_high_contrast():
    f = features(age=71, has_pension=True, balance_eur=14000, monthly_spend_avg_90d=1500,
                 monthly_income_avg_90d=1850, idle_cash_eur=5000)
    t = txs([(dt.date(2026, 9, 3), 1850, "pension", "Federale Pensioendienst"),
             (dt.date(2026, 8, 3), 1850, "pension", "Federale Pensioendienst")])
    lay = plan(f, mix(retiree=0.7, young_professional=0.3), t=t)
    comps = _components(lay)
    assert comps[0] == "PensionHero"
    assert lay.theme.density == "large" and lay.theme.contrast == "high" and lay.theme.tone == "formal"
    assert "ScamShield" in comps
    assert len(comps) <= 4
    hero = lay.sections[0].props
    assert hero["pension_eur"] == 1850
    assert hero["pension_received_date"] == "2026-09-03"
    assert "71" in lay.explanations["theme"]


def test_retiree_override_even_when_not_dominant_by_theme_table():
    f = features(age=68)
    lay = plan(f, mix(retiree=0.5, young_family=0.5))
    assert lay.theme.density == "large" and lay.theme.contrast == "high"


def test_hidden_pref_removes_component():
    f = features(age=34, has_child_signals=True)
    m = mix(young_family=0.7, young_professional=0.3)
    assert "UpcomingBills" in _components(plan(f, m))
    prefs = Prefs(layout_prefs=[LayoutPrefRow(component="UpcomingBills", state="hidden")])
    assert "UpcomingBills" not in _components(plan(f, m, prefs))


def test_hidden_cannot_remove_feed_or_hero():
    f = features(age=34, has_child_signals=True)
    m = mix(young_family=0.7, young_professional=0.3)
    prefs = Prefs(layout_prefs=[LayoutPrefRow(component="ForYouFeed", state="hidden"),
                                LayoutPrefRow(component="FamilyBudgetHero", state="hidden")])
    comps = _components(plan(f, m, prefs))
    assert comps[0] == "FamilyBudgetHero" and comps[1] == "ForYouFeed"


def test_pinned_pref_includes_component_first():
    f = features(age=34, has_child_signals=True)
    m = mix(young_family=0.7, young_professional=0.3)
    assert "ScamShield" not in _components(plan(f, m))
    prefs = Prefs(layout_prefs=[LayoutPrefRow(component="ScamShield", state="pinned")])
    lay = plan(f, m, prefs)
    comps = _components(lay)
    assert comps[2] == "ScamShield"
    assert lay.explanations["ScamShield"] == "Pinned by you."


def test_density_budget_respected():
    for m, budget in [
        (mix(student=1.0), 6),
        (mix(young_professional=1.0), 5),
        (mix(retiree=1.0), 4),
    ]:
        lay = plan(features(age=70 if m[0].persona == "retiree" else 25), m)
        assert len(lay.sections) == budget


def test_feed_always_second_and_one_hero():
    for m in [mix(student=1.0), mix(freelancer=1.0), mix(young_family=1.0), mix(retiree=1.0), mix(young_professional=1.0)]:
        lay = plan(features(age=70 if m[0].persona == "retiree" else 25), m)
        comps = _components(lay)
        assert comps[1] == "ForYouFeed"
        assert sum(c in HERO_COMPONENTS for c in comps) == 1
        assert lay.sections[0].size == "hero"
        assert all(s.size != "hero" for s in lay.sections[1:])


def test_stress_boosts_advisor_and_runway():
    f = features(age=29, runway_days=9, balance_eur=80)
    lay = plan(f, mix(young_professional=1.0))
    comps = _components(lay)
    assert comps[0] == "RunwayHero"
    assert "AdvisorContact" in comps
    adv = next(s for s in lay.sections if s.component == "AdvisorContact").props
    assert "9 days" in adv["reason"]
    assert adv["advisor_name"] == "Els Vermeulen"


def test_every_section_has_all_props_and_validates():
    t = txs([
        (dt.date(2026, 9, 3), 1850, "pension", "Federale Pensioendienst"),
        (dt.date(2026, 9, 12), 3200, "invoice_income", "Studio Nord"),
        (dt.date(2026, 7, 12), 3000, "invoice_income", "Studio Nord"),
        (dt.date(2026, 9, 25), -64.2, "groceries", "Colruyt"),
        (dt.date(2026, 9, 20), -48.0, "leisure", "Bar Leuven"),
        (dt.date(2026, 9, 1), -75.0, "savings_transfer", "KBC Spaarrekening"),
    ])
    rp = [RecurringPayment(counterparty="Engie", category="utilities", amount_eur=145, period_days=30,
                           last_date=dt.date(2026, 9, 8), next_date=dt.date(2026, 10, 8))]
    f = features(age=40, recurring_payments=rp, has_invoice_income=True, income_sources_180d=1,
                 quarter_invoice_income_eur=6200, has_child_signals=True, idle_cash_eur=100, has_savings_product=True)
    for comp in layout.REGISTRY:
        prefs = Prefs(layout_prefs=[LayoutPrefRow(component=comp, state="pinned")]) if comp not in HERO_COMPONENTS else Prefs()
        lay = plan(f, mix(freelancer=0.5, young_family=0.5), prefs, t)
        Layout.model_validate(lay.model_dump())
        for s in lay.sections:
            missing = REQUIRED_PROPS[s.component] - set(s.props)
            assert not missing, f"{s.component} missing {missing}"
            assert s.component in lay.explanations
        assert "theme" in lay.explanations

    # Direct check of every props builder against the contract
    ctx = {"features": f, "persona_mix": mix(freelancer=0.5, young_family=0.5), "customer": customer(40),
           "txs": t, "as_of": AS_OF, "cards": [], "weights": {"freelancer": 0.5, "young_family": 0.5}}
    for comp, entry in layout.REGISTRY.items():
        props = entry["props"](ctx)
        assert set(props) == REQUIRED_PROPS[comp], comp

    ib = layout.REGISTRY["InvoiceTracker"]["props"](ctx)
    assert ib["clients"][0]["name"] == "Studio Nord" and ib["clients"][0]["eur"] == 6200
    ub = layout.REGISTRY["UpcomingBills"]["props"](ctx)
    assert ub["bills"][0]["counterparty"] == "Engie" and ub["total_eur"] == 145
    sg = layout.REGISTRY["SavingsGoal"]["props"](ctx)
    assert sg["goal_label"] == "Child savings" and sg["saved_eur"] == 75
    sb = layout.REGISTRY["SplitBills"]["props"](ctx)
    assert len(sb["recent"]) == 2
    bh = layout.REGISTRY["BalanceHero"]["props"](ctx)
    assert len(bh["sparkline"]) == 30 and bh["sparkline"][-1] == f.balance_eur


def test_unknown_persona_mix_falls_back():
    lay = plan(features(), [])
    assert _components(lay)[0] == "BalanceHero"


def test_cashflow_card_triggers_stress_boost():
    card = Card(card_key="cashflow_squeeze:2026-09", card_type="cashflow_squeeze", family="forecast", stage="info",
                title="t", body="b", confidence=0.8)
    lay = plan(features(age=45), mix(young_professional=1.0), cards=[card])
    assert "AdvisorContact" in _components(lay)


# ---- v2: customisation --------------------------------------------------------


def test_pinned_tile_keeps_its_slot_while_the_rest_adapts():
    prefs = Prefs(layout_prefs=[LayoutPrefRow(component="ScamShield", state="pinned", position=2)])
    for m in [mix(young_family=1.0), mix(freelancer=1.0), mix(student=1.0)]:
        lay = plan(features(age=34, has_child_signals=True), m, prefs)
        comps = _components(lay)
        assert comps[2 + 2] == "ScamShield"
        assert next(s for s in lay.sections if s.component == "ScamShield").pinned


def test_pins_beyond_the_density_budget_are_still_shown():
    pins = [LayoutPrefRow(component=c, state="pinned", position=i)
            for i, c in enumerate(["ScamShield", "SplitBills", "InvoiceTracker", "AdvisorContact", "SavingsGoal"])]
    lay = plan(features(age=70), mix(retiree=1.0), Prefs(layout_prefs=pins))
    assert len(lay.sections) == 2 + 5
    assert _components(lay)[2:] == ["ScamShield", "SplitBills", "InvoiceTracker", "AdvisorContact", "SavingsGoal"]


def test_pinned_hero_wins_and_can_be_challenged_by_a_suggestion():
    f = features(age=40, has_invoice_income=True, income_sources_180d=3)
    prefs = Prefs(layout_prefs=[LayoutPrefRow(component="BalanceHero", state="pinned")])
    p = layout.plan_home_layout(f, mix(freelancer=1.0), prefs, customer(40), [], AS_OF, [])
    assert p.layout.sections[0].component == "BalanceHero" and p.layout.sections[0].pinned
    assert p.suggestions and p.suggestions[0].component == "TaxReserveHero" and p.suggestions[0].as_hero


def test_style_overrides_win_and_are_explained():
    prefs = Prefs(style=StylePrefs(density="large", appearance="dark", accent="teal", privacy=True))
    lay = plan(features(age=21, has_student_signals=True), mix(student=1.0), prefs)
    t = lay.theme
    assert (t.density, t.appearance, t.accent, t.privacy, t.tone) == ("large", "dark", "teal", True, "casual")
    assert set(t.overrides) == {"density", "appearance", "accent"}
    assert lay.explanations["theme"].startswith("You chose large text, dark mode, a teal accent.")
    assert len(lay.sections) == layout.DENSITY_BUDGET["large"]


def test_life_event_suggests_a_tile_until_dismissed():
    ev = LifeEvent(type="first_invoice", date=AS_OF - dt.timedelta(days=20), evidence="first invoice")
    f = features(age=33, has_salary=True, life_events=[ev])
    p = layout.plan_home_layout(f, mix(young_professional=1.0), Prefs(), customer(33), [], AS_OF, [])
    assert p.suggestions[0].component == "TaxReserveHero"
    assert "first client payment" in p.suggestions[0].reason
    snoozed = Prefs(dismissed_suggestions=[SuggestionDismissal(component="TaxReserveHero", created_at=AS_OF)])
    p2 = layout.plan_home_layout(f, mix(young_professional=1.0), snoozed, customer(33), [], AS_OF, [])
    assert all(s.component != "TaxReserveHero" for s in p2.suggestions)


def test_declared_signal_suggests_only_after_it_was_said():
    f = features(age=30, has_salary=True)
    said = AS_OF - dt.timedelta(days=5)
    prefs = Prefs(declared=[DeclaredSignalRow(signal="expecting_baby", created_at=said)])
    p = layout.plan_home_layout(f, mix(young_professional=1.0), prefs, customer(30), [], AS_OF, [])
    assert any(s.title.startswith("You told Kate") for s in p.suggestions)
    before = layout.plan_home_layout(f, mix(young_professional=1.0), prefs, customer(30), [], said - dt.timedelta(days=1), [])
    assert not any(s.title.startswith("You told Kate") for s in before.suggestions)


def test_gallery_lists_every_tile_except_the_feed():
    prefs = Prefs(layout_prefs=[LayoutPrefRow(component="SplitBills", state="hidden")])
    p = layout.plan_home_layout(features(age=30), mix(young_professional=1.0), prefs, customer(30), [], AS_OF, [])
    comps = {g.component for g in p.gallery}
    assert comps == set(layout.REGISTRY) - {"ForYouFeed"}
    states = {g.component: g.state for g in p.gallery}
    assert states["SplitBills"] == "hidden" and states["BalanceHero"] == "shown"
    assert sum(g.suggested for g in p.gallery) == 3 and all(g.state == "available" for g in p.gallery if g.suggested)
