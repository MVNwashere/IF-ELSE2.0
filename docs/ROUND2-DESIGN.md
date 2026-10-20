---
title: Round 2 design: the ecosystem engine
type: spec             # context | spec | decision | notes
status: draft          # draft | review | final | outdated
incorporated: no       # no | partial | yes | n/a
code_refs: []          # planned: backend/app/ecosystem/, frontend/src/journey/
owner: team IF-ELSE
created: 2026-10-20
updated: 2026-10-20
source: CLAUDE.md, finals-guide-summary.md, kbc-ecosystems-summary.md, round 1 code
---

# Round 2 design: the ecosystem engine

> Goal and vision: [CLAUDE.md](../CLAUDE.md). Decisions: [LOG.md](LOG.md). Round 1 engine: [DESIGN.md](DESIGN.md).
> This replaces [KBC-QUESTIONS.md](KBC-QUESTIONS.md) as our answer to the KBC case.

## 1. The idea in one paragraph

In round 1 KBC learned to **notice**: the app reads a customer's own signals and knows who they are and what is
happening. In round 2 KBC learns to **act**. A recognised intent ("I'm going freelance") becomes a **goal** with a
**journey** of concrete steps. Each step is routed to a KBC service or a **vetted partner** from a trusted network.
The customer approves every step and every piece of data shared, and the **outcome is measured** for all three
parties. KBC is the orchestrator, and the customer gets peace of mind.

> Pitch line: *"In round 1 we gave KBC eyes. Today we give it hands, and the customer holds the remote."*

## 2. How it answers the case

| KBC asks (journey step) | Our building block | Reused from v1 |
|---|---|---|
| 1. Recognise an emerging need | **Intent detector**: transaction signals, life events and stated intent ("Kate, we're expecting") → candidate goals with confidence and evidence | `customer_state/`, `engine/features.py`, `persona.py`, `/api/me/declare` |
| 2. Understand context and intent | Goal **context**: persona mix, budget, products held, what KBC already knows (so the customer is never asked twice) | Customer State snapshot, evidence strings |
| 3. Activate services, expertise, partners | **Playbooks** (config) + **partner registry** of vetted partners with capabilities and value-share | new |
| 4. Guide through decisions and actions | **Journey** with steps, statuses and deadlines; Kate proposes, the customer confirms | Kate's propose-then-confirm pattern (`KateAction`) |
| 5. Deliver a measurable outcome | **Triple-win ledger** per step and per goal, rolled up across the portfolio | advisor overview, `eur_impact` |

| Triple win | What we measure (illustrative, labelled as assumptions in the UI) |
|---|---|
| Customer | € saved (grants claimed, better rate, avoided fines), hours saved, goal reached by its date |
| KBC | Products activated (loan, insurance), relationship depth, retention signal |
| Partners | Qualified leads, conversions, revenue share paid by KBC or fee per completed step |

**Don't-build check:** this is not a chatbot (Kate only proposes steps the engine planned) and not a screen (the engine
runs headless; the v1 app is one channel). It's an ecosystem: partners plug in through a registry and an adapter
contract.

## 3. Hero journey: Lotte goes freelance, told as a life timeline from today forward

**Time frame: today and the future, never the past.** The demo starts on the pitch date, **20 Oct 2026**. Lotte's
earlier history (student, first job, house, baby) is only context the engine reads; we don't present it as chapters.
Everything after today is simulated forward with v1's time-travel slider and is labelled as simulated in the UI.

**The story.** Lotte (27, Leuven, mortgage, a toddler) left her job at the end of September. On 16 Oct 2026 her first
client pays her first invoice. The engine spots the intent from her own signals: salary stopped, first invoice income.

**Why this is "before they realise they need help"** (every fact to verify before it goes on a slide):
- Social contributions for starters are provisional. The **regularisation** on the real income arrives about two years
  later, and many starters haven't saved for it.
- **Peppol e-invoicing** is mandatory for Belgian B2B invoices since 1 Jan 2026, with fines.
- Quarterly VAT returns and **advance tax payments** (otherwise a tax surcharge).
- Compared with an employee: a **pension gap** and **no income protection** if she gets sick.

### The hero chapter (deep, live in the demo)

| # | Step | Provider (from the catalogue) | Data shared (consent scope) | Win |
|---|---|---|---|---|
| 1 | Spot the start: first invoice in, salary stopped | KBC intent detector | none (stays at KBC) | Customer: help on day 1, not after the first fine |
| 2 | Keep business and private money apart | KBC business account and card | already at KBC | KBC: a new business relationship |
| 3 | Invoice the right way (Peppol) | **Billit** | business name, VAT number, IBAN | Customer: no fines; partner: subscription |
| 4 | Never be surprised by a bill | KBC automatic reserve: a % of every invoice into a tax and contributions pot | none (stays at KBC) | Customer: regularisation and taxes covered in advance |
| 5 | Start-up advice and social insurance fund | **Start it @KBC**, Boostpack | name, start date, activity | Customer: set up correctly; partner: qualified starter |
| 6 | Protect the income and close the pension gap | KBC business income insurance, supplementary pension for the self-employed | income estimate (KBC only) | Customer: safety net; KBC: insurance + pension |
| 7 | Keep the paperwork | KBC digital vault | invoices, contracts | Customer: everything in one place |

### The life timeline (from today forward)

Each finished goal feeds the next one: the ledger and new signals of one journey become input for the intent
detector. This is how we show the system follows a life, not a product, and that "a new goal is a file".

| When (simulated) | Chapter | Depth in the demo | Ecosystem and partners |
|---|---|---|---|
| **20 Oct 2026 (today)** | Going freelance | **Hero, live** | Business, Pensions, Business protection |
| Jan 2027 | First Peppol invoices and the first VAT return done automatically | Outcome check, 5 s | Business (Billit) |
| Summer 2027 | Work trip abroad: eSIM, travel insurance, Fast Lane | Light, 5 s | Travel (Firsty, Brussels Airport) |
| Late 2027 | Revenue keeps growing → the engine proposes the next goal: **first employee** | Seeded goal, 10 s | Work and employees (NOWJOBS, Team Protect Plan) |
| 2028 | The regularisation bill arrives and is already covered by the reserve | **Payoff**, 10 s | Ledger: the measured outcome |

**Backup playbook:** the 50-year-old investor (pension gap check, managed investing, Private Plan, inheritance
planning). Only if there is time; it needs the `marc` customer.

### Synthetic data changes

Lotte's data currently has her freelance since Jan 2026 with nine months of invoices. Re-date it to fit the story:
the salary continues until 1 Oct 2026, the first invoice payment lands on 16 Oct 2026, and `TODAY` / `DEMO_TODAY`
moves to 2026-10-20. Check the v1 cards that depend on relative dates (for example sara's car insurance renewing 12
days after `TODAY`). Future chapters are generated by the playbooks' simulated signals, not stored as transactions.

## 4. Architecture

```
signals (v1 Customer State) ─┐
stated intent (Kate/declare) ┴─► intent detector ─► candidate goals ─► customer accepts goal
                                                                            │
                         playbooks/*.json ─► journey planner ─► journey (steps, status, deadlines)
                                                                            │  per step:
             partner registry ─► router ─► consent passport (customer approves scope) ─► adapter (KBC or partner mock)
                                                                            │            ◄── signed webhook: status
                                                                            ▼
                                                 triple-win ledger ─► customer view (v1 app) + ecosystem console
```

New backend package `backend/app/ecosystem/`, mounted as a router like `customer_state/api.py`:

| Module | Responsibility |
|---|---|
| `playbooks/*.json` | One goal per file: trigger rules, steps, provider per step, consent scope, win estimates. Adding a goal is a file, not a release. |
| `partners.json` | Vetted partner registry: name, ecosystem, capabilities, allowed data fields, value-share model, vetting status. |
| `intent.py` | Pure functions: Customer State + declared signals + `as_of` → candidate goals with confidence and evidence. |
| `journey.py` | Playbook + context → journey; step state machine `proposed → approved → in_progress → done` (or `declined`, `blocked`). |
| `consent.py` | Consent passport: grants per partner and scope, with expiry and revoke. The adapter only receives fields in an active grant. |
| `adapters.py` | One interface `start(step, payload) -> ref` and `status(ref)`; mock adapters per partner that progress over simulated time. |
| `ledger.py` | Writes win entries on step completion; portfolio roll-up and projection to 2.3M customers. |
| `api.py` | Endpoints below. |

Storage: new SQLite tables in the existing DB (`goals`, `journey_steps`, `consent_grants`, `ledger_entries`,
`partner_events`), created in `db.py` like the v1 tables.

## 5. API (session-derived identity, as in v1)

| Method and path | What |
|---|---|
| `GET /api/me/goals` | Candidate and active goals with journey and progress |
| `POST /api/me/goals` | Accept a candidate goal or state a new one (`{playbook_id}`) |
| `POST /api/me/goals/{goal_id}/steps/{step_id}` | `{decision: approve \| decline}`; approve creates the consent grant and starts the adapter |
| `GET /api/me/consents` | The consent passport: who sees what, why, until when |
| `POST /api/me/consents/{grant_id}/revoke` | Revoke; the step goes to `blocked` and the partner is notified |
| `POST /api/partners/{partner_id}/webhook` | Partner status update, **HMAC-signed**, idempotent on event id |
| `GET /api/ecosystem/overview` | Advisor or KBC role only: funnel per goal, partner performance, triple-win totals, 2.3M projection |

Every `{goal_id}` and `{grant_id}` is looked up together with the session's customer id (no IDOR). Kate gets new
action kinds `start_goal` and `approve_step`. They stay proposals that the app sends through the endpoints above
after a tap.

## 6. Customer experience (v1 app = the channel)

- **Goal hero tile** on the adaptive home: "Going freelance: 3 of 7 steps done", with a progress ring. It uses the v1
  registry (a new component `GoalHero`), so the layout planner can make it the hero.
- **Journey sheet**: the steps as a checklist. Each step shows provider, *why this partner*, what it costs or
  saves, and one Approve button.
- **Approve sheet = consent passport preview**: "Billit will see: your business name, VAT number and IBAN. Not
  your income or your private account. Until you stop." Approve or decline.
- **Kate** opens with the detected intent ("Your first client just paid you. Congratulations on going freelance!
  Want KBC to set up the rest?") and can propose the next step.
- **Life timeline**: a strip above the journey from today into the future; dragging it fast-forwards simulated time.
- **Ecosystem console** (replaces the advisor view): the goal funnel, partner network status, a live event feed of
  webhooks and the triple-win counter projected to 2.3M customers.

## 7. Security (Aikido 10%, and it's a bank)

Keep every v1 control. New for round 2:
- Partner webhooks: HMAC-SHA256 over the body with a per-partner secret from `.env`, timestamp window, idempotency
  key, and a strict Pydantic schema. The partner id comes from the path *and* must match the signature key.
- Data minimisation is enforced in code: adapters receive a payload built from the grant's scope only, and there is
  a unit test that the income never leaves for Billit.
- Every consent grant, revoke and outbound payload goes to `audit_log`.
- Playbooks and the partner registry are static files validated at startup. No LLM decides which partner gets data.

## 8. Demo script (3 min, live pitch, no own laptop: slides + recorded screen video)

| Time | Beat |
|---|---|
| 0:00–0:20 | Hook: "Going freelance means an accountant, a social insurance fund, Peppol, VAT and a bill two years later that nobody warned you about. Today your bank opens a business account and that's it." |
| 0:20–0:45 | **Today, 20 Oct 2026.** Lotte's first client pays. Kate spots the intent from her own signals and offers the goal. One tap. |
| 0:45–1:35 | The hero journey: business account, approve Billit (the consent passport shows exactly what's shared), the webhook comes back, the automatic reserve is set, income protection and pension proposed. Progress ring fills. |
| 1:35–2:10 | Fast-forward on the life timeline: Jan 2027 VAT done, summer 2027 trip, late 2027 the engine proposes "first employee", **2028 the regularisation bill arrives and is already covered**. |
| 2:10–2:35 | Ecosystem console: the same events seen by KBC and partners; the triple-win ledger ticks; projection to 2.3M. "A new goal is a file." |
| 2:35–3:00 | Trust: AI proposes, the customer approves, partners see only what's granted. Close: "Peace of mind. KBC takes care of it." |

## 9. Work plan (today; adjust names in LOG.md)

| Until | Backend (2 people) | Frontend (1–2 people) | Pitch (1 person, part-time) |
|---|---|---|---|
| 10:30 | Playbook + partner JSON schema; freelance playbook; `journey.py` state machine with tests; re-date Lotte's data (§3) | Mock JSON for `GET /api/me/goals`; `GoalHero` tile | Aikido connected to this repo, first scan |
| 12:30 | `consent.py`, `adapters.py` mocks, endpoints, webhook with HMAC; intent detector for Lotte's first invoice (16 Oct 2026) | Journey sheet + approve/consent sheet on mock data | Deck skeleton; verify facts (regularisation, Peppol, advance payments) |
| 14:00 | Ledger + `/api/ecosystem/overview`; Kate `start_goal`/`approve_step`; travel and first-employee playbooks, goal chaining | Wire to real API; life timeline strip; ecosystem console page | Script, timings |
| 14:30 | **Feature freeze.** Demo path test, Aikido rescan and fixes | Polish, reset button for the demo | Record the screen video (no own device at the pitch) |
| 15:45 | README (what's new today, how to run, what's unfinished), Builderbase submission | | Rehearse twice; deck exported as PDF |

## 10. Open questions

1. Value-share model to show: lead fee, revenue share, or a flat fee per completed step? (Pick one, label it
   illustrative.)
2. Can we name real catalogue partners (Billit, Start it @KBC, Firsty, NOWJOBS) on slides? They come from KBC's
   own catalogue, so probably yes; ask a KBC mentor.
3. Check facts before they go on a slide: how and when the regularisation of social contributions works, the Peppol
   start date and fines, advance tax payment surcharges, and the number of new self-employed per year in Belgium.
