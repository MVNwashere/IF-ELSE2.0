# IF-ELSE2.0: KBC Adaptive Home, round 2

Tectonic Hackathon final, 20 October 2026 (KBC track). This repo continues our round 1 project,
**KBC Adaptive Home** ([github.com/Senne-Meuleman/IF-ELSE](https://github.com/Senne-Meuleman/IF-ELSE)),
for the round 2 challenge: *move customers from intent to successful action, with KBC and its partners*.

## What comes from round 1 and what's new

- **From round 1 (30 Sept 2026):** everything in `backend/`, `frontend/` and the docs `DESIGN.md`,
  `KBC-QUESTIONS.md`, `CUSTOMER-STATE.md`, `COMPONENT-PROPS.md` and `feed-specs/`. Imported as-is on 20 Oct.
- **New today:** see the git history after the commit "Import round 1 code and docs", and `docs/` files created on
  2026-10-20.

## Structure

| Folder      | Purpose                         |
|-------------|---------------------------------|
| `backend/`  | FastAPI engine and API (round 1)|
| `frontend/` | React + Vite phone app (round 1)|
| `data/`     | Data files (synthetic only)     |
| `docs/`     | Design docs                     |
| `notes/`    | Working notes                   |

## Setup

```bash
cp .env.example .env   # then fill in values
```

---

*Round 1 README follows.*

## KBC Adaptive Home

*Persona sets the stage, moments fill it.*

One banking app that **looks and behaves differently depending on the customer's life situation**. Nobody designed
the home screen you see: the system composed it from signals in the customer's own transactions.

- **Adaptive layout** (who you are): a persona mix (student, young professional, young family, freelancer, retiree)
  decides which modules appear, which is the hero, density, contrast and tone.
- **For You feed** (what is happening now): nine soft personas and the supplied ten core cards plus 100 targeted
  catalogue definitions, ranked from Customer State observations, urgency, consent and feedback. Cards whose
  required data is unavailable are held back. The feed **ends**.
- **Explainable and controllable**: "Why am I seeing this?" on every card and every section; dismiss, snooze,
  less like this, pin, hide, consent switch.
- **Time travel**: the same customer, recomputed "as of" any date over 8 years. Watch the layout morph.
- **Yours to shape** (v2): pin tiles to a slot (they stay put while the rest adapts), hide tiles, add from a tile
  gallery, restyle (text size, contrast, dark mode, tone, accent, reduce motion, hide amounts), every setting with
  an **Auto** default. When life changes, the app **suggests** a tile instead of silently rearranging yours.
- **Kate** (v2): a chat assistant grounded in the same signals. "Ask Kate" on every card, a proactive opener, and
  she can *propose* changes (pin a tile, bigger text, "we're expecting") that you confirm with one tap.

Built for the Tectonic Hackathon (KBC challenge). **All data is synthetic.** See `docs/DESIGN.md` for the design and
`docs/KBC-QUESTIONS.md` for how this answers KBC's five questions.

### Run it

Backend (Python 3.12):

```bash
cd backend
py -3.12 -m pip install -r requirements.txt        # or: python -m pip install ...
py -3.12 -m synth.generate --n 1000 --seed 42       # builds backend/kbc.db (also runs automatically on first start)
py -3.12 -m uvicorn app.main:app --reload --port 8000
```

Frontend (Node 22):

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173 (proxies /api to :8000)
```

Or build once and let the backend serve it: `npm run build`, then open http://localhost:8000.

Standalone UI without a backend: http://localhost:5173/?mock=1

### Demo logins

Password for all: `demo` (override with `DEMO_PASSWORD` in `.env`).

| Username | Story | What it shows |
|---|---|---|
| `lotte` | 2018 student in Leuven → 2021 first job → 2022 mortgage → 2024 baby → 2026 freelance | **Time travel**: drag the slider and watch the same person pass through every persona |
| `sara` | Freelancer **and** young mother; car insurance renews in 12 days; Netflix price increase | A **blend** nobody designed, the honest insurance comparison |
| `jan` | 71, retiree; pension; a duplicate charge; idle cash | Retiree layout: large, calm, high contrast, scam shield |
| `advisor` | Portfolio view | Persona distribution, card volume, scoring time projected to 2.3M customers |

Regular synthetic customers: `c1` … `c1000`.

### How it works

```
transactions ─► features ─► existing persona mix ─► layout planner ─► layout spec ─┐
       └──────► Customer State ─► nine personas + catalogue recommender ─► feed ───┤
                                                                  feedback ─────────┘► phone renderer
```

| Module | What it does |
|---|---|
| `backend/synth/` | ~1,000 synthetic customers with injected scenarios + 3 hand-crafted demo customers (8-year histories) |
| `backend/app/engine/features.py` | transactions → features (income pattern, recurring payments, runway, idle cash, life events) |
| `backend/app/engine/persona.py` | features → weighted persona mix with plain-language evidence |
| `backend/app/engine/cards.py` | 13 card generators, each with evidence, impact, lifecycle stage |
| `backend/app/engine/ranker.py` | `persona_fit × (urgency, impact, confidence, novelty) × fatigue`, then hard constraints |
| `backend/app/engine/layout.py` | component registry + deterministic planner → validated layout spec; pins, style overrides, tile gallery, suggestions |
| `backend/app/customer_state/` | normalized banking observations, metrics, changes, uncertainty and cached snapshots |
| `backend/app/recommender/` | nine persona scores, ten core card generators, 100 imported targeted card definitions, eligibility and feed ranking |
| `backend/app/engine/kate.py` | Kate: grounded intent rules → reply + proposed actions; optional Gemini rephrasing with number validation |
| `backend/app/main.py` | FastAPI: session auth, `/api/me/*` from session only, feedback, prefs, consent, advisor overview |
| `frontend/` | React + Vite + Framer Motion: control panel, phone frame, registry renderer, animated morphs |

Tests: `cd backend && py -3.12 -m pytest` (including recommender, Customer State, feedback and API isolation).

Offline evaluation against the injected ground truth: `cd backend && py -3.12 -m scripts.evaluate`

Customer State: see [docs/CUSTOMER-STATE.md](docs/CUSTOMER-STATE.md) for its data model, calculations,
synthetic scenarios, persistence and `/api/me/customer-state` endpoints. The home feed now consumes its snapshots;
the existing layout planner and Kate still use the earlier feature pipeline.

The three supplied specifications are preserved in [docs/feed-specs](docs/feed-specs). After changing the targeted
card specification, run `python backend/scripts/import_feed_catalogue.py` to rebuild the checked-in JSON catalogue.
The feed uses observed values rather than the example amounts written in the specifications. Tapping a feed card
opens its available breakdown, explanation and related cards. Goals and emergency-buffer cards include an adjustable
savings estimate. Feedback persists and immediately re-ranks the feed.

| Metric (1,000 synthetic customers, seed 42) | Value |
|---|---|
| persona recall / dominant-persona precision | 0.94 / 1.00 |
| feed precision@5 / recall vs injected events | 0.66 / 0.85 |
| scoring time per customer (laptop, single core) | ≈ 3 ms |

Remaining misses are mostly by design: renewals more than 45 days out are not shown yet, and a price increase that
has not been charged yet cannot be detected.

### Security (Aikido)

- HMAC-signed `HttpOnly` `SameSite=Lax` session cookie (8h); PBKDF2-SHA256 200k-iteration password hashes;
  login rate limit per username and per IP.
- Customer endpoints take the customer from the session only: no customer ids in customer URLs (no IDOR).
- Every input is a Pydantic model with patterns, enums and length limits. SQL uses bound parameters only.
- Security headers + CSP; the frontend renders text nodes only, never HTML.
- Advisor endpoints check the role server-side and write to `audit_log`.
- Kate can't change anything herself: she returns proposed actions, which the app runs through the same validated
  endpoints after the customer taps. Messages ≤ 500 chars, 30/min per user; LLM output (if enabled) must be plain
  text whose numbers all appear in the grounded context, else the deterministic answer is used.
- Secrets only via `.env` (see `.env.example`); `ground_truth` is never returned to customers.

### Scale story

The engine is pure functions per customer, so it is embarrassingly parallel. In production: nightly batch +
event triggers (salary received, due date entering a new stage) recompute and cache each `HomeResponse`; the app
open is a cache read. The advisor overview times scoring the whole synthetic portfolio and extrapolates to 2.3M.

### Demo script (< 3 min)

1. Log in as `lotte`, turn on **Explain mode**, drag the time slider from 2018 to 2026: the layout changes with
   her life, while the feed changes its core values, persona mix and eligible targeted cards.
2. Switch to `sara`: the feed combines parent, household and self-employed signals. Open a core card for its
   observed breakdown and related cards; see the business and family recommendations beneath the core cards.
3. Swipe a card away or choose "less like this": the feed re-ranks. Scroll to "✓ You're all caught up".
4. Switch to `jan`: large text, high contrast, pension hero and a simpler feed with bill calendar and safety guidance.
5. **Make it yours**: as `lotte`, tap Edit, pin a tile, then drag the slider: the pinned tile stays while the rest
   morphs. At Jan 2026 a banner suggests "You've started invoicing clients. Add Tax reserve?". Open settings and
   pick dark mode or large text; Explain mode now says "You chose …".
6. Ask Kate "we're expecting a baby": she proposes to take it into account; one tap shifts the persona mix, with
   the evidence "You told Kate on …".
7. Log in as `advisor` and call `GET /api/advisor/overview` for the scale numbers.

### Not done / honest limitations

- Rules, not ML: persona scoring and ranking are transparent rule-based models by design; the contracts allow
  swapping in trained models.
- LLM copywriting (Gemini) and voice (ElevenLabs) are designed (see `docs/DESIGN.md` §6.7) but not wired in;
  everything works with deterministic templates. Kate's optional Gemini layer (`KATE_LLM=gemini`, needs
  `pip install google-genai` and credentials) is implemented but untested against the live API; Kate runs on
  deterministic rules by default.
- Offers and prices in comparison cards are illustrative placeholders, not KBC products.
- The catalogue retains all 100 concepts. Cards that need unavailable inputs (live rates, verified holdings,
  confirmed travel or life events, account goals, card controls or external offers) are withheld. Apart from the
  savings estimate, bespoke calculators, booking and money-movement workflows described in the catalogue remain
  unavailable.
- English only. Synthetic data only.
