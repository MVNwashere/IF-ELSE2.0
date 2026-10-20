"""Kate: the conversational side of the engine (docs/CUSTOMER-APP.md).

`reply(home, features, request, ...) -> KateReply`

- Grounded: every fact Kate states comes from what the engine already computed (home, features, goals, profile,
  consents).
- Kate never changes anything. She proposes `KateAction`s; the app shows a button; the customer taps it; the app
  calls the regular, validated endpoint (layout-prefs, style, feedback, declare, profile, goals, consents).
- Two modes. Rules (this module) always work and need nothing outside KBC. AI mode (kate_agent.py: a model via
  OpenRouter with typed tools) runs only when it is configured AND the customer allowed it (purpose `kate_ai`); any
  failure falls back to the rules answer.
- Memory: when the customer mentions a fact that fits their profile, Kate proposes to save it (purpose
  `kate_memory`). Special categories of personal data (health, beliefs, ...) are never proposed for saving.
"""
from __future__ import annotations

import logging
import re

from ..profile.fields import FIELDS, PURPOSE_DEFS, phrase, validate, value_label
from ..profile.service import correction_label
from ..schemas import Card, Features, HomeResponse, KateAction, KateReply, KateRequest, ProfileResponse, StylePrefs
from . import kate_agent
from .features import fmt_date, fmt_eur
from .kate_agent import World, goal_action
from .layout import (ADVISOR_NAME, CARD_ADVICE, KATE_GENERAL_REPLIES, KATE_QUICK_REPLIES, PERSONA_LABEL, SCAM_HOTLINE,
                     SCAM_TIPS, TILE_LABEL)

log = logging.getLogger("kate")

MAX_REPLY = 1100

GREETING = {
    "casual": "Hey {name}!",
    "neutral": "Hello {name}.",
    "warm": "Hi {name}!",
    "business": "Good day, {name}.",
    "formal": "Good day, {name}.",
}

# keyword → tile. First match wins, so more specific words come first.
TILE_WORDS: list[tuple[tuple[str, ...], str]] = [
    (("subscription",), "SubscriptionsTile"),
    (("tax", "vat", "btw"), "TaxReserveHero"),
    (("invoice", "client"), "InvoiceTracker"),
    (("savings", "saving goal", "goal"), "SavingsGoal"),
    (("bill",), "UpcomingBills"),
    (("spending", "categories"), "SpendingByCategory"),
    (("scam", "safety", "shield"), "ScamShield"),
    (("advisor", "adviser"), "AdvisorContact"),
    (("split",), "SplitBills"),
    (("pension",), "PensionHero"),
    (("runway",), "RunwayHero"),
    (("family",), "FamilyBudgetHero"),
    (("balance",), "BalanceHero"),
    (("quick action", "shortcut"), "QuickActions"),
    (("kate", "assistant"), "KateTile"),
]

DECLARE_WORDS: list[tuple[tuple[str, ...], str, str]] = [
    (("expecting", "pregnant", "baby on the way", "having a baby", "zwanger"), "expecting_baby",
     "Congratulations! Want me to take that into account? Your home will adapt to a growing family, "
     "and you can undo it any time."),
    (("going freelance", "become freelance", "becoming freelance", "self-employed", "start my own business",
      "starting my own business", "zelfstandige", "own company"), "going_freelance",
     "Exciting step! Want me to take that into account? I'll keep VAT and invoices in view from day one. "
     "You can undo it any time."),
    (("retiring", "going to retire", "retire soon", "retirement next"), "retiring",
     "A big milestone. Want me to take that into account? Your home will get calmer, with your pension in view. "
     "You can undo it any time."),
    (("start studying", "going to university", "going to college", "i'm a student", "i am a student"), "studying",
     "Nice! Want me to take that into account? I'll focus on how far your money stretches. You can undo it any time."),
]

# things a customer says that are really a goal → the playbook KBC can run for them
GOAL_WORDS: list[tuple[tuple[str, ...], str]] = [
    # more specific phrases first that would otherwise fall into an older goal
    (("debt", "can't pay", "cannot pay", "can not pay", "behind on", "bailiff", "deurwaarder", "arrears",
      "klarna", "pay later", "unpaid bills", "schulden"), "back_on_track"),
    (("separating", "separation", "divorce", "breaking up", "break up", "split up", "scheiding"), "separation"),
    (("moving in together", "move in together", "living together", "getting married", "get married", "wedding",
      "samenwonen", "trouwen"), "together"),
    (("side business", "side hustle", "side job", "bijberoep", "next to my job", "alongside my job"), "side_job"),
    (("care home", "nursing home", "home care", "woonzorgcentrum", "mantelzorg", "ageing parent", "aging parent",
      "elderly parent", "my mother needs", "my father needs"), "care_parent"),
    (("sell my business", "sell my company", "selling my business", "selling my company", "hand over my business",
      "successor", "overdracht"), "sell_business"),
    (("export", "foreign client", "clients abroad", "customers abroad", "sell abroad", "international clients",
      "international business"),
     "go_international"),
    (("my farm", "harvest", "greenhouse", "tractor", "boerderij", "veiling"), "farm_growth"),
    (("electric car", "electric vehicle", "ev charging", "charging station", "laadpaal", "elektrische auto"),
     "ev_switch"),
    (("start investing", "begin investing", "first investment", "beginnen met beleggen", "how do i invest"),
     "first_investment"),
    (("buy a house", "buy a home", "buying a house", "buying a home", "buy an apartment", "first home", "huis kopen",
      "house hunting", "mortgage"), "buy_home"),
    (("insulat", "solar", "heat pump", "energy bill", "renovat", "energy label", "epc"), "energy_upgrade"),
    (("expecting", "pregnant", "baby on the way", "having a baby", "zwanger"), "new_baby"),
    (("going freelance", "become freelance", "becoming freelance", "self-employed", "start my own business",
      "starting my own business", "zelfstandige", "own company"), "go_freelance"),
    (("unpaid", "owes me", "late payer", "hasn't paid", "has not paid", "not paying"), "get_paid"),
    (("retire", "pension gap", "inheritance", "invest my savings", "put my savings to work"), "retire_well"),
    (("holiday", "travel", "trip", "vacation", "flight"), "travel"),
    (("protect my savings", "safe banking", "grandchildren", "was it a scam"), "peace_of_mind"),
    (("moving house", "moving out", "move house", "new flat", "new apartment", "rent a flat", "verhuizen"),
     "move_house"),
]
# goals about a hard moment start with empathy, not with a sales line
GOAL_LEAD = {
    "back_on_track": "Thanks for telling me, that takes courage. Let's take it one step at a time",
    "separation": "I'm sorry to hear that. I can make the money side calmer",
    "care_parent": "That's a lot to take on. I can carry part of it",
}



# ----------------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------------


def _has(text: str, *words: str) -> bool:
    return any(w in text for w in words)


def _card(home: HomeResponse, key: str | None) -> Card | None:
    return next((c for c in home.feed.cards if c.card_key == key), None) if key else None


def _shown(home: HomeResponse) -> set[str]:
    return {s.component for s in home.layout.sections}


def _tile_from(text: str) -> str | None:
    for words, comp in TILE_WORDS:
        if _has(text, *words):
            return comp
    return None


def _style_with(home: HomeResponse, **changes) -> StylePrefs:
    return home.style.model_copy(update=changes)


def _card_quick(card: Card) -> list[str]:
    return list(KATE_QUICK_REPLIES.get(card.card_type, KATE_GENERAL_REPLIES))


def _snooze(card: Card) -> KateAction:
    return KateAction(kind="snooze_card", label="Remind me in a week", card_key=card.card_key, card_type=card.card_type)


def _out(reply: str, actions: list[KateAction] | None = None, quick: list[str] | None = None) -> KateReply:
    return KateReply(reply=reply[:MAX_REPLY], actions=(actions or [])[:3], quick_replies=(quick or [])[:4])


# ----------------------------------------------------------------------------------
# Intents (deterministic)
# ----------------------------------------------------------------------------------


def _goal_intent(goals, text: str) -> KateReply | None:
    if goals is None:
        return None
    for words, playbook_id in GOAL_WORDS:
        if not _has(text, *words):
            continue
        action = goal_action(goals, playbook_id)
        if action is None:
            return None
        pb = next(p for p in goals.playbooks if p.playbook_id == playbook_id)
        if action.kind == "open_goal":
            g = next(g for g in goals.goals if g.goal_id == action.goal_id)
            return _out(f"We're already on it: {g.title.lower()}, {g.progress.done} of {g.progress.total} steps done.",
                        [action])
        cand = next((c for c in goals.candidates if c.playbook_id == playbook_id), None)
        partners = f" together with {', '.join(cand.partners_preview[:3])}" if cand and cand.partners_preview else ""
        lead = GOAL_LEAD.get(playbook_id, "I can take care of that")
        return _out(f"{lead}: '{pb.title}' is a plan of {pb.steps} steps that KBC runs for you"
                    f"{partners}. You approve every step, and you decide what any partner gets to see.", [action])
    return None


def _opener(home: HomeResponse, card: Card | None, goals=None) -> KateReply:
    name = home.customer.first_name
    hello = GREETING[home.layout.theme.tone].format(name=name)
    if not card and goals is not None and goals.candidates:
        c = goals.candidates[0]
        return _out(f"{hello} I noticed something: {c.evidence[0] if c.evidence else c.tagline}. {c.why_now} "
                    f"Want KBC to take care of it?",
                    [KateAction(kind="start_goal", label="Let KBC take care of it", playbook_id=c.playbook_id)],
                    ["Why do you think so?"] + KATE_GENERAL_REPLIES[:2])
    if card:
        return _out(f"{hello} Let's look at this together: {card.title}. {card.body}",
                    [KateAction(kind="open_card", label="Show me the card", card_key=card.card_key)],
                    _card_quick(card))
    cards = home.feed.cards
    if not cards:
        return _out(f"{hello} Nothing needs your attention right now. What can I help you with?",
                    quick=KATE_GENERAL_REPLIES + ["Make the text bigger"])
    top = cards[0]
    more = f" There {'is' if len(cards) == 2 else 'are'} {len(cards) - 1} more thing{'s' if len(cards) > 2 else ''} " \
           f"in your feed." if len(cards) > 1 else ""
    return _out(f"{hello} Here's what stands out. {top.title}.{more} Shall we go through it?",
                [KateAction(kind="open_card", label="Show me", card_key=top.card_key)],
                _card_quick(top)[:2] + KATE_GENERAL_REPLIES[:2])


def _about_card(card: Card, text: str, home: HomeResponse) -> KateReply | None:
    quick = _card_quick(card)
    if _has(text, "wasn't me", "was not me", "not me", "fraud", "didn't do", "did not do"):
        return _out(f"Let's act fast. Call Card Stop on {SCAM_HOTLINE.split('Card Stop ')[-1]} to block your card, "
                    f"then call your branch. Don't share codes with anyone who calls you.",
                    [KateAction(kind="add_tile", label="Keep Scam shield on my home", component="ScamShield")]
                    if "ScamShield" not in _shown(home) else [], ["How do I recognise a scam?"])
    if _has(text, "remind", "later", "next week", "not now"):
        return _out("Sure. I'll bring it back in a week.", [_snooze(card)], KATE_GENERAL_REPLIES)
    if _has(text, "why", "calculate", "how do you know", "how did you"):
        ev = "; ".join(card.evidence) if card.evidence else "the pattern in your transactions"
        rank = f" It's high in your feed because: {card.rank_explanation}." if card.rank_explanation else ""
        return _out(f"Here's what I based this on: {ev}.{rank}", [], [q for q in quick if "why" not in q.lower()][:3])
    if _has(text, "coverage", "differ", "compare", "comparison"):
        rows = card.details.get("comparison") if isinstance(card.details, dict) else None
        if rows:
            lines = "; ".join(f"{r['item']}: now {r['current']}, KBC {r['kbc']}" for r in rows[:5])
            note = card.details.get("note", "")
            return _out(f"{lines}. {note}".strip(), [_snooze(card)], ["What should I do?"])
    if _has(text, "per year", "a year", "yearly") and card.eur_impact:
        return _out(f"That's about {fmt_eur(card.eur_impact)} per year.", [], quick)
    if _has(text, "what should", "what can i", "what do i", "options", "what now", "help", "sort out", "what if",
            "how does", "is this right", "cover", "how late"):
        advice = CARD_ADVICE.get(card.card_type, card.body)
        actions = [_snooze(card)]
        if card.card_type == "protection_gap" or card.card_type == "pension_savings":
            actions.insert(0, KateAction(kind="add_tile", label="Put my advisor on my home", component="AdvisorContact"))
        if card.card_type == "late_client":
            actions.insert(0, KateAction(kind="add_tile", label="Add the invoices tile", component="InvoiceTracker"))
        actions = [a for a in actions if a.kind != "add_tile" or a.component not in _shown(home)]
        cta = f" You can also tap “{card.cta.label}” on the card." if card.cta else ""
        return _out(advice + cta, actions, [q for q in quick if q.lower() not in text][:3])
    return None


STYLE_REQUESTS: list[tuple[tuple[str, ...], dict, str]] = [
    (("bigger", "larger", "can't read", "cannot read", "hard to read", "text size", "groter"),
     {"density": "large"}, "larger text"),
    (("smaller", "more compact", "compact"), {"density": "compact"}, "a compact layout"),
    (("dark mode", "dark theme", "darker"), {"appearance": "dark"}, "dark mode"),
    (("light mode", "light theme"), {"appearance": "light"}, "light mode"),
    (("contrast",), {"contrast": "high"}, "high contrast"),
    (("hide amount", "hide my balance", "privacy", "people looking", "hide numbers"), {"privacy": True},
     "hidden amounts (tap to reveal)"),
    (("less motion", "reduce motion", "animations", "dizzy"), {"reduce_motion": True}, "fewer animations"),
]


def _style_intent(home: HomeResponse, text: str) -> KateReply | None:
    if _has(text, "reset my style", "reset the style", "default look", "reset look", "back to normal", "back to auto"):
        return _out("I can put the look back on Auto, so it adapts to you again.",
                    [KateAction(kind="reset_style", label="Reset look to Auto")])
    changes: dict = {}
    names: list[str] = []
    for words, change, name in STYLE_REQUESTS:
        if _has(text, *words) and not (set(change) & set(changes)):
            changes.update(change)
            names.append(name)
    if not changes:
        return None
    what = " and ".join([", ".join(names[:-1]), names[-1]] if len(names) > 1 else names)
    label = f"Switch to {what}" if len(what) <= 50 else "Apply these changes"
    return _out(f"Of course: {what}. Tap below to apply it; you can switch back any time in your settings.",
                [KateAction(kind="set_style", label=label, style=_style_with(home, **changes))])


def _tile_intent(home: HomeResponse, text: str) -> KateReply | None:
    wants_add = _has(text, "pin", "add", "show me", "put", "keep")
    wants_hide = _has(text, "hide", "remove", "get rid", "don't want", "do not want")
    if not (wants_add or wants_hide):
        return None
    comp = _tile_from(text)
    if not comp:
        return None
    label = TILE_LABEL[comp][0]
    if wants_hide:
        if comp not in _shown(home):
            return _out(f"{label} isn't on your home screen right now.")
        return _out(f"No problem. I'll take {label} off your home; you can add it back from Edit home.",
                    [KateAction(kind="hide_tile", label=f"Hide {label}", component=comp)])
    return _out(f"Good idea. {TILE_LABEL[comp][1]}. Pinned tiles stay where you put them.",
                [KateAction(kind="pin_tile", label=f"Pin {label}", component=comp)])


def _declare_intent(home: HomeResponse, text: str) -> KateReply | None:
    for words, signal, message in DECLARE_WORDS:
        if _has(text, *words):
            if any(d.signal == signal for d in home.declared):
                return _out("You told me that already, and your home takes it into account.")
            return _out(message, [KateAction(kind="declare", label="Yes, take it into account", signal=signal)])
    return None


def _general(home: HomeResponse, f: Features, text: str) -> KateReply | None:
    if _has(text, "why does my app", "why does the app", "look like this", "persona", "who am i", "why this layout",
            "why do i see", "how do you decide"):
        mix = ", ".join(f"{round(p.weight * 100)}% {PERSONA_LABEL[p.persona]}" for p in home.persona_mix)
        ev = next((p.evidence[0] for p in home.persona_mix if p.evidence), "")
        theme = home.layout.explanations.get("theme", "")
        return _out(f"Nobody designed this screen for you by hand: it's composed from your own transactions. "
                    f"Right now you look like {mix}{f' (for example: {ev})' if ev else ''}. {theme} "
                    f"You can pin, hide or restyle anything.",
                    quick=["Make the text bigger", "How am I doing this month?"])
    if _has(text, "subscri"):
        subs = [r for r in f.recurring_payments if r.category == "subscription"]
        if not subs:
            return _out("I don't see any subscriptions on your account.")
        monthly = sum(r.amount_eur * 30 / max(1, r.period_days) for r in subs)
        items = ", ".join(f"{r.counterparty[:40]} {fmt_eur(r.amount_eur)}" for r in subs[:5])
        actions = [] if "SubscriptionsTile" in _shown(home) else [
            KateAction(kind="pin_tile", label="Pin Subscriptions", component="SubscriptionsTile")]
        return _out(f"You have {len(subs)} subscription{'s' if len(subs) != 1 else ''}, about {fmt_eur(monthly)} "
                    f"a month: {items}.", actions)
    if _has(text, "next income", "get paid", "payday", "salary", "when is my"):
        if f.next_income_date:
            amt = f" of about {fmt_eur(f.next_income_eur)}" if f.next_income_eur else ""
            return _out(f"I expect your next income{amt} around {fmt_date(f.next_income_date)}.")
        return _out("I can't predict your next income yet: it doesn't follow a regular pattern.")
    if _has(text, "stretch", "runway", "last until", "enough money"):
        if f.runway_days is not None:
            return _out(f"At your current pace, your balance of {fmt_eur(f.balance_eur)} lasts about {f.runway_days} "
                        f"days. Postponing non-urgent spending until your next income helps most.")
        return _out(f"Your balance of {fmt_eur(f.balance_eur)} isn't heading below zero at your current pace.")
    if _has(text, "how am i doing", "this month", "spend", "spent", "where did my money", "where does my money",
            "balance", "how much"):
        top = sorted(f.spend_by_category_30d.items(), key=lambda kv: kv[1], reverse=True)[:3]
        cats = ", ".join(f"{k.replace('_', ' ')} {fmt_eur(v)}" for k, v in top)
        return _out(f"Your balance is {fmt_eur(f.balance_eur)}. On average you receive {fmt_eur(f.monthly_income_avg_90d)} "
                    f"and spend {fmt_eur(f.monthly_spend_avg_90d)} a month."
                    + (f" In the last 30 days your biggest costs were {cats}." if cats else ""),
                    quick=["What are my subscriptions?", "Why does my app look like this?"])
    if _has(text, "pin code", "pincode", "my pin", "card code", "password", "itsme code"):
        return _out(f"I can't see your PIN or passwords, and KBC will never ask for them, not even me. Forgot your PIN? "
                    f"Your branch or advisor can send a new one. Did someone ask you for it? {SCAM_HOTLINE}.",
                    quick=["How do I recognise a scam?"])
    if _has(text, "scam", "phishing", "fraud", "suspicious"):
        return _out(" ".join(SCAM_TIPS) + f" Lost your card or worried? {SCAM_HOTLINE}.",
                    [] if "ScamShield" in _shown(home) else
                    [KateAction(kind="pin_tile", label="Pin Scam shield", component="ScamShield")])
    if _has(text, "advisor", "human", "a person", "call my bank", "talk to someone", "call"):
        return _out(f"{ADVISOR_NAME}, your advisor, can help in person or by phone. "
                    f"You can book a moment from the advisor tile.",
                    [] if "AdvisorContact" in _shown(home) else
                    [KateAction(kind="pin_tile", label="Pin my advisor", component="AdvisorContact")])
    return None


def _signals_intent(goals, deadlines, forecasts, text: str) -> KateReply | None:
    """Deadlines and forecasts: "what's coming up?", "when is my VAT due?", "will I owe social contributions later?"."""
    if deadlines is None:
        return None
    asks_forecast = _has(text, "regularis", "social contribution", "will i owe", "tax surprise")
    asks_deadline = _has(text, "deadline", "coming up", "is due", "vat due", "vat return", "advance tax", "when do i pay")
    if not (asks_forecast or asks_deadline):
        return None
    if asks_forecast and forecasts:
        fc = forecasts[0]
        amount = f" of about {fmt_eur(round(fc.amount_eur, -1))}" if fc.amount_eur and "€" not in fc.title else ""
        due = f", around {fmt_date(fc.due)}" if fc.due else ""
        action = goal_action(goals, fc.playbook_id) if fc.playbook_id else None
        return _out(f"{fc.title}{amount}{due}. {' '.join(fc.evidence[:2])} This is an estimate from your own "
                    "transactions, so it can change.", [action] if action else [])
    items = [d for d in deadlines if not _has(text, "vat") or d.kind == "vat_return"]
    if not items:
        return _out("Nothing is due in the coming weeks that I can see from your account.")
    lines = []
    for d in items[:3]:
        amount = f" (about {fmt_eur(round(d.amount_eur))})" if d.amount_eur else ""
        short = f", {fmt_eur(round(d.shortfall_eur))} short" if d.shortfall_eur else ""
        when = "" if fmt_date(d.date) in d.title else f" on {fmt_date(d.date)}"
        lines.append(f"{d.title}{when}{amount}{short}")
    first = items[0]
    action = goal_action(goals, first.playbook_id) if first.playbook_id else None
    return _out("Coming up: " + "; ".join(lines) + ". I can set money aside automatically so these never surprise you.",
                [action] if action else [])


# ----------------------------------------------------------------------------------
# Profile: what KBC knows, memory, corrections, permissions (deterministic)
# ----------------------------------------------------------------------------------

# Special categories of personal data (GDPR art. 9). Kate never offers to store them and says so.
SENSITIVE_WORDS = ("diagnos", "cancer", "my illness", "chronic", "depress", "therapy", "medication", "disabilit",
                   "diabet", "my health is", "health condition", "health problem", "mental health", "burnout", "disease",
                   "religio", "my church", "mosque", "synagogue", "my faith", "political party", "i vote for",
                   "trade union", "vakbond", "i'm gay", "i am gay", "lesbian", "bisexual", "transgender",
                   "sexual orientation")

PROFILE_QUESTIONS = ("what do you know about me", "what do you know of me", "what does kbc know", "my profile",
                     "what data do you have", "what information do you have", "what do you remember")
ACCESS_QUESTIONS = ("who has my data", "who can see my data", "who sees my data", "shared my data",
                    "access to my data", "my consents", "consent passport", "who has access")
REVOKE_WORDS = ("revoke", "stop sharing", "take back access", "withdraw")
FORGET_WORDS = ("forget", "delete what i told", "remove what i told", "erase what i told")
FORGET_ALL = ("everything", "all of it", "what i told you", "all you know", "all that")
FIELD_WORDS: dict[str, tuple[str, ...]] = {
    "children": ("kids", "children", "child"),
    "partner": ("partner", "wife", "husband", "relationship", "married", "single"),
    "employment": ("job", "work", "employ", "freelance", "self-employed", "retired"),
    "housing": ("rent", "mortgage", "where i live", "my home", "my house"),
    "risk_appetite": ("risk",),
    "contact_channel": ("contact", "call me", "phone"),
    "avoid_topics": ("offers", "topics"),
    "cares_for_relative": ("care for", "caring for"),
}
# (phrases, purpose, allowed). Matched as whole words; for each purpose the "off" phrases come first.
PERMISSION_WORDS: list[tuple[tuple[str, ...], str, bool]] = [
    (("stop remembering", "don't remember", "do not remember", "don't save", "stop saving"), "kate_memory", False),
    (("you may remember", "you can remember", "remember what i tell"), "kate_memory", True),
    (("stop using my transactions", "don't analyse", "don't analyze", "stop spotting", "don't spot",
      "stop detecting"), "detect_life_events", False),
    (("no personalised offers", "no personalized offers", "stop personalising", "stop personalizing",
      "stop targeting"), "personalise_offers", False),
    (("stop using ai", "don't use ai", "do not use ai", "turn off ai", "switch off ai"), "kate_ai", False),
    (("use ai", "turn on ai", "switch on ai", "smarter answers"), "kate_ai", True),
    (("hide my profile from my advisor", "don't let my advisor", "advisor can't see"), "advisor_view", False),
    (("let my advisor see", "share my profile with my advisor", "advisor can see my profile"), "advisor_view", True),
]
# persona → words, for "I'm not a freelancer", "that's wrong, I'm not retired"
PERSONA_WORDS: dict[str, tuple[str, ...]] = {
    "freelancer": ("freelancer", "self-employed", "self employed", "freelance"),
    "student": ("student",),
    "retiree": ("retired", "retiree", "pensioner"),
    "young_family": ("family", "a parent", "have kids", "have children"),
    "investor": ("investor",),
    "young_professional": ("young professional",),
}
NOT_ME = ("i'm not", "i am not", "im not", "not a ", "i don't have", "i do not have", "no longer", "that's wrong",
          "that is wrong", "wrong about")
REJECT_GOAL = ("not interested", "don't want", "do not want", "no need", "stop suggesting", "not for me",
               "not planning")
AVOID_WORDS = ("no offers about", "no more offers", "stop showing me", "stop offering", "don't want offers",
               "don't sell me", "not interested in", "stop suggesting")
TOPIC_WORDS = {"investing": ("invest",), "insurance": ("insurance",), "credit": ("loan", "credit")}

NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
_CHILDREN = re.compile(r"\b(\d{1,2}|one|two|three|four|five|six|seven|eight)\s+(?:kids|children|sons|daughters)\b")


def _phrase(text: str, *phrases: str) -> bool:
    return any(re.search(rf"(?<![a-z]){re.escape(p)}(?![a-z])", text) for p in phrases)


def _allows(profile: ProfileResponse | None, purpose: str) -> bool:
    if profile is None:
        return purpose != "kate_ai"
    return next((p.allowed for p in profile.permissions if p.purpose == purpose), False)


def _saved(profile: ProfileResponse | None) -> dict:
    return {f.key: f for f in profile.fields if f.value is not None} if profile else {}


def stated_facts(text: str) -> dict[str, object]:
    """Facts about the customer in one message, as validated profile values. Conservative: explicit phrases only."""
    out: dict[str, object] = {}
    m = _CHILDREN.search(text)
    if m:
        n = m.group(1)
        out["children"] = int(n) if n.isdigit() else NUM_WORDS[n]
    elif _has(text, "no kids", "no children", "don't have kids", "don't have children", "do not have kids",
              "do not have children"):
        out["children"] = 0
    if _has(text, "my wife", "my husband", "got married", "just married", "we're married", "i'm married",
            "i am married"):
        out["partner"] = "married"
    elif _has(text, "my partner", "my girlfriend", "my boyfriend", "we live together", "we're living together"):
        out["partner"] = "partner"
    elif _has(text, "i'm single", "i am single", "i live alone", "i'm divorced", "i am divorced"):
        out["partner"] = "single"
    if _has(text, "i'm self-employed", "i am self-employed", "i'm a freelancer", "i am a freelancer",
            "i work for myself", "i run my own business", "i have my own business"):
        out["employment"] = "self_employed"
    elif _has(text, "side business", "side job", "side hustle", "next to my job"):
        out["employment"] = "employee_side_job"
    elif _has(text, "i'm retired", "i am retired", "since i retired"):
        out["employment"] = "retired"
    elif _has(text, "lost my job", "i'm unemployed", "i am unemployed", "looking for a job", "looking for work",
              "between jobs"):
        out["employment"] = "job_seeker"
    elif _has(text, "i'm an employee", "i am an employee", "my employer", "my boss"):
        out["employment"] = "employee"
    if _has(text, "i rent", "we rent", "i'm renting", "we're renting", "my landlord", "our landlord"):
        out["housing"] = "renting"
    elif _has(text, "live with my parents", "living with my parents"):
        out["housing"] = "with_parents"
    elif _has(text, "we own our home", "i own my home", "we own our house", "i own my house", "paid off our house",
              "paid off my house"):
        out["housing"] = "own"
    if _has(text, "don't like risk", "avoid risk", "risk averse", "risk-averse", "play it safe"):
        out["risk_appetite"] = "careful"
    elif _has(text, "i like risk", "high risk", "adventurous investor"):
        out["risk_appetite"] = "adventurous"
    if _has(text, "prefer", "rather", "contact me", "reach me"):
        if _has(text, "call me", "by phone", "a call", "phone call"):
            out["contact_channel"] = "phone"
        elif _has(text, "branch", "in person", "face to face"):
            out["contact_channel"] = "branch"
        elif _has(text, "in the app", "a message", "the app"):
            out["contact_channel"] = "app"
    if _has(text, "caring for my mother", "caring for my father", "i care for my", "i look after my mother",
            "i look after my father"):
        out["cares_for_relative"] = True
    return {k: validate(k, v) for k, v in out.items()}


def _save_action(key: str, value) -> KateAction:
    return KateAction(kind="update_profile", label=f"Save: {value_label(key, value)}"[:60], fact_key=key,
                      fact_value=value)


def _open_profile() -> KateAction:
    return KateAction(kind="open_profile", label="Open my profile")


def _sensitive(text: str) -> KateReply | None:
    if not _has(text, *SENSITIVE_WORDS):
        return None
    return _out("Thank you for trusting me with that. I won't keep it: health, beliefs and similar personal details "
                "never go into your profile. If it affects your money, I'm happy to look at that with you.",
                quick=["How am I doing this month?"])


def _profile_summary(home: HomeResponse, profile: ProfileResponse | None) -> KateReply:
    told = [phrase(k, f.value) for k, f in _saved(profile).items()]
    if told:
        lines = ["You told us that " + (", ".join(told[:-1]) + " and " + told[-1] if len(told) > 1 else told[0])
                 + "."]
    else:
        lines = ["You haven't told us anything about yourself yet."]
    mix = ", ".join(f"{round(p.weight * 100)}% {PERSONA_LABEL[p.persona]}" for p in home.persona_mix)
    source = "From your transactions and what you told us" if told else "From your transactions"
    lines.append(f"{source}, your home is built for: {mix}.")
    if profile is not None:
        a = profile.data_access
        who = ("No partner can see your data" if a.partners_with_access == 0 else
               f"{a.partners_with_access} partner{'s' if a.partners_with_access != 1 else ''} can see part of your data")
        reads = ("KBC reads no outside sources" if a.sources_connected == 0 else
                 f"KBC reads {a.sources_connected} outside source{'s' if a.sources_connected != 1 else ''} with your OK")
        lines.append(f"{who}, and {reads}.")
    lines.append("In your profile you can correct anything and decide what it's used for.")
    return _out(" ".join(lines), [_open_profile()], ["Who has my data?"])


def _data_access(text: str, consents) -> KateReply:
    active = [g for g in consents.grants if g.status == "active"] if consents is not None else []
    if _has(text, *REVOKE_WORDS):
        g = next((g for g in active if g.partner_name.lower() in text), None)
        if g:
            return _out(f"{g.partner_name} can see {', '.join(x.label.lower() for x in g.fields)} for "
                        f"'{g.goal_title}'. If you revoke it, they are told to stop and delete your data.",
                        [KateAction(kind="revoke_consent", label=f"Revoke {g.partner_name}'s access"[:60],
                                    grant_id=g.grant_id)])
    if not active:
        lead = "No partner can see your data right now."
    else:
        lead = " ".join(f"{g.partner_name} sees {', '.join(x.label.lower() for x in g.fields[:3])} for "
                        f"'{g.goal_title}', until {fmt_date(g.expires_on)}." for g in active[:3])
    reads = [s.name for s in (consents.sources if consents is not None else []) if s.status == "connected"]
    more = f" KBC reads {', '.join(reads)} with your OK." if reads else ""
    return _out(lead + more + " You can revoke any of it in your consent passport.",
                [KateAction(kind="open_passport", label="Who sees my data")])


def _forget_intent(text: str, profile: ProfileResponse | None) -> KateReply | None:
    if not _has(text, *FORGET_WORDS):
        return None
    saved = _saved(profile)
    key = next((k for k, words in FIELD_WORDS.items() if k in saved and _has(text, *words)), None)
    if key:
        return _out(f"Sure. I can delete '{FIELDS[key].label}: {saved[key].value_label}' from your profile.",
                    [KateAction(kind="forget_fact", label=f"Delete: {FIELDS[key].label}"[:60], fact_key=key)])
    if _has(text, *FORGET_ALL):
        if not any(f.source == "kate" for f in saved.values()):
            return _out("Nothing from our chats is saved in your profile.", [_open_profile()])
        return _out("I can delete everything you saved to your profile from our chats. Things you entered yourself "
                    "in your profile stay.", [KateAction(kind="forget_kate_facts", label="Forget what I told Kate")])
    return None


def _permission_intent(text: str, profile: ProfileResponse | None) -> KateReply | None:
    for phrases, purpose, allowed in PERMISSION_WORDS:
        if not _phrase(text, *phrases):
            continue
        p = PURPOSE_DEFS[purpose]
        if _allows(profile, purpose) == allowed:
            return _out(f"That's already {'on' if allowed else 'off'}: {p.label.lower()}.", [_open_profile()])
        return _out(f"{p.description if allowed else p.when_off} You can change it back any time in your profile.",
                    [KateAction(kind="set_permission", label=f"{'Allow' if allowed else 'Stop'}: {p.label}"[:60],
                                purpose=purpose, allowed=allowed)])
    return None


def _correction_intent(text: str, goals, profile: ProfileResponse | None) -> KateReply | None:
    """"No offers about investing", "I'm not a freelancer", "not interested in buying a house"."""
    saved = _saved(profile)
    if _has(text, *AVOID_WORDS):
        topics = {t for t, words in TOPIC_WORDS.items() if _has(text, *words)}
        if topics:
            current = set(saved["avoid_topics"].value) if "avoid_topics" in saved else set()
            if topics <= current:
                return _out("You told us that already: no offers on those topics.")
            if not _allows(profile, "kate_memory"):
                return _out("You can switch off offers on a topic in your profile, under 'No offers about'.",
                            [_open_profile()])
            return _out(f"Understood. I'll hold back offers and goal suggestions about "
                        f"{value_label('avoid_topics', sorted(topics))}. Alerts about your own contracts stay.",
                        [_save_action("avoid_topics", sorted(current | topics))])
    if _has(text, *NOT_ME):
        hits = [p for p, words in PERSONA_WORDS.items() if _has(text, *words)]
        if hits:
            actions = [KateAction(kind="correct_inference", label=correction_label("persona", p)[:60],
                                  correction_kind="persona", target=p) for p in hits[:2]]
            if "young_family" in hits and "children" not in saved and _allows(profile, "kate_memory"):
                actions.append(_save_action("children", 0))
            return _out("Thanks for correcting me. Tap below and your home stops treating you that way; you can "
                        "undo it in your profile.", actions)
    if _has(text, *REJECT_GOAL) and goals is not None:
        for words, playbook_id in GOAL_WORDS:
            if _has(text, *words) and any(p.playbook_id == playbook_id for p in goals.playbooks):
                return _out("Got it, I'll stop suggesting that. You can still start it yourself any time.",
                            [KateAction(kind="correct_inference", label=correction_label("goal", playbook_id)[:60],
                                        correction_kind="goal", target=playbook_id)])
    return None


def _with_facts(r: KateReply | None, text: str, profile: ProfileResponse | None) -> KateReply | None:
    """Offer to save facts the customer just mentioned, on their own or next to the main answer."""
    saved = _saved(profile)
    facts = {k: v for k, v in stated_facts(text).items() if k not in saved or saved[k].value != v}
    if not facts:
        return r
    if not _allows(profile, "kate_memory"):
        if r is not None:
            return r
        return _out("Thanks for telling me. You've switched off that I remember things, so I won't save it.",
                    [_open_profile()])
    saves = [_save_action(k, v) for k, v in facts.items()]
    if r is None:
        return _out("Thanks for telling me. Shall I save it to your profile? Your home and my answers then take it "
                    "into account, and you can change or delete it any time.", saves)
    room = 3 - len(r.actions)
    if room <= 0:
        return r
    return _out(r.reply + " I can also save what you told me to your profile.", r.actions + saves[:room],
                r.quick_replies)


def rules_reply(home: HomeResponse, f: Features, req: KateRequest, goals=None, deadlines=None,
                forecasts=None, profile: ProfileResponse | None = None, consents=None,
                ai_available: bool = False) -> KateReply:
    """`ai_available`: the AI mode is configured but the customer hasn't allowed it (the fallback offers it)."""
    text = req.message.strip().lower()
    card = _card(home, req.card_key)
    if not text:
        return _opener(home, card, goals)
    sensitive = _sensitive(text)
    if sensitive:
        return sensitive
    signal_reply = _signals_intent(goals, deadlines, forecasts, text)
    if signal_reply:
        return signal_reply
    if goals is not None and goals.candidates and _has(text, "why do you think", "how do you know"):
        c = goals.candidates[0]
        return _out(f"From your own transactions: {'; '.join(c.evidence)}. Nothing has been shared with anyone.",
                    [KateAction(kind="start_goal", label="Let KBC take care of it", playbook_id=c.playbook_id)])
    if _has(text, *ACCESS_QUESTIONS) or (_has(text, *REVOKE_WORDS) and consents is not None and
                                         any(g.partner_name.lower() in text for g in consents.grants)):
        return _data_access(text, consents)
    if _has(text, *PROFILE_QUESTIONS):
        return _profile_summary(home, profile)
    for intent in (_forget_intent(text, profile), _permission_intent(text, profile), _style_intent(home, text),
                   _correction_intent(text, goals, profile)):
        if intent:
            return intent
    declared = _declare_intent(home, text)
    goal = _goal_intent(goals, text)
    if declared and goal:   # "we're expecting": adapt the home AND offer the journey
        return _with_facts(_out(declared.reply + " " + goal.reply, declared.actions + goal.actions), text, profile)
    r = declared or goal or _tile_intent(home, text)
    if r is None and card:
        r = _about_card(card, text, home)
    r = r or _general(home, f, text)
    if r is None:   # a question about another card in the feed?
        r = next((x for c in home.feed.cards
                  if _has(text, *c.card_type.split("_")) and (x := _about_card(c, text, home))), None)
    r = _with_facts(r, text, profile)
    if r:
        return r
    if ai_available:
        return _out("I'm not sure I got that. With AI switched on I can answer more freely; it only sees what your "
                    "question needs.",
                    [KateAction(kind="set_permission", label="Let Kate use AI", purpose="kate_ai", allowed=True)],
                    KATE_GENERAL_REPLIES + ["What do you know about me?"])
    return _out("I'm not sure I got that. I can explain anything in your feed, show where your money goes, "
                "change how your app looks, or put a tile on your home.",
                quick=KATE_GENERAL_REPLIES + ["Make the text bigger", "What do you know about me?"])


def reply(home: HomeResponse, features: Features, req: KateRequest, llm: kate_agent.Chat | None = None, goals=None,
          deadlines=None, forecasts=None, profile: ProfileResponse | None = None, consents=None) -> KateReply:
    """AI mode when it is configured (or `llm` is given) and the customer allowed it; otherwise, or on any failure,
    the rules. `goals` is the ecosystem GoalsResponse, `consents` its ConsentsResponse."""
    chat = llm or (kate_agent.openrouter_chat if kate_agent.enabled() else None)
    ai_on = chat is not None and _allows(profile, "kate_ai")
    base = rules_reply(home, features, req, goals, deadlines, forecasts, profile, consents,
                       ai_available=chat is not None and not ai_on)
    if not ai_on:
        return base
    try:
        out = kate_agent.run(World(home, features, req, goals, deadlines, forecasts, profile, consents), chat)
    except Exception as e:  # any failure → the deterministic answer
        log.warning("kate agent failed: %s", type(e).__name__)
        return base
    return out or base
