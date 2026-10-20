---
title: KBC Adaptive Home design (round 1)
type: spec          # context | spec | decision | notes
status: review         # draft | review | final | outdated
incorporated: partial  # no | partial | yes | n/a
code_refs: [backend/app/, frontend/src/]
owner: team IF-ELSE
created: 2026-09-30
updated: 2026-10-20
source: round 1 repo, github.com/Senne-Meuleman/IF-ELSE
---

# KBC Adaptive Home — High-Level Design

> **Partly outdated (round 1).** §4–§8 (architecture, components, API, security) still describe the code, except
> that `engine/copywriter.py` was never built and the feed now runs on `customer_state/` + `recommender/` (see
> [CUSTOMER-STATE.md](CUSTOMER-STATE.md) and the README). §2, §3, §10, §11 and §12 are round 1 planning. For
> round 2, see [ROUND2-DESIGN.md](ROUND2-DESIGN.md).

> **Audience:** the coding agents and teammates building this project.
> **Status:** v2, 2026-09-30 (adds §6.9 customisation and §6.10 Kate) (Tectonic Hackathon, KBC challenge).
> **Rule for agents:** this document is the source of truth for scope, contracts and file ownership. If you must deviate, update this doc in the same change and say why.

---

## 1. The idea in one paragraph

One banking app that **looks and behaves differently depending on the customer's life situation**: a student, a young family, a freelancer, a retiree, or any blend of them. Two layers work together:

- **Adaptive layout (the frame):** *who you are* decides the shape of the home screen: which modules appear, which one is the hero, density, font size, tone of voice.
- **For You feed (the content):** *what is happening right now* decides which cards show up and in what order, e.g. *"Your car insurance renews in 12 days, here's an honest comparison."*

Both are **computed from signals** (transactions, products, age, life events), not picked from hand-designed templates. That is the core of the pitch: *"We never designed this screen. The system composed it."*

**Tagline:** *Persona sets the stage, moments fill it.*

---

## 2. Why this fits the challenge (and how we score)

KBC asks for "not a new feature, but a scalable personalization approach" that understands, supports and guides 2.3M customers.

| Judging criterion | Weight | How we win it |
|---|---|---|
| Creativity / originality | 30% | Generated layout (not templates), blended personas, life-stage **time travel**, a feed that **ends** ("You're all caught up") |
| Technical ability | 30% | Real signal detection on synthetic transactions, a transparent recommender (scoring + constraints + feedback loop), a layout planner with a validated JSON spec, smooth morphing UI |
| Fit to the challenge | 30% | Answers KBC's questions 1–5 directly: signals → recognition → automatic adaptation → cross-product → scale story |
| Security (Aikido) | 10% | Session-derived identity (no IDOR), role checks, strict schema validation, no LLM-generated markup or numbers, CSP, secrets in env |

Deliverables (from the participants guide): short description, **demo video < 3 min**, public GitHub repo with README, Aikido screenshots before and after fixes.

---

## 3. Scope

### MVP (must have for the video)
1. Synthetic data for ~1,000 customers + **3 hand-crafted demo customers** with long histories.
2. Persona inference → **persona mix** (weights, not a single label).
3. Card generators (≥ 6 card types, incl. insurance renewal) + ranker + card lifecycle.
4. Layout planner → layout spec JSON → rendered mobile home screen.
5. **Time-travel slider** (re-computes the home screen "as of" a date) and customer switcher.
6. "Why am I seeing this?" on every card **and** on the layout itself.
7. Feedback: dismiss / snooze / less like this / pin / hide → visibly changes the feed/layout.
8. Login with session cookie; customers can only see themselves.

### Stretch (only after MVP works end to end)
- LLM-written copy in persona tone + NL/FR (Gemini via Google Cloud credits), strictly validated.
- ElevenLabs "Read my day" voice summary (retiree mode).
- Advisor/portfolio view: persona distribution, card volumes, projection to 2.3M.
- Offline evaluation report (precision@5 against injected ground truth).

### Non-goals
- Real KBC data, real product catalogues, real prices. Everything is synthetic and labelled as such.
- LLM-generated UI code/HTML. The LLM never produces markup.
- Actually executing payments or product purchases (CTAs are simulated).
- Native mobile app. It's a web app in a phone frame.

---

## 4. Architecture

```
                 ┌────────────────────────── backend (FastAPI, Python) ──────────────────────────┐
                 │                                                                               │
 synthetic DB ──►│ load(customer, txs ≤ as_of) ─► features ─► persona mix ─┐                     │
 (SQLite)        │                                   │                     ├─► layout planner ──► layout spec (JSON)
                 │                                   └─► card generators ─► ranker ──► feed (cards)             │
                 │                                                    ▲         ▲                              │
                 │                         customer feedback/prefs ───┴─────────┘                              │
                 │                                                   (optional) copy writer (LLM) ──► validated│
                 └───────────────────────────────────────────────────────────────────────────────┬──────────┘
                                                                                                 │ GET /api/me/home
                                                                                                 ▼
                 ┌────────────────────────── frontend (React + Vite + TS) ───────────────────────────────────┐
                 │  Demo control panel (customer, time slider, explain mode)  │  Phone frame: renderer maps   │
                 │                                                            │  spec → registered components │
                 │                                                            │  with animated layout morphs  │
                 └────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Design principles**
1. **Pure core.** `features`, `persona`, `cards`, `ranker`, `layout` are pure functions: `(customer, txs, prefs, as_of) → result`. No I/O, no globals, easy to test and to batch at scale.
2. **Deterministic first, LLM optional.** Everything works with the LLM off. The LLM may only rewrite text; it never chooses amounts, dates or products.
3. **Explainable everywhere.** Every card and every layout decision carries `evidence[]` in plain language.
4. **Server is the source of truth.** The frontend renders the spec; it does not decide what to show.
5. **Time is a parameter.** Every computation takes `as_of`. This powers both the time-travel demo and card lifecycles.

### Tech stack
| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLite (stdlib `sqlite3`) | Fast to build; Pydantic gives us schema validation for free |
| Frontend | React + TypeScript + Vite, Framer Motion (`layout` animations) | The morph between layouts *is* the demo; Framer Motion's shared layout animations do this almost for free |
| Tests | pytest (backend), Vitest optional | Engine modules must have unit tests |
| LLM (stretch) | Gemini on Vertex AI (Google Cloud hackathon credits), model name via env `GEMINI_MODEL` | Partner tech, credits provided |
| Voice (stretch) | ElevenLabs TTS | Partner tech, retiree accessibility |

---

## 5. Repository layout and ownership

```
kbc-adaptive-home/
  README.md                 # how to run, demo logins, what's unfinished (required by rules)
  .env.example              # SESSION_SECRET, GEMINI_MODEL, GCP_PROJECT, ELEVENLABS_API_KEY, DEMO_PASSWORD
  .gitignore                # .env, *.db, node_modules, dist, __pycache__
  docs/DESIGN.md            # this file
  backend/
    requirements.txt
    app/
      main.py               # FastAPI app, middleware, routes            [owner: API agent]
      auth.py               # sessions, password hashing, role deps      [owner: API agent]
      db.py                 # connection + queries (bound params only)   [owner: API agent]
      schemas.py            # Pydantic models = THE contracts (sec. 7)   [owner: lead; change via PR only]
      engine/
        features.py         # transactions → feature dict                [owner: Engine agent]
        persona.py          # features → persona mix                     [owner: Engine agent]
        cards.py            # card generators                            [owner: Engine agent]
        ranker.py           # scoring, constraints, lifecycle, fatigue   [owner: Engine agent]
        layout.py           # component registry + planner               [owner: Layout agent]
        copywriter.py       # optional LLM copy + validation             [owner: Layout agent]
        pipeline.py         # build_home(customer, txs, prefs, as_of)    [owner: Engine agent]
    synth/
      generate.py           # synthetic customers + transactions         [owner: Data agent]
      demo_customers.py     # the 3 hand-crafted hero customers          [owner: Data agent]
    tests/                  # pytest, one file per engine module
    scripts/evaluate.py     # precision@k vs ground truth (stretch)
  frontend/
    src/
      api.ts                # typed client, mirrors schemas.py           [owner: Frontend agent]
      components/registry.tsx  # component name → React component
      components/*.tsx      # one file per registered component
      feed/                 # card, card stack, "all caught up"
      demo/ControlPanel.tsx # customer switcher, time slider, explain toggle
      theme.ts              # density/tone/contrast → CSS variables
```

Agents stay inside their owned files. Shared contracts live in `backend/app/schemas.py` and `frontend/src/api.ts` and must stay in sync.

---

## 6. Components in detail

### 6.1 Synthetic data (`synth/`)

**Why long histories:** annual events (insurance renewal, yearly subscriptions) need **≥ 13 months** of transactions. Generate **400 days** for regular customers and **~8 years** for demo customers.

**Tables**
```
customers(id, first_name, last_name, birth_year, city, language['nl'|'fr'], products JSON,
          consent_personalization INT, ground_truth JSON)      -- ground_truth = injected personas/events, never sent to customers
accounts(customer_id, balance_today)
transactions(id, customer_id, date, amount, category, counterparty)
users(id, username UNIQUE, password_hash, role['customer'|'advisor'], customer_id)
feedback(id, customer_id, card_key, card_type, decision, created_at)
audit_log(id, at, user_id, action, target)
```

**Transaction categories** (the only allowed values):
`salary, invoice_income, pension, student_income, allowance_from_parents, child_benefit, benefit, rent, mortgage, utilities, telecom, subscription, insurance_car, insurance_home, insurance_family, groceries, leisure, transport, childcare, baby, school, tuition, social_contribution, vat_payment, tax, savings_transfer, furniture, notary, healthcare, other`

**Scenarios to inject** (store in `ground_truth`):
| Scenario | Pattern |
|---|---|
| student | age 18–25, `student_income` (irregular, small), `allowance_from_parents`, `tuition` once a year, small rent (kot) |
| young_family | `childcare`, `baby`, `child_benefit` monthly income |
| freelancer | `invoice_income` from 3–6 counterparties at irregular dates/amounts, quarterly `vat_payment`, quarterly `social_contribution` |
| retiree | age 65+, monthly `pension`, more `healthcare` |
| insurance_renewal | yearly `insurance_car` payment; renewal date = last payment + 365 days |
| price_increase | a `subscription` that rises (e.g. €13.99 → €17.99) in the last 60 days |
| duplicate_charge | same counterparty, same amount, within 48h, in the last 14 days |
| cashflow_squeeze | variable spending +80% in the last 30 days |
| idle_cash | balance > 6× monthly spending, no savings product |

Many customers get **2 scenarios**, so blends exist naturally.

**Demo customers** (`demo_customers.py`, fixed seed, usernames below, password from env `DEMO_PASSWORD`, default `demo` for local use only):
| Username | Story | What it shows |
|---|---|---|
| `lotte` | 2018 student in Leuven → 2021 first job → 2022 moves in, mortgage → 2024 baby → 2026 goes freelance | **Time travel**: the same person passes through every persona |
| `sara` | Freelancer **and** young mother, car insurance renewing in 12 days, Netflix price increase | **Blend** + the insurance card |
| `jan` | 71, retiree, pension, a duplicate charge, idle cash | Retiree layout (large, calm, high contrast), voice mode |

### 6.2 Features (`engine/features.py`)

`compute_features(customer, txs, balance, as_of) -> Features`, using only transactions with `date <= as_of`.
Balance at `as_of` = `balance_today − Σ amount(txs after as_of)`.

Examples: `age`, `monthly_income_avg_90d`, `income_regularity` (coefficient of variation of monthly income), `income_sources` (distinct payers, 180d), `has_child_signals`, `has_pension`, `has_vat_payments`, `runway_days` (days until balance < 0 at current burn), `next_income_date` (estimate), `recurring_payments[]` (counterparty, amount, period, last_date), `idle_cash_eur`.

### 6.3 Persona mix (`engine/persona.py`)

Personas: `student`, `young_professional`, `young_family`, `freelancer`, `retiree`.

Each persona has a scoring function over features, returning a raw score 0..1 and **evidence strings**. Normalize to weights summing to 1, drop weights < 0.15, renormalize.

```json
{ "persona_mix": [
    {"persona": "freelancer",   "weight": 0.58, "evidence": ["Income from 4 different clients in the last 6 months", "Quarterly VAT payments to FOD Financiën"]},
    {"persona": "young_family", "weight": 0.42, "evidence": ["Monthly Groeipakket child benefit since March 2024", "Regular payments to a daycare"]}
]}
```

Rules of thumb (weights are tuning knobs, keep them in one dict at the top of the file):
- **student:** age < 26 AND (`student_income` or `allowance_from_parents` or `tuition` in last 12 months)
- **young_professional:** steady `salary` (low variation), age < 36, no child signals. This is also the fallback persona.
- **young_family:** `child_benefit` or `childcare`/`baby`/`school` in the last 6 months
- **freelancer:** `invoice_income` from ≥ 2 payers, or any `vat_payment`/`social_contribution`
- **retiree:** `pension` income, or age ≥ 67

### 6.4 Cards (`engine/cards.py`)

Each generator: `(features, customer, txs, as_of) -> list[Card]`. Generators never rank; they only propose.

**Card families and MVP generators**
| Family | Generator | Example | Commercial? |
|---|---|---|---|
| ⏰ deadline | `insurance_renewal` | "Your car insurance with {insurer} renews on 12 Oct. Same coverage at KBC: €14/month less. Here's what differs." | yes |
| ⏰ deadline | `vat_reserve` (freelancer) | "VAT return due 20 Oct. Set aside ~€1,840." | no |
| 🔍 anomaly | `price_increase` | "Netflix went from €13.99 to €17.99." | no |
| 🔍 anomaly | `duplicate_charge` | "Two identical charges of €64.20 at Colruyt on 27 Sep." | no |
| 📉 forecast | `runway` / `cashflow_squeeze` | "At this pace you'll be at −€80 on the 27th." | no |
| 💡 opportunity | `idle_cash` | "€6,400 has been idle for 4 months." | yes |
| 🎉 milestone | `life_event` (first salary, baby, first invoice, pension start) | "First salary! 3-step starter plan." | no |
| 🛡️ protection | `scam_awareness` (retiree weighting) | "Scam SMS wave this week: KBC never asks for your card code." | no |

**Honesty rule for comparisons:** any comparison card must list coverage differences, not only price. Never claim a competitor's policy terms; say *"compared to what you pay now"*.

**Card lifecycle** (computed from `due_date` and `as_of`):
| Stage | Condition | UI |
|---|---|---|
| `early` | > 14 days before due | neutral |
| `soon` | 4–14 days | amber accent |
| `urgent` | ≤ 3 days | red accent, pinned high |
| `expired` | past due | not shown |

Cards without a due date use `stage = "info"`.

### 6.5 Ranker (`engine/ranker.py`)

```
score = persona_fit × (0.40·urgency + 0.30·impact + 0.20·confidence + 0.10·novelty) × fatigue
  urgency    : urgent 1.0 | soon 0.7 | early 0.4 | info 0.3
  impact     : min(1, log10(1 + |eur_impact|) / 3.5)
  persona_fit: Σ_persona weight(persona) × affinity[card_type][persona]   (affinity table 0..1)
  novelty    : 1.0 if the card is new since last visit, else 0.5
  fatigue    : Π over past feedback on this card_type: less → ×0.3, dismiss → ×0.8 (recovers after 30 days)
```

**Hard constraints** (applied after scoring, in this order):
1. `commercial` cards require `consent_personalization`; drop them otherwise.
2. `snooze` hides that exact `card_key` for 7 days; `dismiss`/`accept` hide it permanently.
3. Service cards at stage `urgent` always come first.
4. At most **1 commercial card per 3 cards** shown.
5. At most **2 cards of the same family**.

Output: ordered `Card[]` with `rank_explanation` (e.g. `"urgent · €1,840 impact · fits freelancer"`).

### 6.6 Layout planner (`engine/layout.py`)

**Component registry.** Only these names may appear in a layout spec. Each has persona affinities (0..1) and a props builder that fills **real data from features**.

| Component | Purpose | Strongest persona |
|---|---|---|
| `BalanceHero` | Balance + spark line | young_professional |
| `RunwayHero` | "€212 left, 9 days until your next income" | student |
| `FamilyBudgetHero` | Month budget incl. childcare, child benefit | young_family |
| `TaxReserveHero` | Income this quarter vs VAT/social contributions to reserve | freelancer |
| `PensionHero` | "Pension received ✓", upcoming bills, calm tone | retiree |
| `ForYouFeed` | The ranked cards (always present) | all |
| `QuickActions` | 3–4 persona-specific actions | all |
| `UpcomingBills` | Next 14 days of recurring payments | young_family, retiree |
| `SplitBills` | Roommate/pay-request shortcuts | student |
| `InvoiceTracker` | Unpaid/paid invoices, income smoothing | freelancer |
| `SavingsGoal` | Goal progress (e.g. child savings) | young_family, young_professional |
| `ScamShield` | Safety tips + "call my bank" | retiree |
| `AdvisorContact` | Human contact, prominent for sensitive moments | retiree, anyone in cash-flow stress |
| `SpendingByCategory` | Donut/bar of this month | young_professional |

**Planning algorithm (deterministic):**
1. `component_score = Σ_persona weight × affinity + signal_boosts` (e.g. cash-flow stress boosts `AdvisorContact` and `RunwayHero`).
2. Hero = the highest-scoring `*Hero` component.
3. `ForYouFeed` is always placed directly after the hero.
5. Theme from the dominant persona, with overrides: retiree weight ≥ 0.5 → `density: large`, `contrast: high`.
6. Every decision appends a reason to `layout.explanations[component]`.

**Theme tokens**
| | student | young_professional | young_family | freelancer | retiree |
|---|---|---|---|---|---|
| density | compact | comfortable | comfortable | compact | large |
| tone | casual | neutral | warm | business | formal |
| contrast | normal | normal | normal | normal | high |

### 6.7 Copywriter (optional LLM, `engine/copywriter.py`)

- Input: **structured** card/layout data (type, amounts, dates, persona, tone, language). Never raw transaction lines.
- Output: JSON `{card_key: {title, body}}` plus `greeting`, validated with Pydantic.
- **Validation:** max lengths; **every number in the output must appear in the input** (else discard); no URLs, no markup. On any failure or a timeout > 3s, fall back to deterministic templates.
- **Prompt injection:** counterparty names are attacker-controllable (anyone can send €0.01 with a crafted name). Pass them as quoted data fields, strip control characters, cap at 40 chars, and rely on the output validation above.
- Cache by `(customer_id, as_of, layout_hash, language)`. Env flag `LLM_COPY=on|off` (default `off`).

### 6.8 Frontend

- **Layout:** left = **demo control panel** (customer switcher, time-travel slider with milestone ticks from `/api/me/timeline`, "Explain" toggle, LLM toggle). Right = **phone frame** (390×844) rendering the spec.
- **Renderer:** `registry[component]` → React component. Unknown component names are ignored and logged (never crash).
- **Morph:** wrap sections in Framer Motion `motion.div` with `layout` and `layoutId={component}` so a changed spec *animates* into the new arrangement. Theme changes animate via CSS variable transitions. This is the money shot; give it polish time.
- **Cards:** swipe left = dismiss, long-press/menu = snooze / less like this, tap ⓘ = evidence drawer. Stage colors from §6.4.
- **Explain mode:** every section shows a small badge with its `explanations[component]`, and a header chip lists the persona mix ("58% freelancer · 42% young family").
- **Safety:** render text with React text nodes only; **never** `dangerouslySetInnerHTML`.
- **Voice (stretch):** a "Read my day" button calls `POST /api/me/voice`, which uses ElevenLabs server-side (API key never in the browser) and returns audio.

### 6.9 Customisation (v2): the system proposes, the customer decides

The home screen stays **adaptive by default**; customisation is a sparse layer of overrides on top. That keeps the
pitch intact ("we never designed this screen") while giving the customer the last word.

**Layout overrides** (`layout_prefs`, planner in `engine/layout.py`)
- **Pin** a tile: it keeps its **slot** (`position` = index among the tiles below the feed) while everything else
  keeps adapting around it. Demo: pin a tile, drag the time slider, and the pinned tile stays put as the layout morphs.
- **Pin a hero**: the pinned hero stays the main tile. Only one hero can be pinned (pinning another releases the first).
- Pins beyond the density budget are still shown (the budget grows to fit them); `position: null` = first free slot.
- **Reset to adaptive** (`/api/me/layout-reset`) removes all pins, hides and suggestion dismissals.

**Suggestions** (`HomeResponse.suggestions`): once the customer has customised, the system does not silently move
their tiles. Instead it *proposes*:
1. *Life changed*: a life event in the last 120 days (first invoice, baby, pension, first salary, mortgage) or a
   **signal the customer told Kate** maps to tiles that aren't on the home screen yet. "You've started invoicing
   clients. Add Tax reserve?"
2. *Better hero*: the customer pinned a hero, but another scores ≥ 0.25 higher.
Accept = pin (as hero if it is one). "Not now" = snoozed 90 days. Hidden tiles are never suggested.

**Tile gallery** (`HomeResponse.gallery`): every tile with label, description, planner score and the same plain-language
reason as Explain mode. The top 3 available tiles are marked "Suggested for you".

**Style overrides** (`style_prefs`, `/api/me/style`): density, contrast, tone, appearance (light/dark), accent,
reduce motion, hide amounts. Every setting defaults to **Auto** (`null`) = the persona-driven theme. The effective
theme carries `overrides[]`, and the theme explanation starts with "You chose …", so Explain mode stays truthful.

**Declared signals** (`declared_signals`, `/api/me/declare`): "we're expecting", "I'm going freelance", "I'm retiring",
"I'm studying". Each adds a raw score to one persona (`persona.py`, `SCORE["declared"]`) with evidence
"You told Kate on 30 Sep 2026 that …". It applies from the day it was said, so time travel respects it. Clearable.

### 6.10 Kate: the conversational side of the engine (`engine/kate.py`)

Kate answers from the **same grounded data** the home screen is built from (HomeResponse + Features), so she can explain
any card, the persona mix and the layout, and she can act on the same preference endpoints.

- **Entry points**: the Kate tab (proactive opener about the top card), "Ask Kate" on every card (card as context), and
  the `KateTile` on the home screen.
- **Deterministic first**: intent rules (card questions: why / what should I do / coverage / remind me; style
  requests; pin/hide tiles; declared life changes; balance, spending, subscriptions, next income, scams, advisor;
  "why does my app look like this"). All facts come from the engine; no numbers are invented.
- **Proposals, not actions**: Kate returns `KateAction`s (`pin_tile`, `hide_tile`, `set_style`, `snooze_card`,
  `declare`, …). The app shows a button; the customer taps; the app calls the regular validated endpoint. Kate herself
  can never change state, so there is no new write path to secure.
- **Optional LLM** (`KATE_LLM=gemini`): may only **rephrase** the rules answer. Input is a grounded JSON context (counterparty
  names as quoted data); output must be ≤ 1,100 chars, no links/markup, and **every number must occur in the context**.
  Any failure or timeout (4 s) → the deterministic answer. `KateReply.source` says which one you got.
- **Security**: session-derived customer only, `message` ≤ 500 chars, `card_key` pattern-validated, history ≤ 12 turns,
  30 messages/minute per user, declared signals written to `audit_log`.

---

## 7. API contracts

All customer endpoints derive the customer from the session. **No customer IDs in customer URLs.**

| Method | Path | Body / query | Returns |
|---|---|---|---|
| POST | `/api/login` | `{username, password}` | sets HttpOnly cookie, `{role}` |
| POST | `/api/logout` | – | `{ok}` |
| GET | `/api/me/home` | `?as_of=YYYY-MM-DD` (optional, clamped to the customer's data range, not in the future) | `HomeResponse` |
| GET | `/api/me/timeline` | – | `{min_date, max_date, milestones: [{date, label}]}` |
| POST | `/api/me/feedback` | `{card_key, card_type, decision: dismiss\|snooze\|less\|accept\|reset}` | fresh `HomeResponse` |
| POST | `/api/me/consent` | `{consent_personalization: bool}` | fresh `HomeResponse` |
| POST | `/api/me/layout-prefs` | `{component, state: pinned\|hidden\|reset, position?: 0..20}` (v2: position) | fresh `HomeResponse` |
| POST | `/api/me/layout-reset` | – | fresh `HomeResponse` (all pins/hides cleared) |
| POST | `/api/me/style` | `StylePrefs` (`null` = Auto) | fresh `HomeResponse` |
| POST | `/api/me/suggestion` | `{component, decision: accept\|dismiss}` | fresh `HomeResponse` |
| POST | `/api/me/declare` | `{signal: expecting_baby\|going_freelance\|retiring\|studying, state: set\|clear}` | fresh `HomeResponse` |
| POST | `/api/me/kate` | `{message ≤500, card_key?, history ≤12}` | `KateReply {reply, actions[], quick_replies[], source}` |
| POST | `/api/me/voice` (stretch) | – | `audio/mpeg` |
| GET | `/api/advisor/overview` (stretch) | role = advisor | persona distribution, card volume, scoring time, projection to 2.3M |

**`HomeResponse`** (define in `schemas.py`; mirror in `api.ts`):
```jsonc
{
  "as_of": "2026-09-30",
  "customer": {"first_name": "Sara", "language": "nl"},
  "persona_mix": [{"persona": "freelancer", "weight": 0.58, "evidence": ["..."]}],
  "layout": {
    "version": 1,
    "theme": {"density": "compact", "tone": "business", "contrast": "normal"},
    "sections": [
      {"component": "TaxReserveHero", "size": "hero", "props": {"quarter_income_eur": 8760, "reserve_eur": 1840, "due_date": "2026-10-20"}},
      {"component": "ForYouFeed", "size": "full", "props": {}},
      {"component": "InvoiceTracker", "size": "half", "props": {"unpaid": 2, "unpaid_eur": 3150}}
    ],
    "explanations": {"TaxReserveHero": "You're mainly self-employed (58%), and your VAT return is due in 20 days."}
  },
  "feed": {
    "cards": [{
      "card_key": "insurance_renewal:ag-insurance-car",   // stable id, ^[a-z0-9_:-]{1,80}$
      "card_type": "insurance_renewal",
      "family": "deadline",
      "stage": "soon",
      "title": "Your car insurance renews in 12 days",
      "body": "…",
      "eur_impact": 168,
      "due_date": "2026-10-12",
      "confidence": 0.85,
      "commercial": true,
      "evidence": ["Yearly payment of €612 to AG Insurance on 12 Oct 2025"],
      "rank_explanation": "soon · €168/yr impact · fits every persona",
      "cta": {"label": "Compare coverage", "action": "open_compare"}
    }],
    "caught_up": true,
  },
  "generated_at": "2026-09-30T14:02:11Z",
  "llm_copy": false
}
```

---

## 8. Security requirements (Aikido = 10%, and it's a bank)

1. **AuthN:** HMAC-signed session cookie, `HttpOnly`, `SameSite=Lax`, 8h expiry; PBKDF2-SHA256 (≥ 200k iterations) password hashes; login rate-limit per username and per IP.
2. **AuthZ / IDOR:** customer endpoints take the customer from the session only. Advisor endpoints check the role server-side and write to `audit_log`.
3. **Input validation:** every body/query is a Pydantic model with patterns and length limits (`card_key`, `component` ∈ registry, `decision` enum, `as_of` a date clamped to the allowed range).
4. **SQL:** bound parameters only. No string-formatted SQL, ever.
5. **Output:** security headers + CSP (`default-src 'self'`; allow the API origin in dev only). The frontend never injects HTML.
6. **LLM:** see §6.7. The LLM cannot add components, change numbers, or emit links/markup. Validated or discarded.
7. **Secrets:** only via env / `.env` (gitignored). `.env.example` has placeholders. GCP and ElevenLabs keys stay server-side.
8. **Data:** synthetic only; `ground_truth` is never returned by customer endpoints.
9. **Process:** connect the repo to Aikido early (baseline scan), fix, rescan, and screenshot both.

---

## 9. Scale story (one slide, one sentence in the video)

- The engine is pure functions per customer → embarrassingly parallel batch.
- **Nightly batch + event triggers** (salary received, new recurring payment, due date entering a new stage) recompute `HomeResponse` and cache it. The app open is a cache read.
- The LLM runs only on cache misses, and only for copy; templates cover 100% of cases.
- Measure it: time to score all synthetic customers, and extrapolate to 2.3M (show it in the advisor view).

---

## 10. Demo script (< 3 min)

| Time | Beat |
|---|---|
| 0:00–0:20 | Hook: "2.3 million customers, one app. Why does everyone see the same home screen?" |
| 0:20–1:20 | Log in as `lotte`, drag the **time slider** 2018 → 2026: student runway → first salary milestone → family budget → freelancer tax reserve. The layout **morphs** at each step. |
| 1:20–1:50 | Switch to `sara`: a **blend** nobody designed. Turn on explain mode: "58% freelancer · 42% young family". Open the car-insurance card → evidence → honest comparison. |
| 1:50–2:10 | Swipe away a card, choose "less like this" → the feed re-ranks. Scroll to "✓ You're all caught up". |
| 2:10–2:30 | Switch to `jan`: large text, high contrast, scam shield, "Read my day" (voice, if built). |
| 2:30–3:00 | Under the hood: signals → persona mix → cards/ranker → layout spec → renderer. Scale + security in one line each. Close: "Persona sets the stage, moments fill it." |

---

## 11. Work plan for agents

Contracts first (§7 `schemas.py` + `api.ts`), then the tracks can run in parallel.

| # | Track | Agent | Depends on | Done when |
|---|---|---|---|---|
| 0 | Scaffold: repo layout, `schemas.py`, `api.ts`, README stub, `.env.example`, `.gitignore` | Lead | – | Both apps start; `/api/me/home` returns a hard-coded valid `HomeResponse` |
| 1 | Synthetic data + 3 demo customers | Data | 0 | `python -m synth.generate` builds the DB; each scenario is present; demo stories are visible in transactions |
| 2 | Features + persona mix | Engine | 0 (fixtures), 1 | Unit tests: `lotte` persona changes across 5 dates; `sara` is a blend |
| 3 | Card generators + ranker + lifecycle | Engine | 2 | Unit tests per generator; the insurance card moves early → soon → urgent as `as_of` advances; constraints hold |
| 4 | Layout planner | Layout | 2 | Unit tests: each demo customer/date gives a different hero; output always validates against the schema |
| 5 | API: auth, home, feedback, prefs, timeline | API | 0, then 2–4 | Endpoints behave per §7; IDOR test: a customer can't reach another's data |
| 6 | Frontend: phone frame, registry, cards, control panel, morph animations | Frontend | 0 (mock JSON), then 5 | Time slider morphs smoothly; feedback visibly changes the feed; explain mode works |
| 7 | Stretch: LLM copy, voice, advisor view, evaluate.py | any | MVP done | Behind flags; MVP still works with flags off |
| 8 | Hardening + Aikido scan + README + video | Lead | MVP done | Aikido before/after screenshots; README covers run, logins, unfinished parts |

**Conventions for all agents**
- Pure engine functions get `as_of` passed in; never call `date.today()` inside the engine.
- All user-visible strings in English for MVP (NL/FR is stretch via copywriter); amounts formatted `€1.840` Belgian style in the frontend.
- New card type = generator + affinity row + template + unit test, all in one change.
- New component = registry entry (backend) + React component + affinity row, in one change.
- Keep weights and thresholds in named constants at the top of each module, as they're our tuning knobs during demo prep.
- Don't commit the DB, `.env`, or any API key.

---

## 12. Open questions

1. Final quarterly VAT due date for Belgium: confirm the day of month before hard-coding it (keep it a constant `VAT_DUE_DAY`).
2. Do we show KBC insurance prices at all, or only "estimated savings" ranges? (Safer: ranges, labelled "illustrative".)
3. Language: is an NL version of the demo worth it for the jury (LLM stretch), or keep English?
4. Team split: who owns which track in §11?
