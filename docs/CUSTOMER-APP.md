# KBC Takes Care: the customer app

The customer-facing app layer: one banking app that looks and behaves differently for each customer. Nobody designs
the home screen by hand. The engine composes it from signals in the customer's own (synthetic) transactions.

*Persona sets the stage, moments fill it.*

- **Layout (who you are):** a persona mix decides which tiles appear, which one is the main tile (the hero), and the
  density, contrast and tone of the screen.
- **For You feed (what is happening now):** a short list of cards, ranked from Customer State. The feed ends with
  "You're all caught up".
- **Explainable and controllable:** every card and every tile says why it is there. The customer can dismiss,
  snooze, pin, hide, restyle and switch off commercial personalisation.
- **Kate:** a chat assistant that answers from the same data and proposes changes the customer confirms.
- **Time travel:** everything is recomputed "as of" any date in the customer's history.

The ecosystem engine (goals, journeys, partners, consent, nudges) sits behind this app. It is documented in
[ECOSYSTEM.md](ECOSYSTEM.md); this doc only covers how the app surfaces it.

## How it fits together

```
SQLite (synthetic) ─► transactions ≤ as_of ─► features ─► persona mix ─┬─► layout planner ─► layout spec
                                                  │                     │      ▲
                                                  └─► card generators ─► ranker (legacy cards: layout signals only)
                    ─► Customer State ─► recommender (9 personas, core + catalogue cards) ─► feed
                                                                              ▲
          feedback, pins, hides, style, declared signals, consent ────────────┘
                                                                  ─► HomeResponse ─► React phone renderer
```

`GET /api/me/home` runs two pipelines and merges them into one `HomeResponse`:

1. `engine/pipeline.py` computes features, the persona mix, legacy cards and the layout plan (sections, theme,
   explanations, suggestions, gallery).
2. `main.py` builds the recommender's feed from Customer State (`customer_state.get_state` →
   `recommender.recommend`) and merges it with the engine's cards in `recommender/compose.py`, then
   `ecosystem/links.py` links feed cards to goal journeys.

**One home, one number per fact (`recommender/compose.py`).** The engine's cards are the moments that need action
(VAT due, a payment that may be a scam, a late client, an insurance renewal); the recommender adds the overview and
catalogue cards. The merge:

| Rule | What it does |
|---|---|
| Moments first | Cards sort by stage (urgent, soon, the rest), then engine moments, then core overview cards, then catalogue tips and seasonal reminders (pension savings, scam season). At most 8 cards. |
| One source per fact | Upcoming payments come from Customer State only (`feed.upcoming_items`, next 30 days, with counterparty names); hero tiles get `balance_eur` and their bills, spending and income from Customer State. With a `TaxReserveHero`, the expected VAT payment uses the reserve amount and the balance forecast moves with it. |
| No duplicates | Tiles that repeat a card leave the layout (`UpcomingBills` next to "Coming up", `SpendingByCategory` next to "Spending this month", an empty `SavingsGoal` next to the buffer card). The VAT card leaves when the VAT hero shows it; a suspicious payment replaces the generic scam tips and explains the spending jump; "Your money" leaves when it only repeats the ball; the €1.000 example planner leaves when a real buffer or savings plan is shown. |
| Tiles follow the feed | `KateTile` opens on the merged feed's top card; `AdvisorContact` names a suspicious payment when there is one. |

Design rules:

| Rule | What it means in the code |
|---|---|
| Pure core | `features`, `persona`, `cards`, `ranker`, `layout`, `kate` take their inputs as arguments. No I/O, no `date.today()`. |
| Time is a parameter | Every computation takes `as_of`. Transactions after it are ignored. |
| Deterministic first | Everything works without an LLM. The optional LLM may only rephrase Kate's text. |
| Explain everything | Persona weights, cards and tiles carry plain-English evidence or explanations. |
| Server decides | The frontend renders the spec. It does not choose what to show. |
| Tuning knobs on top | Weights and thresholds are named constants at the top of each module. |

## Synthetic data (`backend/synth/`)

All data is synthetic. The database is `backend/kbc.db`. It is built on first start (`main.ensure_db`), or by hand:
`py -3.12 -m synth.generate --n 1000 --seed 42`. Delete the file to rebuild it.

| Source | What it creates |
|---|---|
| `generate.py` | 1,000 regular customers (`c1` … `c1000`) with 400 days of history up to `TODAY` (2026-10-20). Primary persona drawn from young professional, student, young family, freelancer, retiree. Injected events: `insurance_renewal`, `price_increase`, `duplicate_charge`, `cashflow_squeeze`, `idle_cash`. Also goal scenarios and near-miss look-alikes for the intent evaluation (see [ECOSYSTEM.md](ECOSYSTEM.md)). Plus the `advisor` login. |
| `demo_customers.py` | Nine hand-crafted demo customers (ids 9001–9009) with long histories, and Lotte's simulated future. |
| `customer_state.py` | Ten Customer State scenarios (stable, variable, debt, foreign, …), appended to an existing database with `py -3.12 -m synth.customer_state`. See [CUSTOMER-STATE.md](CUSTOMER-STATE.md). |
| `holdout.py` | About 300 blind holdout customers for the intent evaluation. Generated in memory, not stored. |

Injected scenarios are stored in `customers.ground_truth`. Customer endpoints never return it.

Tables (in `app/db.py`): `customers`, `accounts`, `transactions`, `users`, `feedback`, `layout_prefs`,
`style_prefs`, `declared_signals`, `suggestion_dismissals`, `visits`, `audit_log`. Customer State and the ecosystem
add their own tables.

Demo logins (password `demo`, or `DEMO_PASSWORD` at build time):

| Username | Story |
|---|---|
| `lotte` | Student in Leuven (2018) → first job → house and mortgage → baby (2024) → goes freelance (Oct 2026). Her timeline continues as a simulated future up to the end of 2028. |
| `sara` | Freelancer and young mother. Car insurance renews soon, Netflix price increase. |
| `jan` | 71, retiree. Pension, a duplicate charge, idle cash. |
| `marc` | 52, the investor. Salary, mortgage nearly paid off, pension savings, idle cash, a trip booked. |
| `tom` | 31, employee with a side business. |
| `els` | 48, eldest starts university, mother moved into a care home. |
| `amir` | 34, newcomer with four months of history. |
| `pieter` | 44, SME owner with clients abroad. |
| `nina` | 29, buy-now-pay-later, bounced direct debits, a bailiff. |
| `advisor` | Opens the KBC ecosystem console instead of the phone. |

**Lotte's simulated future.** Her chapters after today are generated in memory (`lotte_future_transactions`) and
appended by `db.get_transactions`; they are never stored. The time slider can go past today for her, and those
milestones are labelled "Simulated: …". Customer State reads stored transactions only, so in the simulated future the
For You feed does not see the simulated transactions; the layout does.

## Features (`engine/features.py`)

`compute_features(customer, txs, balance_today, as_of) -> Features` uses only transactions on or before `as_of`.
The balance at `as_of` is `balance_today` minus everything booked after it.

Main fields: age, balance, average monthly income and spending (90 days, one-off costs excluded), income regularity
(coefficient of variation), distinct payers (180 days), income by category, next income date and amount, VAT period
income and due date, spending by category (30 days), change in variable spending, runway days, idle cash, flags
(salary, invoices, pension, student, child, VAT, social contributions, mortgage, rent, savings product), child
benefit and childcare per month, recurring payments (with previous price when it changed) and life events
(`first_salary`, `first_invoice`, `baby`, `pension_start`, `first_pension`, `moved_house`).

The full field list is the `Features` model in `schemas.py`.

## Persona mix (`engine/persona.py`)

The layout uses six personas: `student`, `young_professional`, `young_family`, `freelancer`, `investor`, `retiree`.
Each has a scoring function that returns a raw score and evidence strings. Scores are normalised to weights; weights
below 0.15 are dropped and the rest renormalised to sum to 1. With no signals at all, the mix is 100% young
professional ("No strong signals yet").

| Persona | Main signals |
|---|---|
| student | Under 26 with student signals; extra for student job income, allowance, yearly tuition |
| young_professional | Salary, no child signals, under 45; extra for very regular income and age under 36 |
| young_family | Any child signal; grows with child benefit + childcare + baby/school spending as a share of income |
| freelancer | Invoice income, VAT or social contributions; grows with the invoice share of income, ramped over the first year |
| investor | 45–66 with a salary and no pension; extra for a balance of 10+ months of spending and yearly pension savings |
| retiree | Pension income; age 67+ |

**Declared signals.** What the customer told Kate counts too, from the day it was said (so time travel respects it).
Each adds 0.6 to one persona, with evidence "You told Kate on … that …":

| Signal | Persona |
|---|---|
| `expecting_baby` | young_family |
| `going_freelance` | freelancer |
| `retiring` | retiree |
| `studying` | student |

**Profile facts and corrections** (see [Customer profile](#customer-profile-profile)). A stated fact adds the same
0.6, from the day it was saved, with evidence "You told us …": children ≥ 1 → young_family; work self-employed →
freelancer (an employee with a side business → half of that); student → student; retired → retiree. A persona the
customer rejected ("That's not me") scores 0 whatever the transactions say; if nothing is left, the general profile
is the fallback.

The recommender has its own, separate persona model with nine codes (see the feed section).

## Legacy cards and ranker (`engine/cards.py`, `engine/ranker.py`)

Thirteen card generators propose cards from features: `insurance_renewal`, `vat_reserve`, `price_increase`,
`duplicate_charge`, `runway`, `cashflow_squeeze`, `idle_cash`, `life_event`, `scam_awareness`, `pension_savings`,
`late_client`, `protection_gap`, `new_payee`. Comparison cards list coverage differences, not only price, and KBC
prices are illustrative. Counterparty names are cleaned (control characters stripped, capped at 40 characters).

Stage comes from the due date: more than 14 days → `early`, 4–14 → `soon`, 0–3 → `urgent`, past → not shown. No due
date → `info`.

The ranker scores each card:

```
score = persona_fit × (0.40·urgency + 0.30·impact + 0.20·confidence + 0.10·novelty) × fatigue
  urgency     urgent 1.0 | soon 0.7 | early 0.4 | info 0.3
  impact      min(1, log10(1 + |eur_impact|) / 3.5)
  persona_fit Σ weight(persona) × affinity[card_type][persona]
  novelty     1.0 if there was no earlier visit or the due date is after the last visit, else 0.5
  fatigue     × 0.3 per "less", × 0.8 per "dismiss" on that card type in the last 30 days
```

Then: commercial cards need consent; dismissed or accepted card keys are hidden, snoozed ones for 7 days; urgent
service cards come first; at most 1 commercial card per 3 shown, 2 per family, 7 in total.

**Where this output is used.** The ranked legacy cards feed the layout planner (cash-flow stress, the Kate tile
boost) and `GET /api/advisor/overview`, and they are the "moments" that `recommender/compose.py` merges into the
visible feed next to the recommender's cards.

## For You feed (`backend/app/recommender/feed.py`)

The feed is built from Customer State, not from `Features`. Customer State itself (signals, metrics, patterns,
risks, freshness) is documented in [CUSTOMER-STATE.md](CUSTOMER-STATE.md).

**Personas.** `infer_personas` scores nine soft personas from observed, non-sensitive signals, age, declared signals
and products: `TEEN`, `STU`, `YPRO`, `PAR`, `HOME`, `SELF`, `INV`, `PRE`, `SEN`. They are returned as
`HomeResponse.feed_personas`. Products are only used when `as_of` is today, because holdings are not dated.

**Cards.**

| Kind | Source | Count |
|---|---|---|
| Core cards | `_core_cards`: money, spending, coming up, unusual, insurance, goals, investments, debt, cards, financial health | 10 types |
| Catalogue cards | `catalogue.json`, imported from [reference/feed-specs](reference/feed-specs/) by `scripts/import_feed_catalogue.py` | 100 definitions (`catalog_ys_01` … `catalog_le_12`) |

A catalogue card is eligible only when a fitting persona has weight ≥ 0.18, the age rules allow it, `Product` cards
have consent, and its condition holds on Customer State. Cards that need data the app does not have are held back.
Editorial cards without a condition can show on a persona match. Where Customer State supports a measured value, the
card body uses it; example figures from the spec are never shown.

**Ranking.**

| Step | Rule |
|---|---|
| Filter | Drop dismissed or accepted card keys, snoozed ones (7 days), and commercial cards without consent |
| Score | Core: a fixed priority (money 1.0, spending and coming up 0.82, others 0.48, a few raised per persona). Catalogue: 0.22 + 0.38 × persona fit. Times 0.35 if the customer said "less like this" for that type. Plus 1.2 for urgent, 0.12 for soon |
| Select | At most 7 cards, 4 core, 2 commercial and no more than 1 commercial per 3 shown (before the merge with the engine's moments, see above) |

`rank_explanation` is the card's first two evidence lines. `Feed.hidden_count` is the number of eligible cards left
out. Each card's `details` carries metrics, an optional savings planner, and the related cards to show in the detail
sheet.

**Ecosystem links.** `ecosystem/links.py` maps catalogue ids and legacy card types to goal playbooks. When the
playbook fits the customer, the card gets `details.playbook_id`, the products and partners of that journey, and the
CTA "Let KBC take care of it" (`start_goal`).

## Layout planner (`engine/layout.py`)

`plan_home_layout(features, persona_mix, prefs, customer, txs, as_of, cards) -> Plan` returns the layout, the
suggestions and the gallery. Only registered components can appear. Props are built from real feature data and
follow [COMPONENT-PROPS.md](COMPONENT-PROPS.md) exactly.

| Component | Size | Strongest persona |
|---|---|---|
| `BalanceHero` | hero | young_professional, investor |
| `RunwayHero` | hero | student |
| `FamilyBudgetHero` | hero | young_family |
| `TaxReserveHero` | hero | freelancer |
| `PensionHero` | hero | retiree |
| `ForYouFeed` | full | always shown |
| `QuickActions` | full | all |
| `KateTile` | full | all |
| `UpcomingBills` | half | young_family, retiree |
| `SplitBills` | half | student |
| `InvoiceTracker` | half | freelancer |
| `SavingsGoal` | half | young_professional, young_family, investor |
| `ScamShield` | half | retiree |
| `AdvisorContact` | half | retiree, investor, anyone under cash-flow stress |
| `SpendingByCategory` | half | young_professional |
| `SubscriptionsTile` | half | student, young_professional |

**Scoring.** `component_score = Σ weight(persona) × affinity[component][persona] + signal boosts`.

| Signal | Boost |
|---|---|
| Cash-flow stress (runway ≤ 21 days, or a legacy `runway` / `cashflow_squeeze` card) | `AdvisorContact` +0.65, `RunwayHero` +0.7 |
| Invoice income | `InvoiceTracker` +0.3, `TaxReserveHero` +0.3 |
| Child signals | `FamilyBudgetHero` +0.3, `UpcomingBills` +0.3 |
| Age 65+ | `ScamShield` +0.4, `PensionHero` +0.4 |
| Idle cash / savings product | `SavingsGoal` +0.2 each |
| A legacy card in stage soon or urgent | `KateTile` +0.2 |
| 3+ subscriptions, or one just got more expensive | `SubscriptionsTile` +0.25 |

**Placement.**

1. Hero: the customer's pinned hero, otherwise the best-scoring hero.
2. `ForYouFeed` always comes right after the hero.
3. The density sets a tile budget: compact 6, comfortable 5, large 4 (hero and feed included). Pins never get cut:
   the budget grows to fit them.
4. Pinned tiles keep their slot; the best-scoring remaining tiles fill the gaps.
5. Every placed section gets an explanation in `layout.explanations[component]`, and the theme gets one under
   `explanations["theme"]`.

**Theme.** The dominant persona sets the base. A retiree weight of 0.5 or more forces large text and high contrast.

| | student | young_professional | young_family | freelancer | investor | retiree |
|---|---|---|---|---|---|---|
| density | compact | comfortable | comfortable | compact | comfortable | large |
| tone | casual | neutral | warm | business | formal | formal |
| contrast | normal | normal | normal | normal | normal | high |

## Customisation: the system proposes, the customer decides

The home stays adaptive by default. Customisation is a sparse layer of overrides on top.

| Feature | How it works | Endpoint |
|---|---|---|
| Pin a tile | The tile keeps its slot (`position` = index among the tiles below the feed) while the rest adapts. `position: null` = first free slot. | `POST /api/me/layout-prefs` |
| Pin a hero | It stays the main tile. Only one hero can be pinned; pinning another releases the first. | same |
| Hide a tile | The tile is left out of the layout and never suggested. | same, `state: hidden` |
| Unpin / unhide | `state: reset` removes the preference; the tile adapts again. | same |
| Arrange the wall | Drag tiles and feed cards to any spot of the For you wall, remove them, add rows. Stored as one arrangement per customer and applied at every date. | `PUT /api/me/tile-grid` |
| Reset to adaptive | Removes all pins, hides, suggestion dismissals and the wall arrangement. | `POST /api/me/layout-reset` |
| Tile gallery | `HomeResponse.gallery`: every tile with label, description, score, state (shown, available, hidden) and the same reason Explain mode gives. The top 3 available tiles are marked suggested. Adding a tile pins it to the first free slot. | `POST /api/me/layout-prefs` |
| Suggestions | Up to 2 at a time (see below). Accept = pin (as hero if it is one). "Not now" = snoozed 90 days. The current home does not show them (the wall marks auto-placed tiles "Suggested" instead); the API still returns them. | `POST /api/me/suggestion` |
| Style | Density, contrast, tone, appearance (light/dark), accent, reduce motion, hide amounts. `null` = Auto. The theme lists the keys the customer set in `overrides`, and the theme explanation starts with "You chose …". | `POST /api/me/style` |
| Declared signals | "We're expecting", "I'm going freelance", "I'm retiring", "I'm studying". Changes both persona models. `state: clear` removes one. | `POST /api/me/declare` |
| Card feedback | Dismiss, snooze (7 days), less like this, accept; `reset` clears all feedback. | `POST /api/me/feedback` |
| Consent | Commercial personalisation on or off. Off removes commercial cards from the feed. | `POST /api/me/consent` |

Suggestions come from two triggers. Once a customer has customised, the system does not silently move their tiles;
it proposes instead:

1. **Life changed.** A life event in the last 120 days (first invoice, baby, pension, first salary, mortgage) or a
   declared signal maps to tiles that are not on the home screen yet. Example: "You've started invoicing clients",
   proposing Tax reserve.
2. **Better hero.** The customer pinned a hero, but another hero now scores at least 0.25 higher.

## Customer profile (`profile/`)

One page with everything KBC knows and uses about the customer (`GET /api/me/profile`, `ui/ProfileSheet.tsx`, opened
from Personalise or by Kate). Three layers, and what the data may be used for:

| Layer | Content | The customer can |
|---|---|---|
| What you told us | Facts (below) with their source ("You told Kate on …" / "You entered this") and what each is used for; life changes declared to Kate | Edit, delete, "Forget everything I told Kate" |
| What we worked out | Persona mix with evidence (marked when part of it comes from a stated fact); goals KBC suggests, with evidence | "That's not me" / "Not for me" (corrections), undo |
| What it may be used for | One switch per purpose (below), with what changes when it is off | Switch on or off |
| Who else sees it | Partners with access and outside sources, summarised | Open the consent passport |

**Facts** (`profile/fields.py`) are closed vocabularies only: enums, small integers, booleans, sets of enums. There
is no free text, so nothing typed into a chat (or a prompt injection) can be stored and replayed into a model later.
Special categories of personal data (health, beliefs, politics, sexual orientation, union membership) have no field.

| Field | Values | Used by the engine |
|---|---|---|
| `partner` | single, partner, married | Kate, advisor |
| `children` | 0–12 | Persona (≥ 1 → young_family) |
| `cares_for_relative` | yes/no | Kate, advisor |
| `employment` | employee, self_employed, employee_side_job, student, job_seeker, retired | Persona |
| `housing` | renting, mortgage, own, with_parents | Kate, advisor |
| `risk_appetite` | careful, balanced, adventurous | Kate, advisor |
| `contact_channel` | app, phone, branch | Kate, advisor |
| `avoid_topics` | investing, insurance, credit | Feed: non-core, non-urgent cards whose title is on the topic leave the feed (counted in `hidden_count`). Goals: investing holds back `first_investment`, `retire_well`; insurance `travel`; credit `ev_switch`, `mobility`. Kate. |

**Purposes** (`profile_permissions`; `personalise_offers` is the older `customers.consent_personalization` column):

| Purpose | Default | When off |
|---|---|---|
| `personalise_offers` | on | Commercial cards are gated (as before) |
| `detect_life_events` | on | No goal candidates and no intent nudges; goals the customer starts still work |
| `kate_memory` | on | Kate proposes no saves; `PUT …/facts/{key}` with `via: "kate"` returns 403 |
| `kate_ai` | **off** | Kate uses rules only and nothing leaves KBC. Off by default because the AI mode sends data to an outside provider |
| `advisor_view` | on | `GET /api/advisor/profile/{username}` returns 403 (the attempt is still audited) |

**Corrections** (`profile_corrections`): `persona` + a persona id, or `goal` + a playbook id. Stamped with the effective
date like declared signals. Every change to facts, corrections and permissions is written to `audit_log` with the
field or purpose name, never the value.

## Kate (`engine/kate.py`, `engine/kate_agent.py`)

Kate answers from the same data the home screen is built from: the `HomeResponse` (with the recommender feed), the
`Features`, from the ecosystem the customer's goals, upcoming deadlines, forecasts and consents, and the customer's
profile. She states no fact the engine did not compute.

**Entry points:** the Kate tab (a proactive opener), "Ask Kate" on every card (the card is the context), the
`KateTile` on the home screen, and Kate nudges (see [ECOSYSTEM.md](ECOSYSTEM.md)).

**Two modes.** The rules (below) always work and need nothing outside KBC. The AI mode runs only when it is configured
(`KATE_LLM=openrouter` and `OPENROUTER_API_KEY`) **and** the customer allowed `kate_ai`. When it is configured but not
allowed, the rules fallback offers a "Let Kate use AI" button. Any error, timeout or failed check in AI mode → the
rules answer. `KateReply.source` says `rules` or `llm`.

**Rules: intents, checked in this order:**

| Intent | Examples | Typical proposal |
|---|---|---|
| Opener (empty message) | A detected goal ("I noticed something…"), the focus card, or the top feed card | `start_goal`, `open_card` |
| Sensitive details | Health, beliefs, … | None: "I won't keep it" |
| Deadlines and forecasts | "What's coming up?", "When is my VAT due?", "Will I owe social contributions?" | `start_goal` / `open_goal` |
| Why a goal was detected | "Why do you think so?" | `start_goal` |
| Data access | "Who has my data?", "Stop sharing with Setle" | `open_passport`, `revoke_consent` |
| What KBC knows | "What do you know about me?" | `open_profile` |
| Forget | "Forget what I said about my kids", "forget everything" | `forget_fact`, `forget_kate_facts` |
| Permissions | "Stop remembering things", "don't use AI" (whole words only) | `set_permission` |
| Style | "Make the text bigger", "dark mode", "hide amounts", "reset look" | `set_style`, `reset_style` |
| Corrections | "No offers about investing", "I'm not a freelancer", "not interested in buying a house" | `update_profile` (avoid_topics), `correct_inference` |
| Life changes | "We're expecting", "I'm going freelance" | `declare` (and the matching goal) |
| Goals | "We want to buy a house", "I'm behind on payments" (hard moments start with empathy) | `start_goal` / `open_goal` |
| Tiles | "Pin my subscriptions", "hide the scam shield" | `pin_tile`, `hide_tile` |
| About a card | Why, what should I do, coverage, remind me later, "that wasn't me" | `snooze_card`, `add_tile` |
| General | Persona and layout, balance and spending, subscriptions, next income, runway, scams, advisor | `pin_tile` |
| Facts mentioned | "We have two kids", "I rent", "I'm retired" (explicit phrases only), alone or next to any answer above | `update_profile` |
| Fallback | Anything else | Quick replies (and "Let Kate use AI" when available) |

**AI mode** (`kate_agent.py`): a model on OpenRouter (`KATE_MODEL`, default `anthropic/claude-sonnet-5.5`; requests
ask for providers that don't collect data) answers with tools, in up to 6 rounds within 45 s.

- **Reads:** `get_money_overview`, `get_feed`, `get_card`, `get_subscriptions`, `get_coming_up`, `get_goals`,
  `get_profile`, `get_data_access`, `get_home_setup`. They return what the engine already computed, with amounts
  pre-formatted. The model sees the first name, never the last name, ids or raw transactions.
- **Proposals:** `propose_profile_update`, `propose_forget`, `propose_correction`, `propose_permission`,
  `propose_tile`, `propose_style`, `propose_card_action`, `propose_goal`, `propose_life_change`, `propose_open`,
  `propose_revoke_access`, and `set_quick_replies`. Arguments are validated against the same registries as the
  endpoints (an invalid one returns an error to the model, not an action); `kate_memory` off blocks saves; at most 3.
- **Grounding:** the final text must be plain (no links, markup or code; `**` is stripped), at most 1,100 characters,
  and every number in it must appear in a tool result, the snapshot or the customer's own words. One repair round,
  then the rules answer.
- **Injection:** the system prompt says the snapshot and tool results are data. Counterparty and partner names only
  reach the model as JSON values in tool results; saved facts are enums.

**Proposals, not actions.** Kate returns at most 3 `KateAction`s: `pin_tile`, `hide_tile`, `add_tile`,
`snooze_card`, `dismiss_card`, `set_style`, `reset_style`, `declare`, `open_card`, `start_goal`, `open_goal`,
`update_profile`, `forget_fact`, `forget_kate_facts`, `correct_inference`, `set_permission`, `open_profile`,
`open_passport`, `revoke_consent`. The app shows each as a button. When the customer taps it, the app calls the
regular validated endpoint (layout-prefs, style, feedback, declare, profile, or the ecosystem goals and consents API).
Kate herself cannot change anything, so there is no new write path to secure.

## Time travel

Every customer endpoint takes an optional `?as_of=YYYY-MM-DD`. It is clamped to the first transaction at the low
end and to today (`DEMO_TODAY`, default 2026-10-20) at the high end, or to the end of Lotte's simulated future. No
date means today. Feedback, suggestion dismissals and declared signals are stamped with the effective date, and the
engine ignores them before that date. Pins and hides apply at every date.

`GET /api/me/timeline` returns the date range, `today`, and milestones from the customer's life events. The demo
panel uses them as ticks on the time slider.

## API (`main.py`, `schemas.py`)

All contracts are Pydantic models in `schemas.py`, mirrored in `frontend/src/api.ts`. Customer endpoints take the
customer from the session; there are no customer ids in customer URLs. Mutations accept `?as_of=` and return a fresh
`HomeResponse` (profile mutations return the `ProfileResponse`).

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/login` | `{username, password}` | Sets the session cookie; `{role, username}` |
| POST | `/api/logout` | – | `{ok}` |
| GET | `/api/me/session` | – | `{role, username}` |
| GET | `/api/me/home` | – | `HomeResponse` |
| GET | `/api/me/timeline` | – | `{min_date, max_date, milestones, today}` |
| POST | `/api/me/feedback` | `{card_key, card_type, decision: dismiss\|snooze\|less\|accept\|reset}` | `HomeResponse` |
| POST | `/api/me/consent` | `{consent_personalization}` | `HomeResponse` |
| POST | `/api/me/layout-prefs` | `{component, state: pinned\|hidden\|reset, position?: 0..20}` | `HomeResponse` |
| POST | `/api/me/layout-reset` | – | `HomeResponse` |
| POST | `/api/me/style` | `StylePrefs` | `HomeResponse` |
| POST | `/api/me/suggestion` | `{component, decision: accept\|dismiss}` | `HomeResponse` |
| POST | `/api/me/declare` | `{signal, state: set\|clear}` | `HomeResponse` |
| POST | `/api/me/kate` | `{message ≤ 500, card_key?, history ≤ 12 turns}` | `KateReply {reply, actions, quick_replies, source}` |
| PUT | `/api/me/tile-grid` | `{placements: {id: {slot, span: 1\|2}}, hidden: [id], slotCount}` (ids `card:<card_key>` or `widget:<Component>`) | `{ok}`; returned as `HomeResponse.tile_grid`, cleared by layout-reset |
| GET | `/api/me/profile` | – | `ProfileResponse` |
| PUT | `/api/me/profile/facts/{key}` | `{value, via: you\|kate}` | `ProfileResponse` (422 invalid value, 403 `via: kate` with memory off) |
| DELETE | `/api/me/profile/facts/{key}` | – | `ProfileResponse` |
| POST | `/api/me/profile/forget-kate` | – | `ProfileResponse` (deletes every fact saved from a chat) |
| POST | `/api/me/profile/corrections` | `{kind: persona\|goal, target, state: set\|clear}` | `ProfileResponse` |
| PUT | `/api/me/profile/permissions/{purpose}` | `{allowed}` | `ProfileResponse` |
| GET | `/api/advisor/profile/{username}` | – (advisor role) | `ProfileResponse`, or 403 when the customer didn't allow `advisor_view` |
| GET | `/api/me/customer-state[/{domain}]` | – | Customer State (see [CUSTOMER-STATE.md](CUSTOMER-STATE.md)) |
| GET | `/api/advisor/overview` | – (advisor role) | Persona distribution, card volume and scoring time projected to 2.3M customers |

The goals, consent, sources, nudges, partner webhook and ecosystem console endpoints are listed in
[ECOSYSTEM.md](ECOSYSTEM.md).

`HomeResponse` fields: `as_of`, `customer` (first name, language, consent), `persona_mix`, `feed_personas`, `layout`
(`theme`, `sections[{component, size, props, pinned}]`, `explanations`), `feed` (`cards`, `caught_up`,
`hidden_count`), `generated_at`, `llm_copy` (always false), `style`, `suggestions`, `gallery` (each item with its
`size`), `declared`, `tile_grid` (the customer's arrangement of the For you wall, or null). A `Card`
has `card_key`, `card_type`, `family`, `stage`, `title`, `body`, `eur_impact`, `due_date`, `confidence`,
`commercial`, `evidence`, `rank_explanation`, `score`, `cta` and `details`.

If `frontend/dist` exists, the backend also serves the built frontend, with a path check against directory
traversal. The OpenAPI docs are switched off.

## Security

| Control | Implementation |
|---|---|
| Sessions | HMAC-SHA256 signed cookie `kbc_session`: HttpOnly, SameSite=Lax, 8 h expiry, `Secure` when `COOKIE_SECURE=1`. Key from `SESSION_SECRET` (random per process if unset, so sessions end on restart). |
| Passwords | PBKDF2-SHA256, 200,000 iterations, random salt, constant-time compare. |
| Login rate limit | 10 failed attempts per 15 minutes, per username and per IP (in memory). |
| No IDOR | Customer endpoints use `require_customer` and the session's customer id only. Advisor endpoints use `require_advisor`. |
| Input validation | Every body and query is a Pydantic model: enums for components, decisions, signals and style values; `card_key` pattern `^[a-z0-9_:\-]{1,80}$`; known card types only; length limits on Kate messages and history; `as_of` is a date and clamped. |
| SQL | Bound parameters only. |
| Headers | CSP `default-src 'self'` (no inline scripts, `frame-ancestors 'none'`), `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`, a restrictive `Permissions-Policy`. |
| Output | The frontend renders text nodes only; there is no `dangerouslySetInnerHTML`. Unknown component names are skipped. |
| Untrusted text | Counterparty names are cleaned and capped before they reach card text, and reach the LLM only as quoted JSON data. |
| LLM | Only with the customer's `kate_ai` permission. Read tools over computed data; proposals validated against the registries; text validated or discarded (see Kate). It cannot change anything or add numbers. |
| Profile | Facts are closed vocabularies, validated against the registry; no field for special categories of personal data. |
| Kate rate limit | 30 messages per minute per user. |
| Audit | Declared signals, profile changes (field or purpose name only), advisor overview views and advisor profile looks (allowed or refused) are written to `audit_log`. |
| Data and secrets | Synthetic data only; `ground_truth` never leaves the server. Secrets come from environment variables (placeholders in `.env.example`; `.env` is gitignored). The app does not load `.env` itself. |

## Frontend (`frontend/src/`)

React 19 + TypeScript + Vite, with Framer Motion. In development Vite proxies `/api` to port 8000. With `?mock=1`
(or `npm run dev:mock`) the same UI runs on the demo engine in `demo/` instead: bundled fixtures per demo customer
(`demo-data/customers.json`) and browser-local state (`demo/store.ts`), behind the same interfaces (`data.ts`,
`ecosystem/client.ts`, `nudges/client.ts`). Design decisions behind the home: [FRONTEND-DECISIONS.md](FRONTEND-DECISIONS.md).

| Part | File(s) | What it does |
|---|---|---|
| Shell | `App.tsx` | Session check, login, customer switching, all mutations. An advisor login shows `EcosystemConsole` instead of the phone. |
| Demo panel | `demo/ControlPanel.tsx` | Customer switcher, time slider with milestone ticks (snaps near a milestone), Explain mode, consent switch, reset feedback, and the ecosystem controls (reset goals, play and reset nudges). |
| Phone | `Phone.tsx`, `PhoneScaler.tsx` | Top bar (name, date, notifications, Profile), the KBC logo with the primary account inside the ball (`components/AccountLogo.tsx`, opens the accounts screen), and the For you wall. Bottom nav: Home, Kate, Goals (Pay and Cards are placeholders). |
| For you wall | `feed/CardStack.tsx`, `feed/HomeTileGrid.tsx`, `feed/tileGrid.ts`, `feed/RecommendationTile.tsx`, `home.css` | One grid of feed cards (`card:<key>`) and home tiles (`widget:<Component>`), each a whole multiple of a square unit. Edit mode: drag a tile onto any spot, remove it (×), tap a free spot to place one, add rows. The arrangement is saved with `PUT /api/me/tile-grid`; placing a tile the home doesn't show yet pins it through layout-prefs so its data loads. |
| Goals tab | `ecosystem/GoalsScreen.tsx`, `ecosystem/RoadmapSheet.tsx` | Overview, goals shared with you (join or decline), goals in motion, every available goal (KBC's suggestions first) and achieved goals. Tapping one opens its roadmap (`GET /api/me/goals/preview/{id}`) with Approve & start or Not now. |
| Registry | `components/registry.tsx`, `components/*.tsx` | Component name → React component. Unknown names are logged once and skipped. |
| Theme | `theme.ts` | Density, tone, contrast, appearance and accent → CSS variables on the phone. |
| Feed | `feed/Card.tsx`, `feed/CardStack.tsx`, `feed/CaughtUp.tsx` | Swipe left to dismiss; a menu for snooze and "show me less"; ⓘ opens "Why am I seeing this?" with the evidence; "Ask Kate"; a detail sheet with metrics, savings planner, related cards and linked journey products. |
| Profile | `ui/ProfileSheet.tsx` | The hub behind the avatar: Settings & appearance, What KBC knows about you, Permissions & data (consent passport), Edit home, show/hide amounts. |
| Personalise | `ui/PersonaliseSheet.tsx`, `privacy.tsx` | Style settings with Auto, "Reset all to Auto". Hidden amounts show as `€ ••••` and are revealed for 8 seconds on tap. |
| Kate | `ui/KateSheet.tsx` | Chat with quick replies and action buttons. A tapped action runs through the same handlers as the rest of the app. |
| What KBC knows about you | `ui/AboutYouSheet.tsx`, `data.ts` (`profileData`) | The customer profile: three layers and the purpose switches; every change reloads the home screen. Opened from the Profile hub or by Kate. |
| Advisor profile view | `ecosystem/AdvisorProfilePanel.tsx` | In the ecosystem console: one demo customer's profile, or a notice when they haven't shared it. |
| Accounts | `accounts/` | Tapping the hero opens an accounts screen. Until the backend sends `accounts` on the hero (see [COMPONENT-PROPS.md](COMPONENT-PROPS.md)), it derives clearly labelled demo accounts and bookings from the home data. |
| Explain mode | `Phone.tsx` | A header with the feed persona mix and the theme explanation. |
| Demo engine | `demo/` (`data.ts`, `ecosystem.ts`, `nudges.ts`, `profile.ts`, `store.ts`), `demo-data/` | Backend-free mode for `?mock=1`. Signing in or switching customers keeps its store (it plays the backend's role); everything else in browser storage is cleared as usual. |
| UI tests | `tests/demo-mode.spec.ts`, `playwright.config.ts` | `npm test`: Playwright against the demo engine (fails on any `/api` request). |

## How the app surfaces the ecosystem

- **Feed cards** link to a goal journey (`details.playbook_id`); the CTA "Let KBC take care of it" starts it.
- **Goals tab**: detected goals ("Suggested for you"), every other goal, running and achieved journeys, household
  invites; each goal opens its roadmap first (`ecosystem/GoalsScreen.tsx`, `RoadmapSheet.tsx`, `JourneySheet.tsx`).
  The consent passport opens from Profile → Permissions & data (`PassportSheet.tsx`).
- **Kate** offers, starts and opens goals (`start_goal`, `open_goal`) and answers deadline and forecast questions.
- **Nudges** appear as a lock-screen banner and an inbox; their actions run through Kate's action handlers
  (`nudges/NudgeLayer.tsx`).
- **The advisor login** opens the ecosystem console (`ecosystem/EcosystemConsole.tsx`).

Details: [ECOSYSTEM.md](ECOSYSTEM.md).

## Tests and tools

Run `py -3.12 -m pytest` from `backend/`; there is one test file per engine module plus `test_api.py` and
`test_profile.py`. `test_kate.py` drives the AI mode with a scripted fake model (no network).
`py -3.12 -m scripts.evaluate_kate` runs scripted conversations against the rules, or with `--ai` against the
configured model.
`py -3.12 -m scripts.evaluate` measures persona and legacy card accuracy against the injected ground truth, plus
scoring throughput.
