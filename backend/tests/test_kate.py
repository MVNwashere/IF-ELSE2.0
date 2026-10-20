"""Kate: grounded rules, proposals only, LLM output validated or discarded."""
from __future__ import annotations

import datetime as dt

import pytest

from app.engine import kate, pipeline
from app.schemas import Customer, KateRequest, Prefs, Transaction

AS_OF = dt.date(2026, 9, 30)


@pytest.fixture(scope="module")
def ctx():
    rows = []
    for m in range(1, 10):
        rows.append((dt.date(2026, m, 25), 2800.0, "salary", "Acme NV"))
        rows.append((dt.date(2026, m, 3), -12.99, "subscription", "Spotify"))
        rows.append((dt.date(2026, m, 5), -17.99 if m >= 8 else -13.99, "subscription", "Netflix"))
        rows.append((dt.date(2026, m, 10), -420.0, "groceries", "Colruyt"))
    txs = [Transaction(id=i, customer_id=1, date=d, amount=a, category=c, counterparty=cp)
           for i, (d, a, c, cp) in enumerate(sorted(rows), 1)]
    cust = Customer(id=1, first_name="Nora", last_name="Test", birth_year=1995, city="Gent")
    return pipeline.build_home_with_features(cust, txs, 5200.0, Prefs(), AS_OF)


def ask(ctx, message, card_key=None):
    home, f = ctx
    return kate.reply(home, f, KateRequest(message=message, card_key=card_key))


def test_opener_greets_by_name(ctx):
    assert "Nora" in ask(ctx, "").reply


def test_subscriptions_are_grounded(ctx):
    r = ask(ctx, "What are my subscriptions?")
    assert "Netflix" in r.reply and "Spotify" in r.reply


def test_style_and_tile_requests_become_proposals(ctx):
    assert ask(ctx, "switch to dark mode please").actions[0].style.appearance == "dark"
    a = ask(ctx, "pin my subscriptions").actions[0]
    assert (a.kind, a.component) == ("pin_tile", "SubscriptionsTile")


def test_declaring_needs_a_tap(ctx):
    a = ask(ctx, "We're expecting a baby in March!").actions[0]
    assert (a.kind, a.signal) == ("declare", "expecting_baby")


def test_fallback_offers_help(ctx):
    r = ask(ctx, "qwertyuiop")
    assert r.quick_replies and r.source == "rules"


def test_llm_text_is_used_only_when_grounded(ctx):
    home, f = ctx
    req = KateRequest(message="How am I doing this month?")
    good = kate.reply(home, f, req, llm=lambda *a: "Nice and steady this month, Nora.")
    assert good.source == "llm"
    invented = kate.reply(home, f, req, llm=lambda *a: "You could save €987654 with our new product.")
    assert invented.source == "rules"
    link = kate.reply(home, f, req, llm=lambda *a: "See https://evil.example for details.")
    assert link.source == "rules"

    def boom(*a):
        raise TimeoutError

    assert kate.reply(home, f, req, llm=boom).source == "rules"


def test_several_style_wishes_become_one_proposal(ctx):
    r = ask(ctx, "Can you make the text bigger? I also want dark mode")
    assert len(r.actions) == 1
    s = r.actions[0].style
    assert (s.density, s.appearance) == ("large", "dark")
    assert "larger text and dark mode" in r.reply
