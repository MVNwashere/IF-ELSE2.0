# Project log

Decisions and progress, newest at the top. Keep each entry short: what, why, and who.
The goal and context are in [CLAUDE.md](../CLAUDE.md).

## 2026-10-20

- **Decision: hero journey = Lotte goes freelance, told as a life timeline from today (20 Oct 2026) forward.**
  A KBC mentor advised against the house journey because KBC already covers house buying. Entrepreneurship is a
  suggested domain, and the pain (regularisation of social contributions, Peppol, VAT) comes later, which fits "before
  they realise". Future chapters (VAT, a trip, first employee, regularisation payoff) are simulated and chained: each
  finished goal feeds the next. Lotte's synthetic data must be re-dated (first invoice 16 Oct 2026). Details in
  ROUND2-DESIGN.md §3 and §8. (Henri)
- **Data re-dated:** `TODAY`/`DEMO_TODAY` = 2026-10-20. Lotte is employed until the end of Sep 2026 (last pay slip
  1 Oct), registers at the enterprise counter on 2 Oct and her first client pays on 16 Oct. Sara's car insurance now
  renews 1 Nov (12 days ahead), her Q3 VAT return is due today and she has two October invoices; Jan's duplicate charge
  and new payee moved to 17–18 Oct. The Customer State scenarios keep their own reference date (`SCENARIO_TODAY`
  = 30 Sep). Date-pinned tests updated; 174 pass. Delete `backend/kbc.db` to rebuild with the new data. (Henri)
- **Ecosystem engine built** (`backend/app/ecosystem/`, `frontend/src/ecosystem/`). KBC_Ecosystems.xlsx imported as
  the catalogue (229 building blocks, 21 ecosystems); 11 vetted partners with allowed fields and value-share models;
  8 playbooks (buy home, energy upgrade, new baby, go freelance, get paid, retire well, travel, safe banking) using
  55 building blocks. Intent rules with evidence; journeys with a consent passport (grant, expiry, revoke →
  step blocked); data minimisation enforced in code and at startup; HMAC-signed, idempotent partner webhooks, with
  simulated partners answering through the same path; triple-win ledger; KBC ecosystem console for the advisor
  login (funnel over 1,004 customers, partner network, live verified events, 2.3M projection with assumptions). Feed
  cards and Kate now start or open journeys. New synthetic signals: Lotte's house hunt (search alert, inspection,
  purchase deposit) and Nov 2022 energy bill. New persona **investor** (45–66, salary, idle wealth) and demo customer
  **marc** (52). The go_freelance playbook content is still round-1-generic and needs the freelance-hero details
  (regularisation, Peppol, advance tax). Facts on slides still to verify. (Henri, with Claude)
- **Docs:** round 1 docs marked. `KBC-QUESTIONS.md` is outdated (answers the round 1 brief); `DESIGN.md` is
  partly outdated (§4–§8 still describe the code). New [ROUND2-DESIGN.md](ROUND2-DESIGN.md) (draft): ecosystem
  engine design, API, demo script and work plan. It recommends the house journey as hero; still to be confirmed. (Henri)
- **Decision:** we bring our previous idea (IF-ELSE v1, Adaptive Home) into IF-ELSE2.0 with a new goal. v1
  becomes the customer-facing part; 2.0 builds the ecosystem engine behind it.
- **Repo set up** (IF-ELSE2.0): folders `backend/`, `frontend/`, `data/`, `docs/`, `notes/`.
- **Goal set:** KBC case "From intent to impact". We build the backend ecosystem engine behind the v1 front-end
  (Adaptive Home): intent → journey → vetted partners → measurable outcome, with KBC as the trusted orchestrator.
  Core idea: peace of mind for the customer, who can do everything in their own app.
- **Open:** which journey (life or business challenge) to demo first. Candidates: buying a house, the
  50-year-old investor (pension and wealth).
