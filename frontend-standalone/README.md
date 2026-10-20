# KBC Adaptive Home — standalone frontend

This folder is an independent copy of the existing React interface for frontend development. You can move or copy this entire folder anywhere and run it there. It needs no Python, backend, database, environment file, API key or files from the parent project.

## Start

Open a terminal in **this folder** and run:

```powershell
npm.cmd run dev
```

Open **http://127.0.0.1:5174**. On Windows you can also double-click `start.cmd`. Stop the server with **Ctrl+C** in its terminal.

Only Node and npm need to be installed. The launcher installs this folder's locked dependencies when needed. If your installed Node is older than 22.12, it uses a temporary Node 22 runtime from npm without replacing your installed Node. The first setup needs internet access. Node 22.12+ can run the dependencies directly.

Port 5174 is reserved for this preview, so it can run beside the original frontend on 5173. If the port is busy, stop the other instance or run `npm.cmd run dev -- --port 5175` and use the URL printed in the terminal.

## Evaluate

Choose a customer in the left demo panel or on the login screen. Demo password: **`demo`**.

- **Lotte:** student-to-freelancer time travel and a freelance journey.
- **Sara:** freelancer/family layout, recommendations and deadlines.
- **Jan:** retirement layout and safety signals.
- **Marc:** wealth and pension goals.
- **Advisor:** ecosystem console and your browser's simulated journey activity.

The home has three parts: the top bar (name, date, notifications and Profile), the KBC logo (light-blue ball on a rising band) with the primary account inside the ball, and a scrollable **For you** tile wall. Every tile is a whole multiple of a square unit (half the screen width): 1 or 2 units wide, and as many units tall as its content needs. Balances, upcoming payments, summaries, metrics and savings plans are visible before opening a tile. In edit mode (Profile → Edit home, or **Edit tiles**) you drag tiles onto any free or taken spot, remove tiles with their × button, and tap a free spot to fill it. **+ Add row** adds spots that stay free for your own choices. Free spots, Pinned/Suggested labels and × buttons appear only in edit mode.

**Goals** has its own tab in the bottom navigation (in place of More). It shows an overview (goals in motion, steps done, savings so far), active goals with progress and the next step, every available goal (KBC’s suggestions first, with reason and potential benefit), and achieved goals. Tap any available goal to see its full roadmap, then choose **Approve & start** or **Not now**. Previewing or closing a roadmap does not create a goal or grant access. Home tiles still open their full details, actions and feedback.

**Profile** contains settings and appearance, permissions and connected sources (the consent passport), and home editing. Kate, journeys and the advisor console remain available. All data comes from the JSON fixtures in this folder. Tiles, feedback, theme, goal progress, consents, source connections and nudge acknowledgements are saved separately for each customer in this browser's local storage. The demo session also survives refresh.

Try starting a goal, approving a KBC step, and approving a partner step. The partner completes locally after about two seconds plus the UI's polling interval. You can inspect/revoke its consent, switch customers, or reload. **Reset preview** in the left panel clears all saved demo choices and signs out; the narrower feedback/goals/nudges/style reset controls also remain available.

This is a UI sandbox: logins are local demo selections, partners and source connections are simulated, and no money moves or data leaves the app. Historical screens use saved snapshots; dragging between snapshot dates reuses the latest earlier sample rather than running the original financial engine. Kate uses local scripted responses. Console detection counts are fixed synthetic samples; goal activity reflects your browser's saved actions. No `?mock=1` flag is needed.

## Where to edit

| File or folder | Purpose |
|---|---|
| `src/App.tsx`, `src/Phone.tsx` | App state and phone layout |
| `src/components/` | Home tiles |
| `src/accounts/` | Account drill-down and chart |
| `src/feed/`, `src/ui/` | Feed cards, settings and Kate |
| `src/ecosystem/`, `src/nudges/` | Journey, consent, console and notification UI |
| `src/index.css`, `src/theme.ts` | Global appearance and theme |
| `src/demo-data/customers.json` | Bundled customer screens, tile props and all 13 journey templates |
| `src/demo-data/overview.json`, `src/demo-data/nudge-stats.json` | Console sample data |
| `src/data.ts`, `src/demo/` | Browser-local interaction adapters and saved demo state |
| `vite.config.ts` | Independent dev server; no backend proxy |

Changes to source files update the browser through Vite's hot reload. Keep future frontend work inside this folder. The original `frontend/` and `backend/` are independent from this preview.

## Build and browser checks

```powershell
npm.cmd run build
npm.cmd run preview
```

The build is written to `dist/`; preview serves it at **http://127.0.0.1:4174**. Any static web server can serve `dist` independently.

```powershell
npm.cmd test
```

The browser tests cover customer/advisor rendering without API requests, roadmap previews and approval, account and recommendation drill-downs, profile permissions and privacy, journey completion/revoke, saved appearance, customer isolation and resetting a pending journey. On Windows they use installed Microsoft Edge. On other systems, install Playwright's Chromium once (`npx playwright install chromium`) before running tests. Browser tests use isolated browser contexts and do not clear your normal browser's saved demo.
