# The ecosystem engine

How a customer's intent becomes a completed, measured outcome with KBC and its partners. Code:
`backend/app/ecosystem/`, `frontend/src/ecosystem/`, `frontend/src/nudges/`, plus the goal bits of
`backend/app/engine/kate.py`.

Related docs: [CUSTOMER-APP.md](CUSTOMER-APP.md) (the customer app and its engine, the channel this engine uses),
[CUSTOMER-STATE.md](CUSTOMER-STATE.md) (the For You feed), [reference/kbc-ecosystems.md](reference/kbc-ecosystems.md)
and [reference/KBC_Ecosystems.xlsx](reference/KBC_Ecosystems.xlsx) (KBC's catalogue of building blocks).

## 1. The idea

The app already knows who the customer is and what is happening. The ecosystem engine makes KBC **act** on it.
A recognised intent ("I'm going freelance") becomes a **goal** with a **journey** of concrete steps. Each step is
done by a KBC service, a KBC advisor or a **vetted partner**. The customer approves every step and every piece of
data that leaves KBC. Afterwards the engine **measures** from the customer's own later transactions whether the goal
delivered. KBC is the orchestrator; the customer gets peace of mind.

| KBC's five steps | Building block |
|---|---|
| 1. Recognise an emerging need | Intent detection (`intent.py`): transparent rules over the customer's own transactions plus what they told Kate → candidate goals with confidence and evidence |
| 2. Understand context and intent | Customer context (`context.py`): products held, budget, values a partner may receive. A step is skipped when the customer already holds the product, so they are never asked twice |
| 3. Activate services, expertise, partners | Playbooks (one JSON file per goal) and the partner registry (`partners.json`), validated at startup |
| 4. Guide through decisions and actions | Journey with a step state machine, consent passport, Kate and nudges. Kate proposes; the customer taps |
| 5. Deliver a measurable outcome | Triple-win ledger (estimates per completed step) and measured outcomes (`outcomes.py`: verified, pending or not met) |

**Triple win.** Every completed step writes ledger rows for three parties. All amounts are illustrative and labelled
as estimates in the UI.

| Party | What is counted |
|---|---|
| Customer | € saved, hours saved, goal reached; later checked against real transactions |
| KBC | Revenue estimate, KBC products activated |
| Partner | A qualified lead, and the fee per the partner's value-share model |

It is not a chatbot (Kate only proposes steps the engine planned) and not a screen (the engine runs behind the API;
the phone app is one channel, the console another).

## 2. Architecture

```
transactions + declared signals (Kate, /api/me/declare) + connected data sources
        │
        ▼
context.py ─► intent.py ─► candidate goals (confidence, evidence, why now; commercial goals held back in hard times)
                                  │ customer taps Start (or states a goal)
                                  ▼
playbooks/*.json ─► service.start_goal ─► journey (steps; already-held products marked done)
                                  │ per step, customer approves
                  ┌───────────────┼──────────────────────────┐
                 KBC            KBC advisor               partner (registry)
            done at once      meeting booked        consent grant ─► payload (granted ∩ allowed fields)
                                                            │       ◄── HMAC-signed webhook: done / rejected / failed
                                                            │           (or SLA missed → next-ranked partner offered)
                                  ▼
                 ledger (triple win) + outcomes.py (measured) ─► phone app, Kate, nudges, ecosystem console
```

## 3. Modules

Backend, `backend/app/ecosystem/`:

| File | Responsibility |
|---|---|
| `catalogue.json` | KBC's 229 building blocks in 21 ecosystems, imported from `KBC_Ecosystems.xlsx` by `scripts/import_ecosystems.py` |
| `partners.json` | Partner registry: data fields (with sensitivity), what is never shared, partners, per-step alternatives, advisor hand-offs |
| `playbooks/*.json` | One goal per file: trigger, ecosystems, target days, next goal, steps |
| `registry.py` | Loads and validates catalogue, partners and playbooks once. A broken file fails at startup |
| `models.py` | Pydantic models for every API shape (mirrored in `frontend/src/ecosystem/types.ts`) |
| `context.py` | What KBC already knows at a date: holdings, partner-shareable values, numbers for step texts, freelance assumptions, keyword constants |
| `intent.py` | 24 detectors (one per playbook), suppression of commercial goals, `detect()` and `detect_with_suppressed()` |
| `service.py` | The engine: goals, step state machine, consent grants and revoke, partner fallback and demotion, households, stalled journeys, webhooks, console overview, partner onboarding |
| `store.py` | SQLite tables (`eco_goals`, `eco_steps`, `eco_grants`, `eco_events`, `eco_ledger`, `eco_sources`, `eco_partner_calls`, `eco_members`, `eco_approvals`, `eco_shown`). Bound parameters only; reads filter on the session's customer id |
| `webhooks.py` | HMAC signing and verification, simulated partners (done, late, reject, fail, timeout) and deletion confirmations |
| `signals.py` | Deadlines and forecasts (pure functions) |
| `outcomes.py` | Measured outcomes from later transactions (pure functions) |
| `sources.py`, `sources.json` | Inbound data sources the customer can connect, with purpose and expiry |
| `nudges.py` | Kate's proactive messages and the attention budget |
| `links.py` | Links For You feed cards to the goal journey behind them |
| `api.py`, `nudges_api.py` | Routers, mounted in `app/main.py` |

Also: `app/engine/kate.py` maps phrases to goals (`GOAL_WORDS`), opens or starts goals (`start_goal`, `open_goal`
actions), answers "what's coming up?" and "will I owe social contributions later?" from `signals.py`, and leads hard
goals (back on track, separation, care for a parent) with empathy instead of a sales line.

Frontend:

| File | What |
|---|---|
| `ecosystem/GoalsStrip.tsx` | Top of the home: active goals with a progress ring, what KBC noticed, household invitations |
| `ecosystem/JourneySheet.tsx` | One goal as a checklist: provider, why them, win, result, measured outcomes, stall prompt, invite |
| `ecosystem/ConsentSheet.tsx` | Approve a step: what the provider will and will not see, for how long, partner choice, what KBC earns |
| `ecosystem/PassportSheet.tsx` | Consent passport both ways: partners with access to your data, and sources KBC reads, with proof of deletion |
| `ecosystem/PlaybooksSheet.tsx` | State a goal yourself |
| `ecosystem/EcoSheets.tsx`, `bits.tsx`, `useGoals.ts`, `client.ts` | Sheet routing, shared pieces, state and polling, API client |
| `ecosystem/EcosystemConsole.tsx` | The KBC console (advisor login) |
| `ecosystem/mock.ts`, `nudges/mock.ts` | In-memory engine for `?mock=1` |
| `nudges/NudgeLayer.tsx`, `useNudges.ts` | Lock-screen-style notifications, bell, Kate inbox, playback when the date moves forward |
| `nudges/NudgeStatsPanel.tsx` | Attention-budget KPI in the console |

## 4. Goals and playbooks

There are **24 playbooks** using 109 of the 229 building blocks:

| Area | Goals (playbook id) |
|---|---|
| Home and family | `buy_home`, `move_house`, `energy_upgrade`, `new_baby`, `together`, `separation`, `care_parent`, `study_start` |
| Work and business | `go_freelance`, `side_job`, `get_paid`, `first_employee`, `go_international`, `sell_business`, `farm_growth`, `job_change` |
| Money and later life | `first_investment`, `retire_well`, `inheritance`, `peace_of_mind`, `back_on_track` |
| Mobility and travel | `mobility`, `ev_switch`, `travel` |

A playbook has an id, title, icon, tagline, ecosystems, `target_days`, an optional `next_goal` and a list of steps.
Each step names its `provider`, the catalogue `products` it uses, the data `fields` a partner gets, `consent_days`,
`held_if` (products that make the step unnecessary), `kbc_products` activated on completion, a `win` text per party,
`estimates` and a `result` template.

**Chains.** A finished goal can propose the next one (`next_goal`): `side_job` → `go_freelance` → `first_employee`,
`go_international` → `first_employee`, `together` → `buy_home` → `energy_upgrade`, `separation` → `move_house` →
`buy_home`, `ev_switch` → `energy_upgrade`, `back_on_track` → `peace_of_mind`, `sell_business` → `retire_well`.

`back_on_track` has no upsell and earns KBC nothing (a test checks this).

**Adding a goal is a file.** Drop a JSON file in `playbooks/`, add a detector to `intent.DETECTORS` if it should be
spotted automatically, and restart. At startup `registry.py` rejects: unknown providers or catalogue ids, unknown
`next_goal`, duplicate step ids, a step asking for a field its partner may not receive, a partner step without
fields or consent days, and an advisor step that lists fields. Without a detector the goal can still be started by
the customer from the playbooks sheet or through Kate.

## 5. Partner registry and value share

`partners.json` has 29 providers: KBC itself, 2 KBC advisor roles (private banker, relationship manager) and 26
external partners (Immoscoop, De Immowinkel, Setle, Impact us today, Encon, Billit, Go Solid, Firsty, Brussels
Airport, Helena, Bolero, Soluz.io, Sweco, VAB, MoveSmart, Cambio, NOWJOBS, Q-Park, Kube ESG, IPEX, Mobit, Blue-bike,
and four marked illustrative: CareFinder, a debt counselling service, a notary network, a family mediator).

Each partner has: kind (`kbc`, `advisor`, `partner`), catalogue ids, allowed data fields, a value-share model,
vetting checks, an integration surface, an SLA in hours, an outcome rate and a customer rating.

| Value-share model | Example |
|---|---|
| `lead_fee` | Immoscoop €45 per qualified buyer |
| `fee_per_completed_step` | Encon €60 per advice session |
| `revenue_share` | Firsty 10% of the eSIM price |
| `subscription` | Billit €4 per active subscription per month |

The debt counsellor, notary and family mediator earn KBC €0, and the consent sheet says so ("KBC earns nothing").
Before every approval the customer sees what KBC earns from that partner (`service.fee_disclosure`).

**Choice and ranking.** Some steps have alternatives (`alternatives` in `partners.json`, e.g. Billit or Soluz.io for
Peppol invoicing, Encon or Sweco for energy advice). Options are ranked by outcome rate, then rating, **never by
fee**. Partners that missed their SLA twice (`DEMOTE_AFTER = 2`) drop below partners that answer.

**Advisor hand-off.** `advisor_steps` routes a KBC step to a human advisor (e.g. `retire_well/private_banker`). Approving
books a meeting on the next working day at 10:00; the file stays inside KBC.

**Onboarding.** `POST /api/ecosystem/partners/manifest` checks a partner manifest against the same rules as
`partners.json` and warns if the partner does not support the `deleted` event.

## 6. Intent detection and suppression

Each detector is a pure function of the customer context and declared signals. It returns a confidence, plain
evidence lines ("You pay €850 rent a month and earn a steady salary") and a "why now". The in-app threshold is 0.5.
Nothing happens until the customer taps Start. Examples of signals: salary stops and a first client invoice arrives
(`go_freelance`), salary continues with small invoices and a KBO registration (`side_job`), care-home payments
(`care_parent`), a rent deposit and two rents to different landlords (`move_house`), BNPL plans, bounced direct debits
or a bailiff (`back_on_track`), foreign clients (`go_international`). Rules that matched look-alikes need a second,
goal-specific signal (`buy_home`, `energy_upgrade`, `first_employee`, `first_investment`).

**Suppression.** When the customer is in trouble, commercial goals are not proposed. If `back_on_track` fires, or
`job_change` fires because the salary stopped without new income, then `first_investment`, `travel`, `buy_home`,
`go_international`, `ev_switch` and `together` are held back. While a business is starting (`go_freelance`,
`side_job`), `first_investment` waits too. `detect_with_suppressed()` returns what was held back and why; nudges
follow the same rule.

## 7. Journeys, consent passport and data minimisation

Step state machine (`service.py`):

```
proposed ─approve─► in_progress ─partner webhook "done"─► done      (KBC and advisor steps complete at once)
    │                    ├─ customer revokes the grant ─► blocked ─approve─► in_progress
    └─decline─► declined └─ partner rejects, fails or misses its SLA ─► blocked + next-ranked partner offered
declined / blocked ─reset─► proposed
```

A goal is `active`, `completed` (every step done or declined, at least one done) or `cancelled`. Starting a goal
marks steps whose product the customer already holds as done ("Already arranged with KBC").

**Consent grant.** Approving a partner step creates a grant: partner, fields, purpose, granted on, expires after the
step's `consent_days`. The consent passport lists every grant as active, expired or revoked. Revoking blocks the
step, logs the event and asks the partner to delete the data; the partner confirms with a signed `deleted` webhook,
shown as proof in the passport.

**Data minimisation in code.** `payload_for()` sends only fields that are both in the active grant and in the partner's
allowed list. The registry refuses, at startup, any outside partner allowed to receive income, balances or
transactions, and any step asking for more than its partner may receive. The consent sheet lists what is shared and
what is never shared. Tests check that income never leaves KBC.

**Partner fallback.** If a partner rejects, fails or misses its SLA, its grant ends (deletion requested), the step is
blocked and the next-ranked vetted partner that has not been tried is offered. **Nothing goes to the new partner until
the customer approves again** with a fresh grant. A late answer after a timeout is logged for the scorecard and
refused (409).

**Stalled journeys.** After 30 days without progress the journey asks once "still want this?" (keep, pause, resume,
stop), shown for 14 days at most. A paused goal gets no journey nudges. Acting on a step resumes it.

## 8. Partner webhooks (security)

```
POST /api/partners/{partner_id}/webhook
X-KBC-Timestamp: unix seconds                  (within ±5 minutes)
X-KBC-Signature: hex HMAC-SHA256(secret(partner_id), "{timestamp}.{raw body}")
body: {event_id, ref, status: in_progress | done | failed | rejected | deleted, result}   (unknown keys rejected)
```

- The partner id in the path selects the key, so a partner can only sign for itself. Secrets come from
  `PARTNER_WEBHOOK_SECRET_<ID>` or are derived from `PARTNER_WEBHOOK_MASTER` (random per process if unset).
- A `ref` only matches a step routed to that same partner. Events are idempotent on (partner, event id).
- Bodies are capped at 4 KB. Only external partners (kind `partner`) can call it.
- Status changes require an active grant and an in-progress step; otherwise 409.
- Partners in this project are **simulated**: they answer through exactly this verification path after a short
  delay (`PARTNER_SIM_DELAY`, default 4 s). `PARTNER_SIM_BEHAVIOUR="billit:reject,setle:timeout"` or the console
  switch (`POST /api/ecosystem/partners/{id}/simulate`) makes a partner late, reject, fail or time out.
  `PARTNER_SIM_SLA_S=20` shortens the SLA for a live demo.
- `scripts/partner_webhook.py` plays a partner over HTTP (the server and script must share the key in `.env`).

Other controls: customer endpoints take the customer from the session and look up every goal and grant id together
with it (no IDOR); no LLM decides which partner gets data; every goal start, step decision, revoke, source connection
and console view goes to `audit_log`; outbound shares are logged as events with the field labels sent.

## 9. Nudges

Kate pushes only when money is at stake, a deadline is near or something is waiting on the customer. Never promos.

| Rule | Value |
|---|---|
| Attention budget | Max 2 non-urgent pushes per rolling 7 days; 1 for customers 65+ |
| Quiet hours | 21:00–08:00; held for the 08:00 morning digest (max 3 items bundled) |
| Urgent | New payee or possible scam, duplicate charge, balance going below zero before income: bypass the budget |
| After an urgent alert | No non-urgent push that day |
| Each topic | Sent once. Mute = 90 days of silence (security alerts cannot be muted). Two dismissals, or "show less" on the feed card → inbox only |
| Intent | A goal is pushed only at confidence ≥ 0.75 (in app: 0.5), and once ever |

What does not fit goes to Kate's inbox silently. `simulate()` replays the policy day by day, so the time-travel
slider shows exactly which nudges would have buzzed between two dates. The hero nudge is Lotte's "Your first invoice
is paid 🎉" on 16 Oct 2026, which opens the freelance journey. The console compares naive pushes with what the budget
lets through (`GET /api/ecosystem/nudge-stats`).

## 10. Signals and forecasts

`signals.py` derives, from the customer's own data:

- **Deadlines** (next 45 days): quarterly VAT returns with any shortfall, advance tax payments, provisional social
  contributions, insurance renewals, pension-savings season (November and December), trips, BNPL instalments.
- **Forecasts**: the social-contribution regularisation gap (about 20.5% of net taxable income, arriving about two
  years later, minus the provisional contributions paid), client concentration (one client above 70% of invoice
  income), work purchases on the private account, care costs, a rent deposit to recover, reverse-charge VAT for EU
  clients.

Each deadline or forecast can point at the goal that takes care of it. Rules and amounts not yet checked carry a
`verify` flag (see §18).

## 11. Measured outcomes

The playbooks carry estimates; `outcomes.py` checks reality once steps are done, from the customer's own later
transactions. Each outcome is `verified`, `pending` ("we'll check on <date>") or `not_met`. Measured for 12 goals:
`energy_upgrade` (energy bills), `get_paid` (the late client paid), `go_freelance` (the reserve covers VAT and
contributions), `travel`, `peace_of_mind`, `retire_well`, `buy_home`, `new_baby`, `move_house` (deposit back),
`back_on_track` (no new BNPL or bounced debits), `ev_switch` (fuel spend) and `care_parent`. Steps carry a simulated
completion date, so a later `as_of` measures what happened after it. The console shows realised against estimated.

## 12. Data sources

The consent passport also works the other way: data KBC reads with the customer's OK (`sources.json`). Connecting is
purpose-bound (one goal), expires and is audited. Values are simulated from the synthetic profile; no real
connection is made. A connected value replaces KBC's estimate (e.g. mypension.be gives the exact pension gap).

| Source | Kind | Access |
|---|---|---|
| Accounts at other banks (PSD2) | psd2 | 90 days |
| eBox (government letters) | government | 365 days |
| Peppol invoices (Billit) | partner | 180 days |
| Company register (KBO/CBE) | public | no consent needed, still shown |
| mypension.be | government | 365 days |
| Energy label database (EPC) | government | 365 days |
| Digital meter (Fluvius) | utility | 365 days |

Steps can hint at a source ("Connect mypension.be for an exact number instead of an estimate").

## 13. Households

The owner of a goal can invite a household member by username; the member accepts or declines. Shareable goals:
`buy_home`, `new_baby`, `together`, `energy_upgrade`, `move_house`. **Separation is never shareable.** On a shared goal
a step that sends data to a partner needs every member's approval before anything leaves KBC. Either member can
revoke a grant. Only the owner can stop the goal.

## 14. Ecosystem console

The advisor login opens the KBC console (`GET /api/ecosystem/overview`):

- **Goal funnel**: per goal, how many of the portfolio's customers it is detected for, started, steps done, completed.
- **Learning loop**: shown → started per goal, and which rules fire most.
- **Partner network**: live scorecard per partner (response time, SLA misses, rejections, demotion) and the
  behaviour switch.
- **Triple win realised** and **measured outcomes** (realised vs estimated).
- **Projection to 2.3M customers**, with its assumptions shown (15% of customers with a detected goal start it).
- **Live partner events**: outbound shares and inbound webhooks, marked "verified" when the HMAC checked out.
- **Attention budget**: naive pushes vs pushes sent.

## 15. API

Customer endpoints take the customer from the session. `as_of` is clamped to the customer's data, or up to the end
of their simulated future (§16).

| Method and path | What |
|---|---|
| `GET /api/me/goals` | Candidates, active goals with journeys, household invitations, holdings, all playbooks |
| `POST /api/me/goals` | Start a goal `{playbook_id}` (detected or stated) |
| `POST /api/me/goals/{goal_id}/steps/{step_id}` | `{decision: approve \| decline \| reset, partner_id?}` |
| `POST /api/me/goals/{goal_id}/cancel` | Stop a goal; partners are asked to delete the data |
| `POST /api/me/goals/{goal_id}/stall` | `{answer: keep \| pause \| resume \| stop}` |
| `POST /api/me/goals/{goal_id}/household` | Invite a member `{username}` (owner only) |
| `POST /api/me/household/{goal_id}` | Accept or decline an invitation `{accept}` |
| `POST /api/me/goals-reset` | Demo reset of the customer's goals |
| `GET /api/me/consents` | The consent passport |
| `POST /api/me/consents/{grant_id}/revoke` | Revoke; the step is blocked and the partner deletes the data |
| `GET /api/me/sources` | Inbound data sources and their state |
| `POST /api/me/sources/{source_id}/connect` | Connect `{playbook_id, purpose}` |
| `POST /api/me/sources/{source_id}/disconnect` | Disconnect |
| `GET /api/me/nudges` | Nudges between `since` and `as_of` (max 92 days), with budget info |
| `POST /api/me/nudges/{nudge_key}/ack` | `{action: opened \| dismissed \| mute}` |
| `POST /api/me/nudges-reset` | Demo reset of nudge acks |
| `POST /api/partners/{partner_id}/webhook` | Signed partner status update (§8) |
| `GET /api/ecosystem/overview` | Console (advisor only) |
| `GET /api/ecosystem/nudge-stats` | Attention-budget KPI (advisor only) |
| `POST /api/ecosystem/partners/{partner_id}/simulate` | Demo switch for a simulated partner (advisor only) |
| `POST /api/ecosystem/partners/manifest` | Validate a partner manifest (advisor only) |
| `GET /api/ecosystem/partners/onboarding` | Manifests validated so far (advisor only) |

Elsewhere in `main.py`: `GET /api/me/home` links feed cards to journeys (`links.enrich_feed`), `POST /api/me/kate`
passes goals, deadlines and forecasts to Kate, and `GET /api/me/timeline` adds the simulated chapters as milestones.

## 16. The hero story: Lotte goes freelance

**Why this journey.** KBC already covers buying a house well. Going freelance is where the pain comes later, which fits
"before they realise they need help":

- Social contributions for starters are provisional. The **regularisation** on the real income arrives about two
  years later, and many starters have not saved for it.
- **Peppol e-invoicing** is mandatory for Belgian B2B invoices, with fines.
- Quarterly **VAT** returns and **advance tax** payments (otherwise a tax surcharge).
- Compared with an employee: a **pension gap** and **no income protection** when ill.

**Today is 20 Oct 2026** (`DEMO_TODAY`). Lotte's history (student in Leuven, first job, mortgage in 2022, a baby in
2024) is context the engine reads. She was employed until the end of September 2026, registered at the enterprise
counter on 2 Oct, bought a €1,499 laptop on her private account on 9 Oct, and her first client paid €4,598 on 16 Oct.
The engine spots the intent from her own signals (salary stopped, first invoice in) and Kate's nudge opens the
`go_freelance` journey (10 steps): business account, move work purchases to the business side, Peppol invoicing
with Billit (or Soluz.io), an automatic tax and contributions reserve, advance tax, start-up advice and social
insurance, pension, income protection, professional liability, digital vault. Only the Billit step shares data
(first name, email, company number), for 365 days.

**Life timeline, today forward.** The slider runs past today into a labelled "simulated future" with these chapters:

| When (simulated) | Chapter |
|---|---|
| Nov 2026 – Jan 2027 | First Peppol invoices; the first VAT return is paid from the reserve |
| Summer 2027 | A work trip abroad: eSIM (Firsty), travel insurance, Fast Lane (`travel`) |
| Late 2027 | More work than one person can do → the engine proposes `first_employee` |
| Nov 2028 | The regularisation bill for 2027 arrives and is already covered by the reserve |

The future transactions come from `synth.demo_customers.lotte_future_transactions()` and are appended **in memory**
by `db._simulated_future()`; they are never stored, so today's view and every earlier date are unchanged. The
reserve rule is the playbook's: the VAT share plus 25% of the rest of every invoice. Goals, layout, Kate, nudges and
outcomes follow the timeline.

Other demo customers (password `demo`): `sara` and `jan`, `marc` (52, investor), `tom` (side
job), `els` (sandwich generation: a child at university and a mother in a care home), `amir` (newcomer, four months of
data), `pieter` (SME owner with German and Dutch clients), `nina` (BNPL and bounced debits: only `back_on_track`,
commercial goals suppressed). `advisor` opens the console.

## 17. Evaluation

Two evaluations, run from `backend/`:

**Synthetic portfolio** (`py -3.12 -m scripts.evaluate_intents`): 1,009 customers (1,000 regular + 9 demo) with
injected goal scenarios (`goal:<id>`) and near-miss look-alikes (`near_miss:<id>`). Precision is 94–100% for every
goal with truth, recall 90–100% except `peace_of_mind` (65%); `go_freelance` is fooled by 9% of its look-alikes.
**This is optimistic**: the rules and the scenarios were written together.

**Blind holdout** (`synth/holdout.py`, `py -3.12 -m scripts.evaluate_holdout`): 300 hand-designed customers written
without seeing the rules, about 40% hard negatives, with Dutch and French spellings and noise. The first blind run is
the number to quote: **macro precision 84%, recall 80%, hard-negative false-positive rate 7%**
(`data/holdout_report_blind_v1.json`).

| Weak spots in the blind run | Precision | Recall |
|---|---|---|
| `first_employee` | 18% | 29% |
| `buy_home` | 26% | 71% |
| `first_investment` | 29% | 86% |
| `energy_upgrade` | 44% | 57% |
| `peace_of_mind`, `study_start`, `together` | 75–100% | 43% |

`data/holdout_report.json` is the current report after tightening rules on that same set (macro 87% / 77% / 6%). It
is no longer blind: `first_employee` improved, but `buy_home` recall fell to 14%, `energy_upgrade` to 0 of 7, and
`first_investment` precision is 39%.

## 18. Facts to verify before they go on a slide

Encoded in `context.py` and `signals.py` with a `verify` note:

- Social contribution rate of 20.5% on net taxable income (main occupation; ceilings not modelled).
- €890 per quarter provisional minimum for a starter.
- Regularisation about two years later.
- Advance tax dates 10 Apr, 10 Jul, 10 Oct, 20 Dec.
- €1,050 pension-savings ceiling (2025 basic amount; check 2026).
- Peppol B2B e-invoicing mandatory since 1 Jan 2026, and its fines.
- Supplementary pension for the self-employed at about 8.17%, capped at €3,800; reverse charge for EU clients; rent
  deposit of two months.

## 19. Limitations

- Partners, data sources, offers and amounts are simulated or illustrative. Four partners are explicitly invented.
- Detection is transparent rules, not ML. Blind precision is weak for `first_employee`, `buy_home`,
  `first_investment` and `energy_upgrade` (§17).
- Goals held back by suppression are not yet returned in `GET /api/me/goals`, so the app cannot show "why isn't X
  proposed?" (the data is there in `detect_with_suppressed`).
- In the simulated future the For You feed stays at today's data (Customer State reads SQL); goals, layout, Kate,
  nudges and outcomes do follow the timeline.
- Only Lotte has a simulated future.
- Not built: an incrementality holdout in the console, a live "a new goal is a file" demo.
- The `approved` step status exists in the schema but is not used: approval goes straight to `in_progress`.
