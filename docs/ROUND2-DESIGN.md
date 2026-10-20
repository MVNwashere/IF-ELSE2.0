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
happening. In round 2 KBC learns to **act**. A recognised intent ("we want to buy a house") becomes a **goal** with a
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

## 3. Hero journey (recommended, decision still open in LOG.md)

**"We want to buy a house": Lotte, 2021–2022.** Why this one:
- It's the team's own example, and the Housing + Energy ecosystems are the richest in the KBC catalogue.
- Lotte's synthetic history already contains it: first job in 2021, a notary payment on 15 Mar 2022 and a KBC
  mortgage from April 2022. With v1's time travel we can show the engine spotting the intent *before* the purchase.
- It crosses domains (housing, energy, insurance, admin), which is what "ecosystem" means.

| # | Step | Provider (from the catalogue) | Data shared (consent scope) | Win |
|---|---|---|---|---|
| 1 | What can we afford? | KBC housing budget calculator | none (stays at KBC) | Customer: realistic budget in 1 minute |
| 2 | Find and value homes | **Immoscoop** (search, valuation) | budget range, region | Partner: qualified buyer lead |
| 3 | Know the renovation bill before you bid | **Setle** (renovation costs and grants), **De Immowinkel** (EPC certificate) | property address | Customer: no surprise renovation duty (Flemish rule, verify with `/be-domain`) |
| 4 | Mortgage including renovation | KBC Home Loan API | already at KBC | KBC: mortgage + energy loan |
| 5 | Insured from the day of signing | KBC Home Insurance API | property details | KBC: insurance; customer: no gap |
| 6 | Make it energy-efficient | **Impact us today** (quotes), KBC energy loan, solar/battery calculator | address, chosen works | Customer: grants + lower bills; partner: contract |
| 7 | Keep the paperwork | KBC digital vault, MyHome | deed, EPC, quotes | Customer: everything in one place |

**Backup playbooks** (same engine, a JSON file each, shown for 15 s in the pitch to prove it scales):
- **Freelance start** (Lotte, Jan 2026, first invoice detected): business account, Peppol invoicing via **Billit**,
  automatic tax and social-contributions reserve, supplementary pension for the self-employed, income protection.
- **The 50-year-old investor** (open candidate in LOG.md): pension gap check, managed investing, Private Plan,
  inheritance planning. Would need a new synthetic customer.

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

- **Goal hero tile** on the adaptive home: "Buying a home: 3 of 7 steps done", with a progress ring. It uses the v1
  registry (a new component `GoalHero`), so the layout planner can make it the hero.
- **Journey sheet**: the steps as a checklist. Each step shows provider, *why this partner*, what it costs or
  saves, and one Approve button.
- **Approve sheet = consent passport preview**: "Setle will see: the address of the house. Not your income. Until
  30 June." Approve or decline.
- **Kate** opens with the detected intent ("Your savings and rent payments suggest you're looking to buy. Want
  KBC to take care of it?") and can propose the next step.
- **Ecosystem console** (replaces the advisor view): the goal funnel, partner network status, a live event feed of
  webhooks and the triple-win counter projected to 2.3M customers.

## 7. Security (Aikido 10%, and it's a bank)

Keep every v1 control. New for round 2:
- Partner webhooks: HMAC-SHA256 over the body with a per-partner secret from `.env`, timestamp window, idempotency
  key, and a strict Pydantic schema. The partner id comes from the path *and* must match the signature key.
- Data minimisation is enforced in code: adapters receive a payload built from the grant's scope only, and there is
  a unit test that the income never leaves for Immoscoop.
- Every consent grant, revoke and outbound payload goes to `audit_log`.
- Playbooks and the partner registry are static files validated at startup. No LLM decides which partner gets data.

## 8. Demo script (3 min, live pitch, no own laptop: slides + recorded screen video)

| Time | Beat |
|---|---|
| 0:00–0:20 | Hook: "Buying a house means 7 parties, 40 documents and one scared couple. Today KBC sells only the mortgage." |
| 0:20–0:50 | Lotte in 2021 (time travel): Kate spots the intent from her own signals and offers the goal. One tap. |
| 0:50–1:50 | The journey: approve Immoscoop (consent passport shows exactly what's shared), the webhook comes back, Setle shows the renovation bill and grants *before* she bids, mortgage + insurance + energy loan in one flow. Progress ring fills. |
| 1:50–2:20 | Ecosystem console: the same events seen by KBC and partners; the triple-win ledger ticks; projection to 2.3M. |
| 2:20–2:40 | Scale: "A new goal is a file". Show the freelance and investor playbooks running on the same engine. |
| 2:40–3:00 | Trust: AI proposes, the customer approves, partners see only what's granted. Close: "Peace of mind. KBC takes care of it." |

## 9. Work plan (today; adjust names in LOG.md)

| Until | Backend (2 people) | Frontend (1–2 people) | Pitch (1 person, part-time) |
|---|---|---|---|
| 10:30 | Playbook + partner JSON schema; house playbook; `journey.py` state machine with tests | Mock JSON for `GET /api/me/goals`; `GoalHero` tile | Aikido connected to this repo, first scan |
| 12:30 | `consent.py`, `adapters.py` mocks, endpoints, webhook with HMAC; intent detector for Lotte 2021 | Journey sheet + approve/consent sheet on mock data | Deck skeleton; verify facts (renovation duty, grants) |
| 14:00 | Ledger + `/api/ecosystem/overview`; Kate `start_goal`/`approve_step`; freelance playbook | Wire to real API; ecosystem console page | Script, timings |
| 14:30 | **Feature freeze.** Demo path test, Aikido rescan and fixes | Polish, reset button for the demo | Record the screen video (no own device at the pitch) |
| 15:45 | README (what's new today, how to run, what's unfinished), Builderbase submission | | Rehearse twice; deck exported as PDF |

## 10. Open questions

1. Which hero journey: house (recommended) or the 50-year-old investor? Record it in LOG.md.
2. Value-share model to show: lead fee, revenue share, or a flat fee per completed step? (Pick one, label it
   illustrative.)
3. Can we name real catalogue partners (Immoscoop, Setle, Impact us today, Billit) on slides? They come from KBC's
   own catalogue, so probably yes; ask a KBC mentor.
4. Check facts before they go on a slide: the Flemish renovation obligation after purchase, current grant names and
   amounts, Peppol fines.
