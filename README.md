# KBC Takes Care

*From intent to impact.* **Peace of mind: KBC takes care of it.** A customer states a goal, or KBC spots it in their own banking signals, and
KBC turns it into a guided journey across its own services and a network of vetted partners, with the customer
approving every step and every piece of data shared. The outcome is measured for the customer, KBC and the partners.

Built by team IF-ELSE for KBC at the Tectonic Hackathon (October 2026). **All data is synthetic**; partners, offers and amounts are
illustrative.

## What it does

```
signals (transactions, Kate, connected sources) ─► intent detector ─► "KBC noticed…" ─► customer taps Start
playbooks/*.json ─► journey of steps ─► per step: a KBC service, or a vetted partner after a consent grant
partner ─► HMAC-signed webhook ─► step done ─► measured outcome + triple-win ledger ─► app and KBC console
```

- **Recognise.** Transparent rules spot 24 goals from a customer's own transactions, each with evidence and a
  confidence: going freelance, a side job, buying a home, an energy upgrade, a new baby, caring for a parent, getting
  back on track, retiring well and more. Commercial goals are held back in hard times, with the reason.
- **Understand.** The goal's context comes from what KBC already knows (persona mix, products, Customer State), so
  the customer is never asked twice.
- **Activate.** Each goal is a playbook file. Steps route to KBC building blocks (229 items from KBC's own
  catalogue) or to 29 vetted partners and advisors, each with the data fields it may receive and a value-share model.
- **Guide.** A journey of steps with a consent passport (grant, expiry, revoke), data minimisation enforced in code,
  partner fallback when one rejects or times out, joint approval for households, and Kate nudges within an attention
  budget.
- **Measure.** Outcomes are verified from later transactions instead of trusted estimates, and roll up into a
  triple-win view in the KBC ecosystem console.

The customer sees it in the **KBC Takes Care app**: a phone app whose home screen adapts to the customer's persona mix,
with an explainable For You feed, time travel across the customer's life, customisation and the assistant **Kate**,
who proposes and never acts on her own.

Details: [docs/ECOSYSTEM.md](docs/ECOSYSTEM.md) (the ecosystem engine) and
[docs/CUSTOMER-APP.md](docs/CUSTOMER-APP.md) (the customer app and its engine).

## Run it

Backend (Python 3.12):

```bash
cp .env.example .env                                # then fill in the secrets
cd backend
py -3.12 -m pip install -r requirements.txt
py -3.12 -m uvicorn app.main:app --reload --port 8000 --env-file ../.env   # builds backend/kbc.db on first start
```

Frontend (Node 22):

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173 (proxies /api to :8000)
```

Or run `npm run build` and let the backend serve the app at http://localhost:8000. A standalone UI without a backend
runs at http://localhost:5173/?mock=1.

To rebuild the synthetic data explicitly: `py -3.12 -m synth.generate --n 1000 --seed 42` (or delete
`backend/kbc.db`).

## Demo logins

Password for all: `demo` (override with `DEMO_PASSWORD`; the demo panel's customer switcher assumes `demo`).

| Username | Who | What it shows |
|---|---|---|
| `lotte` | 27, left her job in September, first client paid on 16 Oct 2026 | The hero journey: going freelance. Her life timeline runs past today as a simulated future (VAT, a trip, a first employee, the regularisation bill already covered) |
| `sara` | Freelancer and young mother | A persona blend nobody designed; car insurance renewing in 12 days |
| `jan` | 71, retiree | Large, calm, high-contrast layout; scam shield; a duplicate charge |
| `marc` | 52, investor | Pension, wealth and estate planning |
| `tom` | Employee with a side business | Side job, before it becomes going freelance |
| `els` | 48, a child at university and a mother in care | The sandwich generation |
| `amir` | Newcomer with four months of data | Cold start |
| `pieter` | SME owner with clients abroad | Going international |
| `nina` | BNPL instalments and bounced debits | Back on track only; commercial goals suppressed |
| `advisor` | KBC | The ecosystem console: goal funnel, partner network, live events, triple win, projection to 2.3M customers |

Regular synthetic customers: `c1` … `c1000`.

## Repository

| Path | What |
|---|---|
| `backend/app/ecosystem/` | Ecosystem engine: intents, playbooks, partners, journeys, consent, webhooks, nudges, signals, outcomes, data sources |
| `backend/app/engine/` | Features, persona mix, cards, ranker, layout planner, Kate |
| `backend/app/customer_state/`, `backend/app/recommender/` | Customer State and the For You feed |
| `backend/app/main.py`, `auth.py`, `db.py`, `schemas.py` | FastAPI app, session auth, SQLite, API contracts |
| `backend/synth/` | Synthetic customers, demo personas, the blind holdout set |
| `backend/scripts/` | Evaluation, catalogue imports, a partner webhook client |
| `frontend/` | React + Vite phone app and console |
| `data/` | Evaluation reports |
| `docs/` | Design docs; `docs/reference/` holds KBC's ecosystem catalogue and the feed card specifications |

## Tests and evaluation

From `backend/`:

```bash
py -3.12 -m pytest                       # unit and API tests
py -3.12 -m scripts.evaluate             # persona and feed quality vs injected ground truth
py -3.12 -m scripts.evaluate_intents     # goal detection on the synthetic portfolio, with look-alikes
py -3.12 -m scripts.evaluate_holdout     # goal detection on 300 customers written without seeing the rules
```

The number to quote is the **blind holdout**: macro precision 84%, recall 80%, false positives on hard negatives 7%
on its first run ([data/holdout_report_blind_v1.json](data/holdout_report_blind_v1.json)). The synthetic-portfolio
numbers are optimistic because the rules and that data were written together.

## Security

- HMAC-signed `HttpOnly` `SameSite=Lax` session cookie; PBKDF2-SHA256 password hashes; login rate limits.
- Customer endpoints take the customer from the session only (no IDOR); every input is a Pydantic model; SQL uses
  bound parameters only; security headers and CSP; the frontend renders text, never HTML.
- Partner webhooks are HMAC-SHA256 signed over timestamp and body, with a 5-minute window, idempotent event ids and
  a strict schema.
- Data leaves KBC only under an active consent grant, and only the fields that partner is allowed to receive.
  Grants, revokes and outbound payloads are audited.
- Kate can't change anything herself: she returns proposed actions that run through the same validated endpoints
  after the customer taps. The optional LLM layer only rephrases, and every number must appear in the grounded
  context.
- Host header allow-list (`ALLOWED_HOSTS`; add your LAN address to demo from another device); login limits keyed
  on IP and username; the demo password is never printed.
- Secrets only via `.env`; ground truth is never returned to customers.

## Limitations

- Rules, not ML: detectors, persona scores and rankers are transparent rules by design. The contracts allow
  swapping in trained models.
- Partners are simulated through the same signed webhook path a real partner would use.
- Weak detectors on the blind holdout: first employee, buy home, first investment and energy upgrade all have low
  precision (18–44%); see [docs/ECOSYSTEM.md](docs/ECOSYSTEM.md).
- In Lotte's simulated future, goals, layout, Kate and outcomes follow the timeline, but the For You feed stays at
  today's data.
- Kate's AI mode (`KATE_LLM=openrouter`) is tested with a scripted fake model, not yet against a live model. Without
  it, or for customers who haven't allowed it, Kate runs on her rules.
- Facts behind the freelance journey (social-contribution rates and minimums, advance-tax dates, the pension-savings
  ceiling, the Peppol mandate) are modelled from public rules and need checking before real use.
- English only.
