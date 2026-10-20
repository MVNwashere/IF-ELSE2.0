import { expect, test, type Locator, type Page } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.route('**/api/**', (route) => { throw new Error(`Unexpected backend request: ${route.request().url()}`); });
});

test('all personas and the advisor load without a backend', async ({ page }) => {
  const errors: string[] = [];
  const apiRequests: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('request', (r) => { if (new URL(r.url()).pathname.startsWith('/api/')) apiRequests.push(r.url()); });
  await page.goto('/');
  for (const name of ['Lotte', 'Sara', 'Jan', 'Marc']) {
    await page.locator('aside.panel').getByRole('button', { name, exact: true }).click();
    await expect(page.locator('.phone h1')).toContainText(name);
    await expect(page.locator('.account-orb')).toBeVisible();
    await expect(page.locator('.recommendation-grid .goals-tile')).toHaveCount(0);
    if (name === 'Lotte') {
      await expect(page.locator('.section').first()).toHaveCSS('transform', 'none');
      await page.screenshot({ path: 'test-results/standalone-lotte.png', fullPage: true, animations: 'disabled' });
    }
  }
  await page.locator('aside.panel').getByRole('button', { name: 'Advisor', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'KBC Ecosystem Console' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Partner network' })).toBeVisible();
  expect(apiRequests).toEqual([]);
  expect(errors).toEqual([]);
});

test('a freelance journey approves, completes, revokes and survives reload', async ({ page }) => {
  await page.goto('/');
  await page.locator('aside.panel').getByRole('button', { name: 'Lotte', exact: true }).click();
  await page.getByRole('button', { name: 'Goals', exact: true }).click();
  await page.locator('.gs-option.suggested').first().click();
  await page.getByRole('button', { name: 'Approve & start', exact: true }).click();
  await expect(page.getByText('Keep business and private money apart', { exact: true })).toBeVisible();
  const business = page.locator('.eco-step').filter({ hasText: 'Keep business and private money apart' });
  await business.getByRole('button', { name: 'Review & approve', exact: true }).click();
  await page.getByRole('button', { name: 'Go ahead', exact: true }).click();
  await expect(business.locator('.eco-result')).toBeVisible();
  const invoicing = page.locator('.eco-step').filter({ hasText: 'Invoice the right way: Peppol' });
  await invoicing.getByRole('button', { name: /approve/i }).click();
  await page.getByRole('button', { name: 'Approve & share with Billit' }).click();
  await expect(invoicing.locator('.eco-result')).toBeVisible({ timeout: 10_000 });
  await page.getByRole('button', { name: /Consent passport/ }).click();
  await expect(page.getByRole('heading', { name: 'Billit', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Revoke access' }).click();
  await expect(page.getByText('revoked', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.locator('.phone h1')).toContainText('Lotte');
  await page.getByRole('button', { name: 'Goals', exact: true }).click();
  await expect(page.getByText('Start as a freelancer', { exact: true }).first()).toBeVisible();
  const state = await page.evaluate(() => JSON.parse(localStorage.getItem('kbc-demo-v1')!));
  expect(state.customers.lotte.goals[0].steps.find((s: { step_id: string }) => s.step_id === 'e_invoicing').status).toBe('done');
  expect(state.customers.lotte.grants[0].status).toBe('revoked');
});

test('preferences persist per customer and local state can reset', async ({ page }) => {
  await page.goto('/');
  await page.locator('aside.panel').getByRole('button', { name: 'Lotte', exact: true }).click();
  await page.getByRole('button', { name: 'Profile', exact: true }).click();
  await page.getByRole('button', { name: /Settings & appearance/ }).click();
  await page.getByRole('radio', { name: 'Dark', exact: true }).click();
  await expect(page.locator('.phone.dark')).toBeVisible();
  await page.reload();
  await expect(page.locator('.phone.dark')).toBeVisible();
  await page.locator('aside.panel').getByRole('button', { name: 'Jan', exact: true }).click();
  await expect(page.locator('.phone.dark')).toHaveCount(0);
  await expect(page.locator('.phone h1')).toContainText('Jan');
  await page.getByRole('button', { name: 'Reset demo', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
});

test('resetting a pending journey cancels its local completion', async ({ page }) => {
  await page.goto('/');
  await page.locator('aside.panel').getByRole('button', { name: 'Lotte', exact: true }).click();
  await page.getByRole('button', { name: 'Goals', exact: true }).click();
  await page.locator('.gs-option.suggested').first().click();
  await page.getByRole('button', { name: 'Approve & start', exact: true }).click();
  const invoicing = page.locator('.eco-step').filter({ hasText: 'Invoice the right way: Peppol' });
  await invoicing.getByRole('button', { name: /approve/i }).click();
  await page.getByRole('button', { name: 'Approve & share with Billit' }).click();
  await page.locator('aside.panel').getByRole('button', { name: 'Reset goals', exact: true }).click();
  await expect(page.locator('.gs-option.suggested').first()).toBeVisible();
  await page.reload();
  const state = await page.evaluate(() => JSON.parse(localStorage.getItem('kbc-demo-v1')!));
  expect(state.customers.lotte.goals).toEqual([]);
  expect(state.customers.lotte.pending).toEqual({});
});

test('home previews the complete roadmap without creating a goal until approval', async ({ page }) => {
  await page.goto('/');
  await page.locator('aside.panel').getByRole('button', { name: 'Lotte', exact: true }).click();
  const balance = await page.locator('.account-entry').boundingBox();
  const feed = await page.locator('.feed-head').boundingBox();
  expect(balance!.y).toBeLessThan(feed!.y);
  await expect(page.locator('.goals-tile')).toHaveCount(0);
  await expect(page.locator('[data-card-key="core:money"] .tile-main-value')).toHaveText('€5.500');
  await expect(page.locator('[data-card-key="core:coming_up"] .tile-description')).toContainText('01 Nov');
  await expect(page.locator('.recommendation-grid > .tile-wide').first()).toBeVisible();
  await expect(page.locator('.recommendation-grid > .recommendation-cell:not(.tile-wide)').first()).toBeVisible();
  await page.screenshot({ path: 'test-results/for-you-tiles.png', animations: 'disabled' });
  await page.getByRole('button', { name: 'Goals', exact: true }).click();
  const noticed = page.locator('.gs-option.suggested');
  await expect(noticed.first()).toContainText('10 steps');
  await page.screenshot({ path: 'test-results/goals-screen.png', animations: 'disabled' });
  const seeRoadmap = () => noticed.first().click();
  await seeRoadmap();
  await expect(page.getByRole('heading', { name: 'Your roadmap' })).toBeVisible();
  await expect(page.locator('.roadmap-steps li')).toHaveCount(10);
  const before = await page.evaluate(() => JSON.parse(localStorage.getItem('kbc-demo-v1')!));
  expect(before.customers.lotte.goals).toEqual([]);
  expect(before.customers.lotte.grants).toEqual([]);
  await expect(page.locator('.roadmap-sheet')).toHaveCSS('transform', 'none');
  await page.screenshot({ path: 'test-results/home-roadmap.png', animations: 'disabled' });
  await page.keyboard.press('Escape');
  await expect(page.getByRole('heading', { name: 'Your roadmap' })).toHaveCount(0);
  await seeRoadmap();
  await page.getByRole('button', { name: 'Approve & start', exact: true }).click();
  await expect(page.locator('.eco-step').first()).toBeVisible();
  await page.reload();
  await page.getByRole('button', { name: 'Goals', exact: true }).click();
  await expect(page.locator('.gs-goal')).toHaveCount(1);
  const after = await page.evaluate(() => JSON.parse(localStorage.getItem('kbc-demo-v1')!));
  expect(after.customers.lotte.goals).toHaveLength(1);
  expect(after.customers.lotte.grants).toEqual([]);
});

test('account, recommendations, notifications and profile controls open from the new home', async ({ page }) => {
  await page.goto('/');
  await page.locator('aside.panel').getByRole('button', { name: 'Sara', exact: true }).click();
  await page.getByRole('button', { name: 'Show all accounts' }).click();
  await expect(page.getByRole('button', { name: 'Back to home' })).toBeVisible();
  await page.getByRole('button', { name: 'Back to home' }).click();
  await page.locator('.recommendation-tile').first().click();
  await expect(page.locator('.feed-detail')).toBeVisible();
  await page.getByRole('button', { name: 'Close', exact: true }).click();
  await page.getByRole('button', { name: /Kate inbox/ }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: 'Close', exact: true }).click();
  await page.getByRole('button', { name: 'Profile', exact: true }).click();
  await page.getByRole('button', { name: /Permissions & data/ }).click();
  await expect(page.getByRole('heading', { name: /Consent passport/ })).toBeVisible();
  await page.getByRole('button', { name: 'Close', exact: true }).click();
  await page.getByRole('button', { name: 'Profile', exact: true }).click();
  await page.getByRole('button', { name: /Settings & appearance/ }).click();
  await page.getByRole('switch', { name: 'Hide amounts', exact: true }).click();
  await page.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(page.locator('.account-balance')).toContainText('••••');
  await page.getByRole('button', { name: 'Profile', exact: true }).click();
  await page.getByRole('button', { name: /Edit home/ }).click();
  await expect(page.getByText('Editing your home')).toBeVisible();
});

async function dragTile(page: Page, from: Locator, to: Locator) {
  await from.scrollIntoViewIfNeeded();
  const a = (await from.boundingBox())!;
  const b = (await to.boundingBox())!;
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
  await page.mouse.down();
  await page.mouse.move(a.x + a.width / 2 + 12, a.y + a.height / 2 + 12, { steps: 3 });
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 10 });
  await page.mouse.up();
}

test('one editable grid mixes personal tiles and recommendations and preserves placements per customer', async ({ page }) => {
  await page.goto('/');
  await page.locator('aside.panel').getByRole('button', { name: 'Lotte', exact: true }).click();
  await expect(page.locator('.home-tile-grid')).toHaveCount(1);
  await expect(page.locator('.phone-scroll > .sections')).toHaveCount(0);
  await expect(page.getByText('View accounts', { exact: true })).toHaveCount(0);
  await expect(page.locator('.grid-free, .grid-state, .grid-remove')).toHaveCount(0);
  await page.getByRole('button', { name: 'Edit tiles', exact: true }).click();
  const money = page.locator('[data-tile-id="card:core:money"]');
  await expect(money.locator('.grid-remove')).toHaveCount(1);
  await expect(page.getByRole('button', { name: /^(Move|Make wide|Make compact|Keep) / })).toHaveCount(0);
  await dragTile(page, money, page.locator('.home-tile-grid > [data-slot="1"]'));
  await expect(money).toHaveAttribute('data-slot', '1');
  await expect(money).toHaveClass(/user-pinned/);
  await page.getByRole('button', { name: 'Remove Your money', exact: true }).click();
  await expect(money).toHaveCount(0);
  await page.getByRole('button', { name: '+ Add row', exact: true }).click();
  await page.getByRole('button', { name: 'Fill free spot 13', exact: true }).click();
  await page.getByRole('button', { name: 'Place Your money', exact: true }).click();
  await expect(money).toHaveAttribute('data-slot', '12');
  await page.getByRole('button', { name: 'Done editing', exact: true }).click();
  await expect(page.locator('.grid-free')).toHaveCount(0);
  await page.reload();
  await expect(money).toHaveAttribute('data-slot', '12');
  await page.locator('aside.panel').getByRole('button', { name: 'Jan', exact: true }).click();
  await expect(page.locator('.user-pinned')).toHaveCount(0);
  await page.locator('aside.panel').getByRole('button', { name: 'Lotte', exact: true }).click();
  await expect(money).toHaveAttribute('data-slot', '12');
  await page.getByRole('button', { name: 'Edit tiles', exact: true }).click();
  await page.getByRole('button', { name: 'Reset to adaptive', exact: true }).click();
  await expect(page.locator('.user-pinned')).toHaveCount(0);
  await expect(money).toHaveAttribute('data-slot', '0');
});

test('removed recommendations stay removed and can be placed again in a free spot', async ({ page }) => {
  await page.goto('/');
  await page.locator('aside.panel').getByRole('button', { name: 'Lotte', exact: true }).click();
  await page.getByRole('button', { name: 'Edit tiles', exact: true }).click();
  await page.getByRole('button', { name: 'Remove Your money', exact: true }).click();
  await expect(page.locator('[data-tile-id="card:core:money"]')).toHaveCount(0);
  await expect(page.locator('.home-tile-grid > [data-slot="0"] .recommendation-tile')).toBeVisible();
  await page.reload();
  await expect(page.locator('[data-tile-id="card:core:money"]')).toHaveCount(0);
  await page.getByRole('button', { name: 'Edit tiles', exact: true }).click();
  await page.getByRole('button', { name: '+ Add row', exact: true }).click();
  await page.getByRole('button', { name: 'Fill free spot 13', exact: true }).click();
  await page.getByRole('button', { name: 'Place Your money', exact: true }).click();
  await expect(page.locator('[data-tile-id="card:core:money"]')).toHaveAttribute('data-slot', '12');
  const state = await page.evaluate(() => JSON.parse(localStorage.getItem('kbc-demo-v1')!));
  expect(state.customers.lotte.tileGrid.slotCount).toBe(14);
  await page.locator('.phone-scroll:not([hidden])').evaluate((el) => { el.scrollTop = 0; });
  await page.screenshot({ path: 'test-results/editable-grid.png', animations: 'disabled' });
  await page.getByRole('button', { name: 'Done editing', exact: true }).click();
});
