import { defineConfig } from '@playwright/test';

// UI tests run against the demo engine (`npm run dev:mock`): bundled fixtures, no backend needed.
export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:5175',
    channel: process.platform === 'win32' ? 'msedge' : undefined,
    viewport: { width: 1440, height: 1000 },
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'npm run dev:mock',
    url: 'http://127.0.0.1:5175',
    reuseExistingServer: false,
    timeout: 180_000,
  },
});
