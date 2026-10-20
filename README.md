# IF-ELSE2.0
Hackaton Project 20/10

## Goal

**KBC case: "From intent to impact".** Design a scalable ecosystem that helps customers move from intent to
successful action.

The customer states a goal (buying a house, building up a pension, investing) and **KBC takes care of the rest**,
through a trusted network of vetted partners: brokers, insurers, investment funds, estate agents, renovation and
energy partners. Everything happens in the customer's own app. A triple win for the customer, KBC and the partners.

## From IF-ELSE to IF-ELSE2.0

**We are bringing our previous idea, IF-ELSE, into IF-ELSE2.0, but with a new goal.**

- **IF-ELSE (v1)** was the front-end step: *KBC Adaptive Home*, an app that adapts to each customer's life
  situation (persona mix, explainable feed, assistant Kate).
- **IF-ELSE2.0** keeps that foundation and adds the backend step: the **ecosystem engine** that turns a customer's
  intent into a completed outcome, together with KBC's partners.
- The **new goal** decides what we build: peace of mind for the customer, KBC as the trusted orchestrator, and a
  triple win for the customer, KBC and the partners.

The full goal and context are in [CLAUDE.md](CLAUDE.md). Decisions and progress are in [docs/LOG.md](docs/LOG.md).

## Structure

| Folder      | Purpose                         |
|-------------|---------------------------------|
| `backend/`  | Server / API code               |
| `frontend/` | Web app                         |
| `data/`     | Data files (synthetic only)     |
| `docs/`     | Design docs                     |
| `notes/`    | Working notes                   |

## Setup

```bash
cp .env.example .env   # then fill in values
```
