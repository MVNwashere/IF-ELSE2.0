# Frontend design decisions

Why the home looks the way it does. Written while the redesign lived in a separate `frontend-standalone/` sandbox;
on 20 October 2026 it replaced `frontend/`, wired to the backend (the sandbox's fixture engine is now the `?mock=1`
demo mode). Newest first.

## 20 October 2026 — Today, one number per fact, a wall that fits its tiles

- **Why:** a review of all nine customers found the home contradicting itself (two "upcoming bills" lists from two
  detectors, spending for "this month" next to the last 30 days, a savings goal always at 100%, an invoice tile
  listing top clients under "3 unpaid", account balances invented in the browser) and hiding what mattered: the
  engine's urgent cards (VAT due today, a possible scam) were replaced by generic tips, and the persona's own main tile
  was never shown. Fixed at the source in the backend (`recommender/compose.py`, see CUSTOMER-APP.md).
- **Today** sits under the KBC ball: the persona's main tile (VAT reserve with "Set it aside now", pension, family
  budget; not the balance tile, which only repeats the ball), up to two urgent moments with their action, "Ask Kate"
  and "Why this?", and the one goal KBC noticed. Urgent cards shown there leave the wall.
- **The ball** shows the real current-account balance (the same number as everywhere else) and counts up. No more
  made-up savings or reserve accounts.
- **The wall is masonry**: 4 px rows, each tile spans exactly its content, so short tiles no longer sit in empty
  squares. Every suggested tile gets a place (the fixed 12-slot area silently dropped quick actions and savings).
  Tiles animate in again whenever the customer or the date changes.
- **Tiles say what they are**: an icon per card type, a tone (urgent red, soon amber, opportunity green, tips quiet
  and smaller), and type-specific bodies: "Coming up" lists who gets paid when, "Spending" has a category bar, the
  balance dip shows today → lowest point. Minimum text size about 12 px.
- **Goals**: "Suggested for you" (detected), "Explore goals" with life-area filters (compact list when showing all),
  and "Probably not for you right now", folded, each with its reason (backend `ecosystem/fit.py`).
- **Goal reached** gets its own moment: the verified euros and hours, and the next goal.
- **About you** proposes what the transactions point to ("We think: 1 child · Confirm"); nothing is stored until
  the customer confirms.
- **Login** shows the nine customers as cards with their one-line story; switching customers shows the next phone
  loading instead of flashing the login form. The console reports time per customer and sorts the funnel by
  detections on one shared scale.
- Mock fixtures are regenerated from the backend with `py -3.12 -m scripts.export_demo_fixtures` (from `backend/`).

## 20 October 2026 — Merged into frontend/

- The redesign is the app's only frontend. It reads and writes through the backend; `?mock=1` / `npm run dev:mock`
  runs the same UI on the bundled fixtures. The wall arrangement is stored per customer by the backend
  (`PUT /api/me/tile-grid`), and goal roadmaps come from `GET /api/me/goals/preview/{id}`.
- Kept from the backend-connected app: the customer profile ("What KBC knows about you", now in the Profile hub), Kate's
  profile actions, household invitations (in the Goals tab), paused and shared goals, and the privacy masking fixes.
- Removed with the old home: the goals strip, the tile gallery sheet and the "your life changed" suggestion banner.

## 20 October 2026 — Goals tab, square tile units, reference logo

- Redrew the logo from the supplied reference: one light blue (#00aeef), a round ball just right of centre dipping into a full-width band that rises gently to the right, separated by a background-coloured gap ring. Removed the wordmark, which the reference does not show.
- For you tiles are now whole multiples of a square unit (half the grid width): 1 or 2 units wide, as many units tall as the content needs, measured at runtime. Placement order is kept; dense packing fills holes.
- Pinned/Suggested labels appear only in edit mode; edit tools overlay the tile so sizes do not change when editing.
- Goals moved from a feed tile to a dedicated Goals tab that replaces More in the bottom navigation. All available goals are listed; tapping one opens its roadmap with Approve & start or Not now. The triple-win breakdown was removed from the customer journey (fee disclosure in consent remains).
- Edit mode: drag and drop replaces Move/resize/Pin buttons; each tile has only a remove (×) button. Free spots show only while editing and are tapped to fill; the always-visible Add a tile placeholders and + Add tile button were removed.

## 20 October 2026 — Goals join the For you feed

- Removed the separate goals section. The home now flows from top bar to KBC logo to one For you feed.
- Added Your goals as a full-width tile after the first two quick summary tiles, preserving roadmap previews and approval.
- Made useful information visible on tiles: amounts, payment dates, descriptions, metrics, savings-plan progress, goal benefits and next steps.
- Let content determine tile width and height; detailed or urgent recommendations span the grid, while quick summaries remain compact.

## 20 October 2026 — Home redesign

- Kept all implementation and documentation changes inside `frontend-standalone`, as requested.
- Recreated the supplied KBC circle and rising baseline in SVG/CSS, with the primary account's balance, account name and masked account number inside the circle. Account drill-down remains available.
- Simplified the top bar to name/date, notifications and Profile. Settings, data permissions and home editing live in Profile.
- Limited “KBC noticed” to two suggestions. Each opens a complete roadmap from the bundled journey template without creating saved goals or consents. A single “Approve & start” action creates the goal; existing explicit step and partner-sharing approvals remain.
- Placed the For you recommendations beneath the goals as a two-column tile grid, retaining detailed information, feedback and actions in the detail sheet.
- Preserved per-customer local state, theme controls, privacy masking and the independent, backend-free runtime.
