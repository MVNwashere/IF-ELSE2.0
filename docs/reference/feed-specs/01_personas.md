# Personas: Card-Based Banking Feed PoC

This document defines the personas that drive which cards appear in the feed. Together they are meant to cover the whole retail customer base of a bank, from a 14-year-old with a youth account to a 80-year-old pensioner.

## How personas are used

- **Personas are soft labels, not boxes.** A customer gets a *score* (0 to 1) per persona, computed from age, income pattern, products held, transaction behaviour and life events. One customer can be e.g. `PAR 0.8` + `SELF 0.6` (a parent who is also freelance).
- **The persona score is a prior, not the final decision.** Actual card ranking combines: persona fit + live triggers (e.g. insurance due in 14 days) + the customer's own click/dismiss history.
- **Personas change over time.** A `STU` becomes `YPRO` after the first salary arrives; a `PAR` becomes `HOME` when the kids are teens; a `PRE` becomes `SEN`. The feed should adapt without the customer doing anything.
- **Every card in the catalogue lists the personas it targets** using the codes below.

## Persona overview

| Code | Persona | Typical age | One-line summary |
|------|---------|-------------|------------------|
| TEEN | Teen / Youth Account | 12-17 | Learning about money, pocket money, parent-supervised |
| STU | Student | 18-25 | Low income, tight budget, first independence |
| YPRO | Young Professional | 22-34 | First steady income, building a life, renting |
| PAR | Parent / Young Family | 28-45 | Kids under 12, high fixed costs, time-poor |
| HOME | Established Household | 35-58 | Homeowner, mortgage, teens, peak expenses and earnings |
| SELF | Self-employed / Small Business Owner | 25-65 | Irregular income, mixes private and business finances |
| INV | Active Investor / Affluent | 30-75 | Has meaningful assets, wants performance and optimisation |
| PRE | Pre-retiree | 55-67 | Planning the transition, pension focus, empty nest |
| SEN | Retiree / Elderly | 67+ | Fixed pension income, wants simplicity, safety and clarity |

---

## TEEN: Teen / Youth Account

**Who they are:** Minors holding a youth account linked to a parent or guardian. Their money is pocket money, gifts, and maybe a first holiday job. Spending is mostly small purchases, gaming, snacks, transport and online items.

**Financial characteristics**
- Very small balances, frequent small transactions
- Debit card with strict limits, no credit or overdraft
- Parent has oversight and can set limits

**What they care about**
- Seeing how much they have and how long it lasts
- Saving for a specific thing (phone, concert, bike)
- Understanding money in a simple, playful way

**Feed tendencies:** Short, visual, gamified cards. No jargon. No risky products. Lots of "learn" and "goal" content. Everything must be age-appropriate and parent-safe.

**Signals to detect:** Account type = youth, age < 18, parent-linked profile, tiny transaction sizes.

---

## STU: Student

**Who they are:** 18-25 year olds in higher education or vocational training. Income comes from parents, a student grant or loan, and a part-time job. Often living away from home for the first time.

**Financial characteristics**
- Low, irregular income; balance drops toward month end
- Rent, groceries, transport, subscriptions, social spending
- Little or no savings, may use overdraft
- No or minimal insurance, first-time renter

**What they care about**
- Making it to the end of the month
- Cheap subscriptions, student discounts
- Learning the basics: taxes, rent deposit, first insurance
- First jobs, internships, summer work

**Feed tendencies:** Budget and cash-flow cards high. Discounts, practical life admin ("how to get your rent deposit back"), cheap small-step saving. Little investment content except beginner education.

**Signals to detect:** Age 18-25, university/school payments, student grant deposits, low income, rent + groceries dominated spending.

---

## YPRO: Young Professional

**Who they are:** 22-34, first full-time job or early career. Usually renting, possibly in a relationship, often no kids yet. Starting to think about buying a home, travelling more and investing.

**Financial characteristics**
- Regular salary, rising income
- Rent or first mortgage, car or public transport pass
- Spending on travel, dining, fitness, subscriptions, shopping
- Starting to save; curious about investing

**What they care about**
- Saving for a home deposit, travel and lifestyle
- Getting started with investing without being an expert
- Managing subscriptions and lifestyle creep
- Tax returns, first real insurance, first pension

**Feed tendencies:** Savings goals, investing starter cards, travel content, subscription management, home-buying education, digital convenience.

**Signals to detect:** Age 22-34, monthly salary deposit, rent payments, increasing card spend, first investment/savings activity.

---

## PAR: Parent / Young Family

**Who they are:** Adults (often 28-45) with one or more children under roughly 12. Two incomes or one, with high fixed costs and little spare time. Includes single parents. The "mom" and "dad" personas live here.

**Financial characteristics**
- Childcare, school costs, child benefit, health costs
- Groceries, family car, larger insurance needs (life, liability, health)
- Mortgage or expensive rent, family holidays
- Wants to save for children's future (education account)

**What they care about**
- Keeping the household budget under control
- Protecting the family (insurance, emergency buffer)
- Saving for kids (child savings, education, first bike to first car)
- Saving time: automating payments, shared visibility with partner

**Feed tendencies:** Household cash-flow, insurance coverage, child-related saving and benefits, family holiday content, school-year cost planning, family-friendly tips.

**Signals to detect:** Childcare/school payments, child benefit deposits, kids' clothing/toy merchants, family insurance, child accounts linked.

---

## HOME: Established Household

**Who they are:** 35-58, typically homeowners with a mortgage, teenagers or young adults at home, and peak earning years. Finances are complex: multiple products, bigger sums, long-term planning.

**Financial characteristics**
- Mortgage with rate resets, home maintenance, energy bills
- Two cars, multiple insurances, higher taxes
- Supporting teens or students (allowances, tuition)
- Begins serious pension and investment planning

**What they care about**
- Reducing mortgage cost and energy bills
- Paying for kids' education and first independence
- Home improvement and maintenance budgets
- Long-term wealth building and pension gap

**Feed tendencies:** Mortgage and loan optimisation, home and energy cards, insurance review, tax optimisation, education financing, pension projection.

**Signals to detect:** Mortgage product, home insurance, energy provider payments, teens linked as youth accounts, larger stable income.

---

## SELF: Self-employed / Small Business Owner

**Who they are:** Freelancers, sole traders, small shop owners, contractors. Income is irregular and private and business money often overlap.

**Financial characteristics**
- Irregular invoices and payment delays
- VAT, quarterly taxes, social contributions
- Business expenses (software, equipment, vehicle, fuel)
- Needs buffer for slow months; no employer pension or sick pay

**What they care about**
- Cash-flow forecasting and tax reserve
- Invoice tracking and late payers
- Separating business and private spending
- Their own pension and disability cover

**Feed tendencies:** Income volatility, tax-deadline cards, invoice and VAT reminders, business expense insights, income protection and pension cards.

**Signals to detect:** Invoices received from many payers, VAT/tax payments, business account or business-like merchants, irregular income pattern.

---

## INV: Active Investor / Affluent

**Who they are:** Customers with meaningful investable assets or high savings balances, regardless of age. They actively check performance and want efficiency and advice.

**Financial characteristics**
- Investments across funds, stocks, bonds, maybe property or crypto
- Large savings balances possibly earning little
- Tax-aware, looking for diversification and estate planning

**What they care about**
- Portfolio performance vs benchmark
- Fees, tax efficiency, allocation and risk
- Market events that affect them
- Wealth transfer and legacy

**Feed tendencies:** Portfolio, market news relevant to their holdings, idle cash, rebalancing, tax cards, advisory appointments, alternative assets.

**Signals to detect:** Investment products, high balances, frequent trades, high-tier card, advisory contact.

---

## PRE: Pre-retiree

**Who they are:** 55-67, typically kids have left home, mortgage nearly paid, retirement approaching. Focus shifts from accumulating to protecting and planning income.

**Financial characteristics**
- High earnings plateau, substantial pension assets
- Decreasing fixed costs, increasing health costs
- May help adult kids or care for elderly parents

**What they care about**
- "Can I retire, and when?", pension projection and gap
- Converting assets to income, de-risking
- Downsizing, inheritance, healthcare
- Keeping lifestyle while costs shift

**Feed tendencies:** Retirement projection, pension overview, de-risking, downsizing, care cost planning, travel and leisure planning, digital safety.

**Signals to detect:** Age 55-67, mortgage ending, pension contributions, kids' accounts closed, health spending increase.

---

## SEN: Retiree / Elderly

**Who they are:** 67+ with pension income. Possibly less comfortable with digital tools and a prime target for fraud. Wants simplicity, large readable UI and trust. May have a trusted family member involved.

**Financial characteristics**
- Stable pension income, modest spending, high cash share
- Health, pharmacy, home care, energy, gifts for grandchildren
- Possible widow/widower situation, estate questions

**What they care about**
- Safety from scams and phishing
- Clear overview, no surprises, predictable bills
- Health and care costs, staying in their own home
- Gifts and support for family, legacy

**Feed tendencies:** Large type, plain language. Fraud warnings, bill calendar, pension payment confirmation, health cost tracking, simple savings, branch/phone support, trusted-contact features. No complex or high-risk products.

**Signals to detect:** Age 67+, pension deposits, pharmacy/health merchants, low digital session count, cash withdrawals, branch visits.

---

## Persona and feed behaviour quick reference

| Persona | Usually at top of feed | Tone | Density | Risk appetite shown |
|---------|------------------------|------|---------|--------------------|
| TEEN | Balance, goals, learning | Playful, simple | Low | None |
| STU | Cash-flow, bills, discounts | Casual, practical | Medium | Very low |
| YPRO | Spending, savings goals, investing starter | Friendly, modern | Medium-high | Low-medium |
| PAR | Household budget, insurance, child savings | Warm, efficient | Medium | Low |
| HOME | Mortgage, insurance, net worth | Professional | High | Medium |
| SELF | Cash-flow forecast, taxes, invoices | Direct, business-like | High | Medium |
| INV | Portfolio, markets, cash optimisation | Analytical | High | High |
| PRE | Retirement projection, pension | Reassuring, clear | Medium | Low-medium |
| SEN | Balance, bills, fraud safety | Calm, large, plain | Low | Very low |

## Persona inference: suggested starting rules (PoC)

These are simple rule-of-thumb scores for the PoC; replace with a model later.

| Persona | Key rules |
|---------|-----------|
| TEEN | age < 18 OR account_type = youth |
| STU | age 18-25 AND (education payments OR student grant OR income < threshold) |
| YPRO | age 22-34 AND monthly salary AND no child-related spend |
| PAR | child benefit OR childcare/school payments OR child accounts linked |
| HOME | mortgage product AND age 35-58 AND no young-child signals |
| SELF | many distinct payers OR VAT/tax payments OR business-account |
| INV | investable assets above threshold OR frequent trades |
| PRE | age 55-67 AND (pension contributions OR mortgage ending) |
| SEN | age >= 67 OR pension deposits as main income |
