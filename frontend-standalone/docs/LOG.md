# Standalone frontend decisions

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
