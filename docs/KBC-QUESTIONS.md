---
title: How round 1 answered KBC's questions
type: context          # context | spec | decision | notes
status: outdated       # draft | review | final | outdated
incorporated: n/a      # no | partial | yes | n/a
code_refs: []
owner: team IF-ELSE
created: 2026-09-30
updated: 2026-10-20
source: round 1 repo, github.com/Senne-Meuleman/IF-ELSE
---

# KBC Challenge — Our Answers

> **Outdated for round 2.** This answers the round 1 brief (personalisation). The round 2 brief and our answer are
> in [ROUND2-DESIGN.md](ROUND2-DESIGN.md). It's still useful material for the "recognise emerging needs" part.

> How **KBC Adaptive Home** answers the questions in the Tectonic participants guide.
> Companion to [`DESIGN.md`](DESIGN.md) (section numbers like §6.4 refer to it).
> Use this for the project description, the pitch and the last 30 seconds of the demo video.

---

## The challenge in KBC's words

> *"Imagine a future where KBC perfectly understands what customers need and responds at exactly the right moment."*
> *"We're not looking for a new feature. We're looking for a vision and a proof of concept for a scalable personalization approach that fundamentally strengthens the relationship between KBC and its customers."*

## Our answer in one paragraph

Today every KBC customer opens the same app. We propose an app that is **composed per customer**, and not by hand. The system reads signals from a customer's own financial life, works out *who they are* (a mix of student, young professional, young family, freelancer, retiree) and *what is happening now* (a renewal, a price increase, a tight month, a first salary). From that it builds two things: a **home screen layout** that fits the person, and a **For You feed** of a few useful, explained, time-bound cards that ends when there is nothing more worth saying. The same engine runs for one customer or for 2.3 million, and the customer can always see *why* and change it.

**Persona sets the stage, moments fill it.**

---

## Step 1 — "First, think without constraints"

What the ideal experience looks like from the customer's side:

| Principle | What it means in practice |
|---|---|
| **The bank notices, so I don't have to** | "Your car insurance renews in 12 days" before I forget, not after. |
| **It speaks my language** | A student gets a playful runway ("€212 for 9 days"), a retiree a calm, large, high-contrast screen. |
| **It grows with me** | The app I used as a student turns into a family budget app when I have a child, without me changing anything. |
| **It's on my side** | It optimizes for euros saved and stress avoided, not clicks or product sales. Warnings are never outranked by offers. |
| **It respects my attention** | A short feed that ends: "✓ You're all caught up." No infinite scroll. |
| **It explains itself** | Every card and every screen section has a "Why am I seeing this?" pointing to real evidence. |
| **I'm in control** | Dismiss, snooze, "less like this", pin or hide sections, switch off commercial personalisation, all with one tap. |
| **A human when it matters** | Sensitive moments (income drop, cash-flow squeeze) surface an advisor, not an ad. |

## Step 2 — "Then, deliver it to 2.3M customers in a scalable way"

That is the rest of this document, one question at a time.

---

## Q1. What signals can help us understand what customers need?

**Short answer:** mostly signals KBC already has: transactions on the customer's own accounts, plus products held, age and the customer's own feedback. No external data is needed for a strong first version.

| Signal group | Examples | What it tells us |
|---|---|---|
| **Income pattern** | Salary vs. invoices from several clients vs. pension vs. student job; regularity; changes of payer | Life stage (student, employee, freelancer, retiree); new job; income loss |
| **Recurring payments** | Rent/mortgage, insurance premiums (yearly), subscriptions, utilities | Upcoming renewals, price increases, moves (rent stops, notary payment) |
| **Life-event spending** | Childcare, baby shops, school, tuition, furniture/DIY, notary | Growing family, moving house, study |
| **Government flows** | Child benefit (Groeipakket), VAT payments, social contributions, pension | Family, self-employed status, retirement, admin deadlines |
| **Balance dynamics** | Spending trend vs. income, runway to zero, idle cash | Cash-flow stress, saving opportunity |
| **Anomalies** | Duplicate charges, sudden price jumps | Immediate, concrete help |
| **Products held** | Savings, insurance, mortgage, investment plan | Gaps and overlaps, and also when *not* to recommend |
| **Customer feedback** | Dismiss, snooze, less like this, pins/hides, consent | What this person actually finds useful |
| **Context** | Age, language, calendar (tax deadlines, back to school) | Timing and tone |

**In the PoC:** implemented as `features.py` over synthetic transactions (§6.2), with a fixed list of categories (§6.1).

**Design choices worth saying out loud**
- Only *first-party* data the customer already shares with KBC. No scraping, no social media.
- Every signal produces **human-readable evidence** ("Yearly payment of €612 to your insurer on 12 Oct 2025"), which we reuse in the "why" explanations.
- Signals are computed "as of" a date, so the same pipeline supports real-time triggers, nightly batches and our time-travel demo.

---

## Q2. How can customers be recognized based on their situation, behaviour and intent?

**Short answer:** not with a segment label, but with a **persona mix** (who you are) plus **moments** (what is happening now).

**1. Situation → persona mix.** Five personas (`student`, `young_professional`, `young_family`, `freelancer`, `retiree`) are each scored from signals. The result is a weighted blend with evidence:

> Sara: **58% freelancer** (income from 4 clients, quarterly VAT) · **42% young family** (child benefit since March 2024, daycare payments)

Real people don't fit one box. A self-employed mother is not "a freelancer" *or* "a young family", and blends are where hand-designed segments fail and a computed approach wins. (§6.3)

**2. Behaviour → moments.** Card generators detect time-bound events: renewals, price increases, duplicate charges, tight months, idle cash, first salary, new baby. (§6.4)

**3. Intent → feedback and actions.** What the customer taps, dismisses, snoozes, pins or hides is the most direct intent signal we have. It updates rankings immediately (fatigue factor, §6.5) and layout preferences (§6.6).

**Why this beats classic segmentation**
- **Continuous, not static.** The mix shifts as life changes. Our time-travel demo shows one customer moving from student to freelancer mother over 8 years.
- **Explainable.** Every weight comes with its evidence, visible to the customer and the advisor.
- **Cold start handled.** A new customer gets sensible defaults from age and products, then signals take over within weeks.

---

## Q3. How can personalized experiences automatically adapt to each customer?

**Short answer:** by generating the experience from a **fixed set of building blocks**, instead of designing screens per segment.

**Two adaptive layers**

| Layer | Driven by | What changes | PoC |
|---|---|---|---|
| **Adaptive layout** (the frame) | Persona mix | Which modules appear, which is the hero, density, font size, contrast, tone of voice | §6.6: component registry + planner → layout JSON |
| **For You feed** (the content) | Moments + feedback | Which cards appear, in what order, with what urgency | §6.4–6.5: card generators + ranker |

**How it works automatically**
1. A **component registry** of ~14 approved building blocks (`RunwayHero`, `FamilyBudgetHero`, `TaxReserveHero`, `PensionHero`, `ForYouFeed`, `ScamShield`, …), each with an affinity per persona.
2. A **planner** scores components against the customer's persona mix and current signals, picks a hero, fills a density budget and sets a theme. Output: a small **layout spec (JSON)** that the app renders.
3. A **ranker** orders cards by value to the customer: `urgency × impact × confidence × persona fit × fatigue`, then applies hard rules (service before sales, max 1 commercial per 3 cards, max 7 cards, then "all caught up").
4. **Cards have a lifecycle.** They appear early, escalate (early → soon → urgent) and expire, so the right moment is built in.
5. An **optional LLM** rewrites copy in the right tone and language (NL/FR), but never decides amounts, products or layout, and its output is validated or discarded.

**Why this matters for KBC**
- Designers keep control of *what* can be shown (the registry). The system decides *what fits whom*. It's on-brand by construction.
- Adding a new persona, card or component is a registry entry, not a new app release.
- The combinations are effectively unlimited, but every one is explainable and testable.

---

## Q4. How can this work seamlessly across products, services and channels?

**Short answer:** by making the unit of personalization a **card with evidence and an action**, not a product. The same card can then be shown anywhere.

**Across products.** Cards are organized around the customer's *situation*, not KBC's product lines. The insurance renewal card, the VAT reserve card and the savings card come from different product areas but appear in one feed, ranked against each other on value to the customer. The layout mixes banking (runway, budget), insurance (renewals, coverage) and services (advisor, scam protection) on one screen.

**Across channels.** The engine already outputs everything a channel needs: title, body, evidence, urgency stage, action. A **channel policy** decides where it goes:

| Situation | Channel |
|---|---|
| Urgent and time-critical (going below zero in 3 days) | Push notification |
| Normal relevance | In-app For You feed |
| Sensitive (income drop, financial stress) | Advisor call / branch, with the same evidence on the advisor's screen |
| Accessibility (retiree mode) | Voice: "Read my day" (ElevenLabs, stretch) |
| Conversational | KBC's assistant can use the same cards and explanations as its context |

**One brain, many surfaces.** The customer app, the advisor's screen and the assistant all read the same `HomeResponse`. An advisor sees exactly what the customer sees, with the same "why", so the conversation continues across channels instead of restarting.

**Feedback is shared too.** A card dismissed in the app is not pushed again or brought up by the advisor.

---

## Q5. How can you create meaningful impact for millions of customers at the same time?

**Short answer:** a pure, deterministic engine that runs as a batch plus event triggers, with humans and LLMs only where they add value.

**Scale architecture** (§9)
- The engine is **pure functions per customer**, so it parallelizes trivially across customers.
- **Nightly batch + event triggers** (salary received, new recurring payment, a card entering a new urgency stage) recompute each customer's home and cache it. Opening the app is a cache read.
- **LLM only on cache misses, only for copy.** Templates cover 100% of cases, so cost and latency stay predictable at 2.3M customers.
- **Measured, not claimed.** The PoC times scoring of the full synthetic portfolio and extrapolates to 2.3M in the advisor view.

**Impact at scale, not just reach**
- **Money impact:** each card has `eur_impact`. Summed over the portfolio, that's a KPI: *euros saved for customers per month* (renewals compared, duplicates refunded, price increases spotted, idle cash put to work).
- **Stress impact:** cash-flow warnings sent *before* the account goes below zero; advisor calls for income drops.
- **Relationship impact:** fewer irrelevant messages (the feed ends), more trust (every card explained), higher acceptance of the offers that do appear, because they are timely.

**Guardrails that make it safe to run for millions**
- Service before sales, fixed commercial ratio, consent required for commercial cards.
- Honest comparisons (coverage differences, not only price).
- Full audit log of advisor lookups; customers only ever see their own data.
- Metrics to watch: precision@5 of the feed, dismiss rate per card type, "less like this" rate, euros-saved per customer, opt-out rate.

---

## What KBC is looking for, and how we match it

| KBC asks for | Our answer |
|---|---|
| "Not just another feature" | Not a feature but a **way to compose the whole app**: layout and content, for every customer. |
| "A vision" | *The bank app as a function of your life.* Persona sets the stage, moments fill it. |
| "A proof of concept" | Working app: synthetic data → signals → persona mix → cards/ranker → layout spec → animated home screen, with time travel and feedback. |
| "Scalable personalization" | Pure engine + batch/event triggers + caching; LLM optional; measured scoring time extrapolated to 2.3M. |
| "Strengthens the relationship" | Explanations, control, a feed that ends, service before sales, a human for sensitive moments. |
| "Understand, support and guide" | **Understand:** signals and persona mix. **Support:** timely service cards and adapted UI. **Guide:** actions, honest comparisons, advisor handoff. |

---

## Honest limitations (say them before the jury does)

- **Synthetic data.** Detectors are tuned on data we generated; real transaction data is messier (merchant names, categorization errors).
- **Rules, not ML (yet).** Persona scoring and ranking are transparent rule-based models on purpose. The contract (signals in, weights and cards out) allows swapping in trained models later, e.g. learning ranker weights from feedback.
- **Offers are illustrative.** Prices and coverage in comparison cards are placeholders, not real KBC products.
- **Regulation not fully addressed.** GDPR purpose limitation, MiFID/IDD rules for investment and insurance advice, and fairness checks across personas would need review before production.
- **Adaptive UI needs guardrails in UX research.** Changing layouts can confuse people. We mitigate with a stable navigation bar, pin/hide controls and a "standard layout" switch, but this should be user-tested.
