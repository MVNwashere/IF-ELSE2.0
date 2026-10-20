# IF-ELSE 2.0: guide for working in this repo

Read this first. What the project is and how to run it: [README.md](README.md).

## The goal

**From intent to impact:** a scalable ecosystem that helps bank customers move from an intent ("I'm going
freelance", "we want to buy a house") to a successful, measured outcome, with KBC as the trusted orchestrator of
vetted partners. The customer states a goal, or KBC spots it in their own signals, and KBC takes care of the rest
inside the customer's app.

The engine follows five steps:
1. **Recognise** an emerging need, ambition, opportunity or challenge
2. **Understand** the context and intent behind it
3. **Activate** the right KBC services, expertise and partners
4. **Guide** the customer through decisions and actions
5. **Deliver** a measurable outcome

Every feature should be a **triple win**: the customer reaches the goal more easily, KBC strengthens the relationship
and earns sustainable value, and partners have a clear reason to take part. Start from the customer's goal, not from
a banking product. No generic chatbot and no screen for its own sake.

## Where things are

| Area | Code | Docs |
|---|---|---|
| Ecosystem engine: intents, goals, journeys, consent, partners, webhooks, nudges, outcomes, console | `backend/app/ecosystem/`, `frontend/src/ecosystem/`, `frontend/src/nudges/` | [docs/ECOSYSTEM.md](docs/ECOSYSTEM.md) |
| Customer app (KBC Takes Care): features, persona mix, cards, ranker, layout planner, Kate, API, auth | `backend/app/engine/`, `backend/app/main.py`, `frontend/src/` | [docs/CUSTOMER-APP.md](docs/CUSTOMER-APP.md), [docs/COMPONENT-PROPS.md](docs/COMPONENT-PROPS.md) |
| Customer State and the For You feed | `backend/app/customer_state/`, `backend/app/recommender/` | [docs/CUSTOMER-STATE.md](docs/CUSTOMER-STATE.md) |
| Synthetic data | `backend/synth/` | |
| Evaluation and import scripts | `backend/scripts/` | |
| Source material (KBC catalogue, feed card specs) | | [docs/reference/](docs/reference/) |

## Commands (from `backend/`)

```bash
py -3.12 -m pytest                          # all tests
py -3.12 -m uvicorn app.main:app --reload --port 8000 --env-file ../.env
py -3.12 -m scripts.evaluate_intents        # intent precision/recall on the synthetic portfolio
py -3.12 -m scripts.evaluate_holdout        # the same on the blind holdout
```

Delete `backend/kbc.db` to rebuild the synthetic database on the next start.

## Rules

- **Synthetic data only.** Partners, offers and amounts are illustrative, not real KBC products or contracts.
- **AI proposes, the customer confirms.** Nothing happens and no data leaves KBC without the customer's approval;
  partners only receive the fields they are allowed to see and the customer granted.
- **Identity comes from the session.** No customer ids in customer URLs; validate every input with a Pydantic model;
  bound SQL parameters only.
- **Secrets only in `.env`** (see `.env.example`); never commit it.
- **Transparent rules over black boxes.** Detectors, persona scores and rankers explain themselves with evidence.
- **A new goal is a file** in `backend/app/ecosystem/playbooks/`; playbooks and the partner registry are validated
  at startup.
- Keep docs describing the code as it is now. When behaviour changes, update the matching doc in the same change.
