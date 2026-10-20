# Standalone frontend working notes

This directory is the active frontend-only sandbox. Preserve the existing UI unless the user requests a change.

- Keep this folder independently runnable. Do not import source, assets or runtime data from the original `frontend`, `backend` or any parent folder.
- Use the bundled JSON fixtures and browser-local adapters for demo interactions. Do not add backend requests or a Vite API proxy unless the user explicitly requests integration.
- All customer data and partner behaviour are synthetic. The demo login is a local persona picker, not an authentication system.
- Run with `npm run dev` (port 5174), build with `npm run build`, and check significant interaction changes with `npm test`.
- The launcher in `scripts/run.mjs` handles the installed Node version and locked dependency installation. Keep it portable and avoid absolute machine paths.
- Update this folder's README when the run steps or local demo behaviour change.
