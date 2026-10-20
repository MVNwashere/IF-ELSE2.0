# Component props contract

The layout planner (`backend/app/engine/layout.py`) builds these props from `Features`.
The frontend (`frontend/src/components/*.tsx`) renders exactly these props. Both sides must agree.
All amounts are plain numbers in EUR (positive). Dates are ISO `YYYY-MM-DD`. Every field is always present
(use `0`, `[]` or `null` rather than omitting).

| Component | size | props |
|---|---|---|
| `BalanceHero` | hero | `{ balance_eur, monthly_income_eur, monthly_spend_eur, trend_30d_eur, sparkline: number[] }` — sparkline = 30 daily end-of-day balances ending at `as_of` |
| `RunwayHero` | hero | `{ balance_eur, runway_days: number \| null, next_income_date: string \| null, next_income_eur: number \| null, daily_budget_eur }` — daily budget = balance ÷ max(1, days until next income) |
| `FamilyBudgetHero` | hero | `{ month_label, month_income_eur, month_spent_eur, month_budget_eur, child_benefit_eur, childcare_eur, top_categories: [{category, eur}] }` — top 4 categories this month |
| `TaxReserveHero` | hero | `{ quarter_label, quarter_income_eur, reserve_eur, reserve_pct, vat_due_date, days_to_due }` |
| `PensionHero` | hero | `{ balance_eur, pension_eur, pension_received_date: string \| null, next_pension_date: string \| null, upcoming_bills_eur, upcoming_bills_count }` |
| `ForYouFeed` | full | `{}` (cards come from `feed.cards`) |
| `QuickActions` | full | `{ actions: [{label, action, icon}] }` — 3–4 items; `icon` ∈ `transfer, split, invoice, scan, call, savings, card, insurance, budget, pension` |
| `UpcomingBills` | half | `{ bills: [{counterparty, amount_eur, date, category}], total_eur }` — next 14 days, max 5 |
| `SplitBills` | half | `{ recent: [{counterparty, amount_eur, date}], hint }` — recent shareable spends (leisure/groceries), max 3 |
| `InvoiceTracker` | half | `{ unpaid, unpaid_eur, paid_quarter_eur, clients: [{name, eur, last_date}] }` — clients = distinct invoice payers last 180d, max 4 |
| `SavingsGoal` | half | `{ goal_label, saved_eur, target_eur, monthly_eur }` |
| `ScamShield` | half | `{ tips: string[], hotline }` — 3 tips |
| `AdvisorContact` | half | `{ advisor_name, reason, slots: string[] }` — 2–3 slot labels like "Tue 14:00" |
| `SpendingByCategory` | half | `{ month_label, total_eur, categories: [{category, eur}] }` — top 6 |
| `KateTile` | full | `{ prompt, card_key: string \| null, quick_replies: string[] }` — Kate's opener about the top feed card; tapping opens the Kate chat with that card as context |
| `SubscriptionsTile` | half | `{ monthly_total_eur, count, items: [{counterparty, amount_eur, period_days, previous_amount_eur: number \| null}] }` — max 6, biggest first; `previous_amount_eur` set when the price changed |

Sizes: `hero` (the first section, full width, big), `full` (full width), `half` (half width; two halves sit side by side, an odd one stretches).

Rules:
- Exactly one hero, always first. `ForYouFeed` always second.
- `Section.pinned` is true for tiles the customer pinned; pinned tiles keep their slot while the rest adapts.
- The frontend must ignore unknown component names (log a warning, render nothing).
- The frontend never receives HTML; all strings are rendered as text.

## Optional: `accounts` on the hero (tap the hero tile → accounts screen)

Tapping the hero tile zooms open an accounts screen. The hero tile summarises the account the customer uses most, so
`accounts[0]` is that account. The backend may add this **optional** field to the props of whichever `*Hero` it picks
(nothing breaks when it is missing or malformed: the frontend then shows clearly labelled demo accounts derived from
the persona mix, see `frontend/src/accounts/accounts.ts`).

```jsonc
"accounts": [                       // max 4 are shown; the first is the "Most used" one
  { "id": "main",        "kind": "current",  "name": "Current account", "last4": "4821", "balance_eur": 3165.2 },
  { "id": "tax_reserve", "kind": "reserve",  "name": "Tax reserve",     "last4": "9568", "balance_eur": 1840 }
]
```

`kind` ∈ `current, savings, reserve, child, business, joint` (unknown values fall back to `current`).
`last4` is the last four digits only; the frontend never receives a full IBAN.

Picking an account in that screen turns it into the big blue tile with a balance curve, money in/out (30 days) and a
scrollable history. An account may carry its own real bookings; without them the frontend derives demo bookings
(`frontend/src/accounts/history.ts`) that end exactly on `balance_eur`.

```jsonc
{ "id": "main", "kind": "current", "name": "Current account", "last4": "4821", "balance_eur": 3165.2,
  "transactions": [                 // any order; positive = money in, negative = money out; ~last 75 days is enough
    { "date": "2026-09-26", "counterparty": "Employer NV", "category": "salary",    "amount_eur": 2480 },
    { "date": "2026-09-28", "counterparty": "Colruyt",     "category": "groceries", "amount_eur": -64.2 }
  ] }
```

`category` uses the transaction categories from `Category` in `backend/app/schemas.py` (unknown values still render, with a generic icon).
The balance curve is computed backwards from `balance_eur` and the bookings.
