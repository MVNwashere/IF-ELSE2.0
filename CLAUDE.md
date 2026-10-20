# IF-ELSE 2.0: project goal and context

Read this first. Everything we build in this repo should serve the goal below. Log decisions in
[docs/LOG.md](docs/LOG.md).

## The event

- **Tectonic Hackathon, final round**, Tuesday 20 October 2026, De Vooruit, Ghent. Team **If/Else** (top 32 of 280).
- Hacking 09:00–16:00. **Submit by 16:00.** Semi-final pitch 16:15 (Wintercircus), grand final 18:00. Prize €10,000.
- Details: [docs/finalist-info.md](docs/finalist-info.md).

## The KBC case: "From intent to impact"

> **Design a scalable ecosystem that helps customers move from intent to successful action.**
> Slide tagline: "Don't choose our ecosystem. Define the next one."

**Build the journey.** Show how KBC can:
1. Recognise an emerging need, ambition, opportunity or challenge
2. Understand the context and intent behind it
3. Activate the right services, expertise and partners
4. Guide the customer through decisions and actions
5. Help deliver a measurable outcome

**Think ecosystem.**
- Start from the customer's goal, not from a banking product.
- Use KBC's existing capabilities as building blocks, not boundaries. You can combine existing capabilities in new
  ways, connect different life and business domains, introduce new ecosystem partners, and invent capabilities KBC
  doesn't have today.
- Sustainability and entrepreneurship are sources of inspiration, not limits.
- Choose the life or business challenge where we believe KBC can create meaningful impact.

**Make it a triple win.**
- **Customer:** the goal becomes easier, faster or better to achieve.
- **KBC:** the solution strengthens the customer relationship and creates sustainable business value.
- **Ecosystem:** partners have a clear reason to participate and to share in the value created.

| Don't build | Do build |
|---|---|
| Another feature, another screen, a generic chatbot, a small optimisation | A bold vision, a differentiated ecosystem, a believable future customer experience, a **working proof of concept** |

## Our vision

**Peace of mind: KBC takes care of it.** The working customer doesn't want to worry about money matters any more.
The relationship is built on **trust**: the customer states a goal (or KBC spots it) and KBC handles the rest,
inside the KBC app.

The ecosystem is a **trusted network** around the customer's goal. KBC is the orchestrator, and the partners are
vetted: brokers, insurers, investment funds, estate agents, renovation contractors, energy advisors and subsidy
schemes. The customer never has to look for or check a partner themselves.

Example: *"I want to buy a house."* Instead of only a mortgage, the ecosystem brings in the estate agent, home
insurance, renovation, energy subsidies and so on, all together around one goal.

Personas who should be able to do **everything in their own app**, for example:
- the **50-year-old investor** (wealth, pension, estate planning)
- the earlier ones: student, young professional, young family, freelancer, retiree

## Where we come from: IF-ELSE v1 → 2.0

- **v1** (`C:\Users\mrano\IF-ELSE`, preliminary round, 30 Sept) was a **front-end step for the user**: *KBC
  Adaptive Home*. The home screen adapts to a persona mix inferred from transactions, with an explainable "For You"
  feed, time travel, customisation and the assistant **Kate**. Stack: FastAPI + SQLite (Python 3.12), React + Vite.
  Synthetic data. Demo customers: `lotte`, `sara`, `jan`.
- **2.0 (this repo) is the backend step.** We build the **ecosystem engine** behind the app: the system that turns a
  recognised intent into a completed outcome across KBC and its partners. Reuse v1 code and ideas wherever that
  helps (persona signals, Customer State, Kate's propose-then-confirm pattern).

## Direction for the backend (not final; record decisions in the log)

Building blocks that follow the 5 journey steps:
- **Intent detection**: signals (transactions, life events, what the customer says) → a goal ("buy a house",
  "build up my pension").
- **Goal / journey model**: a goal becomes a plan of steps, with a status, deadlines and a measurable outcome.
- **Partner network**: a registry of vetted partners (broker, insurer, fund, agent, contractor…) with their
  capabilities, and a value-sharing model for each partner.
- **Orchestration**: KBC routes each step to the right partner or KBC service and tracks progress.
- **Consent and trust**: the customer approves every step and every piece of data shared with a partner. AI
  proposes, the customer confirms (as Kate does in v1).
- **Outcome tracking**: measurable results for the customer, KBC and partners (the triple win made visible).

## Rules for working here

- Test every idea against the **triple win** and the **don't build** list. No generic chatbot, no extra screen for
  its own sake.
- With a hard 16:00 deadline: a **working proof of concept** of one strong journey beats a broad half-finished system.
- **Synthetic data only.** Partners and offers are illustrative, not real KBC products or contracts.
- Secrets only in `.env` (never commit it). Keep the v1 security habits: the customer comes from the session,
  inputs are validated, and nothing is done without the customer's confirmation.
- Record important choices and progress in [docs/LOG.md](docs/LOG.md) (newest at the top).
