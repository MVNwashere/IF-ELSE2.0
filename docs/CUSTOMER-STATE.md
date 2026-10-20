# Customer State

Customer State is a backend banking-data foundation, separate from the customer app's layout engine. It describes
observations, calculations, supported patterns, historical changes and uncertain financial inferences. Nothing in
`backend/app/customer_state/` imports `app.engine` or the recommender, ranks content, or chooses UI.

The For You feed consumes it through `backend/app/recommender/`. The layout planner and Kate use the feature
pipeline in `backend/app/engine/features.py` instead (see [CUSTOMER-APP.md](CUSTOMER-APP.md)).

## Architecture

```text
SQLite banking records + synth data
  -> normalization.py: raw observations -> canonical signals
  -> metrics.py: financial calculations
  -> patterns.py: cadence, changes and transaction events
  -> inference.py: replaceable inference provider + financial conditions
  -> service.py: validated CustomerState + persisted snapshot
  -> api.py: session-bound full state or domain projection
```

`models.py` defines backend-only Pydantic contracts. Raw records remain in `transactions` and `accounts`.
Two additive source tables store optional transaction details and dated account observations; existing
databases acquire them through `db.init_schema()`. `storage.put_details()` accepts currency, account,
merchant ID, canonical category, subcategory, country, location, timestamp, payment method, internal
transfer and sensitive flags, plus a source label (including external/open-banking sources).
`storage.put_account()` accepts dated current/savings balances and positive outstanding loan/credit
principal. An observation is an end-of-day balance; movements on later days update liquid balances.
Account IDs must be consistent between details and observations. Upsert a source record with its same
ID to correct it. The original transaction category and counterparty are never overwritten.

The adapter also includes customer products and the recorded last app visit. It deliberately excludes
synthetic ground truth, demographic persona inference, UI preferences, feedback, and declared sensitive
life events. There are currently no financial-goal records to import. Product ownership alone does not
establish a savings balance or loan principal: unavailable values are `null`, not invented zeroes.

## Retrieve state

Use the normal login/session cookie, then:

```text
GET /api/me/customer-state
GET /api/me/customer-state?as_of=2026-08-31
GET /api/me/customer-state/income
GET /api/me/customer-state/cash-flow
```

The domain route accepts `overview` (financial position), `income`, `expenses`, `spending`, `cash-flow`,
`savings`, `debt`, `recurring`, `subscriptions`, `patterns`, `changes`, `events`, `inferences`, `risks`,
and `opportunities`. Domain responses retain dates, currency, freshness and calculation provenance.
Customer identity always comes from the session; passing another customer ID has no effect. Advisor
sessions do not gain individual customer access. No new advisor-data authorization policy is introduced.

The API caps `as_of` at `DEMO_TODAY` (default `2026-09-30`), matching the repository's demo clock.
Dates before available history return empty/unknown state without exposing later observations. To
ingest later demo transactions, advance `DEMO_TODAY` and supply corresponding balance observations.

Backend consumers can call the service directly:

```python
import datetime as dt
from app import db
from app.customer_state.service import get_state, get_domain

with db.tx() as conn:
    state = get_state(conn, customer_id, dt.date(2026, 9, 30),
                      balance_reference=dt.date(2026, 9, 30))
    income = get_domain(state, "income")
```

## Calculation policy and limits

- Amounts use existing signed ledger values; output money is rounded to cents, ratios to four decimals.
  Existing records default to EUR and the current account, with that assumption exposed in limitations.
  Other currencies remain in raw observations/signals but are excluded from EUR calculations; there
  is no implicit FX conversion. Never label a foreign amount EUR at ingestion.
- Monthly averages use at most six **complete calendar months**. The first partial month and current
  partial month are omitted. Zero-activity months within the observed span are included. Coverage is
  assumed to begin with the first transaction because the legacy schema has no feed-coverage marker;
  a first transaction after the first day conservatively excludes that month. Fewer than three complete
  months gives unknown income stability. No complete month gives unknown averages and projections.
- Income uses explicit income categories. Positive refunds reduce expenses, not inflate salary. Savings
  transfers and internal transfers are excluded from income and spending. Net savings is transfers into
  savings less withdrawals, divided by complete months; savings rate is this amount divided by income.
  The current-account side of a savings transfer is classified as saving; an explicitly identified
  savings-account counterpart is an internal transfer, so both legs are not counted twice.
- Fixed expenses are historical charges belonging to detected bills, including subsequently stopped
  bills. Groceries and other repeating purchases are merchant patterns, not fixed bills. Essential and
  discretionary use explicit category sets; unknown categories remain unclassified. Refunds reduce the
  unclassified/net residual rather than being assigned an inferred essential/discretionary purpose.
- Cadence groups use canonical merchant/counterparty, category, direction and account. Weekly, monthly
  and quarterly patterns require three distinct dates; yearly requires two. At least 75% of intervals
  must fit the cadence tolerance (2/7/12/16 days respectively). Amount variability lowers confidence;
  changing salary, subscription or utility amounts do not prevent date-pattern detection. Recognized
  bill categories or explicit direct-debit/standing-order methods distinguish bills from repeat visits.
  This is a heuristic; weekly/quarterly dates with fewer observations remain unconfirmed.
- Salary/subscription/debt-payment changes require at least a 5% change against the preceding median
  and preceding charge. Category changes require a three-month baseline, at least EUR 50 and 30%.
  Savings/free-cash-flow changes require at least EUR 100 and 30%. These are descriptive thresholds,
  not advice. New merchants/categories require at least 60 days of preceding history. Large expenses
  require at least 10 earlier purchases and exceed both EUR 500 and four times the personal median.
- Free cash flow is income minus net expenses **before savings transfers**. Monthly current-account
  inflow/outflow additionally exposes actual cash movements. Liquid cash buffer is known liquid
  balance divided by monthly net expenses; it covers known accounts only. Buffer changes compare
  matching observed account sets against the same preceding three-month spending denominator, with
  a threshold of 10% and 0.25 months. Debt principal trend uses matching observed account sets; never
  subtract a whole mortgage payment from principal because payments can include interest.
- Projections schedule active detected inflows/outflows on the current accounts and add historical
  daily spending excluding scheduled charges. They include recurring savings sweeps and avoid counting
  bills twice. They exclude irregular income and unobserved future transactions. An overdue occurrence
  within its grace period is projected tomorrow; a pattern beyond grace becomes inactive and produces
  a disappearance event. Calendar month ends are clamped, not advanced by a fixed 30 days. The lowest
  balance is an end-of-day projection, not an intraday minimum. All projections are estimates.
- Low liquidity means projected balance below zero (high), or below the greater of EUR 100 and 20%
  of monthly expenses (medium). Debt service above 40% produces a financial condition. Subscription
  cost increases within 60 days produce a condition. These thresholds do not determine presentation.
- The legacy undated `balance_today` is reconstructed by reversing later ledger transactions through
  the supplied balance reference date, as the existing repository does. Its source is explicitly
  `legacy_ledger_reconstruction`; this is not a historically observed balance. Explicit current-account
  observations supersede that fallback. Dated source balances/transaction ages and excluded currency
  counts are exposed under freshness; stale or missing feeds are not silently claimed to be current.
- Foreign-country observations support only a low-confidence **possible recent travel** cluster, never
  an upcoming trip or confirmed physical location. Sensitive categories (including healthcare), sensitive
  subcategories and records marked `sensitive` contribute to aggregate cash totals but become an anonymous
  `other` signal and do not produce merchant/category patterns, travel inference or profile events.
  Source adapters must mark sensitive merchants they recognize; this is not a merchant-name classifier.
  Raw banking records are retained as raw facts. No personality or sensitive-life profiling is performed.

## Persistence, provenance and refresh

`customer_state_snapshots` is a replaceable derived cache keyed by customer, as-of date and algorithm /
inference-provider version. The service hashes the entire eligible source bundle, including metadata,
activity and account observations. A source insertion, correction or deletion rebuilds the requested
snapshot on the next read; unchanged requests return the same state and `generated_at`. No frontend
write is needed. A job or transaction-ingestion handler can call `get_state` after writing records in
the same transaction. Increment the algorithm/provider version when behavior changes.

SQLite rebuilds reserve a write transaction before loading source tables, preventing mixed-source
snapshots under concurrent writers. The caller commits or rolls back. This intentionally follows the
small SQLite application's scale; high-volume ingestion would need a background recalculation queue.

Snapshots contain the source observations needed for replay/explanation, so a full response is larger
than a domain projection. They never replace banking records. Historical as-of snapshots are retained;
rebuilding an identical as-of/version replaces that cache entry instead of appending duplicate events.
Patterns and changes have deterministic IDs based on entity, source evidence and detection date, not
wall-clock generation time. Price and monthly change history is recalculated from retained source
history; missed recurring payments remain detectable after resumption. Correcting source history can
correct derived history. This is a derived cache, not an immutable audit log or a bitemporal database.
No cache-pruning job is installed; deployments should choose their retention policy.

Provenance groups cover calculation periods, transaction IDs, account-observation IDs, pattern IDs and
method identifiers. Pattern/inference confidence is separate from calculated values. `created_at`,
`updated_at` and optional `review_at` express inference lifecycle; uncertainty is never promoted to a fact.

## Extend the capability

1. **Signal:** add upstream fields to `TransactionDetails` or a separately typed observation source,
   persist through a source adapter, and map it in `normalization.py`. Canonical-category overrides
   support categories such as `loan`, `credit` or `restaurants` without rewriting old transaction rows.
   Register any sensitive classification before adding pattern rules.
2. **Metric:** add a typed domain field in `models.py`, calculate it in `metrics.py`, include evidence and
   its calculation window, and test exact values on a deterministic ledger. Choose `null` for unsupported
   measurements and document transfer/currency/partial-period semantics.
3. **Pattern/change:** add a typed change vocabulary entry if needed, implement in `patterns.py`, assign
   a stable ID and source evidence, and test the history before and after the event and on recalculation.
4. **Inference:** implement `InferenceProvider.version` and `infer(state) -> list[Inference]`, then inject
   it into `get_state`. The default `RuleInference` stays deterministic. A future ML/LLM provider must
   obey the same sensitive-data boundary, confidence, evidence and lifecycle contracts; none is wired now.

## Synthetic data and tests

Existing `synth.generate` and `synth.demo_customers` data work unchanged. The additive scenario module
provides stable/variable income, a raise, many subscriptions with a price increase, rising discretionary
spending, declining buffer, increasing savings, mortgage repayments, upcoming negative balance and
foreign spending. It adds realistic account observations and transaction details; no customer state is
hardcoded in the service. IDs 100001–100010 are reserved for these scenarios.

From `backend/`, after generating the normal DB (or against a new dedicated DB):

```bash
python -m synth.customer_state --db kbc.db
python -m pytest
```

The seed command appends transactionally and refuses customer-ID collisions; it does not erase existing
data. Logins are `state_stable`, `state_variable`, `state_salary_increase`, `state_subscriptions`,
`state_spending_increase`, `state_declining_buffer`, `state_growing_savings`, `state_debt`,
`state_low_balance`, `state_foreign`, using `DEMO_PASSWORD` (default `demo`). Tests seed isolated databases
and assert calculations, uncertainty, transfer/refund treatment, sensitive suppression, evidence,
historical isolation, migration, cache invalidation, domain access and customer-session isolation.

On a Windows machine where pytest's default shared temp directory is inaccessible, pass a fresh path
inside the repository, e.g. `python -m pytest --basetemp .pytest_cache/customer-state-validation`.
