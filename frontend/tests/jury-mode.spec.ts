import { devices, expect, test } from '@playwright/test';

// Jury mode (?jury=1): what a judge sees on their own phone after scanning the QR code.
const { defaultBrowserType: _browser, ...iPhone } = devices['iPhone 13'];
test.use({ ...iPhone });

test.beforeEach(async ({ page }) => {
  await page.route('**/api/**', (route) => { throw new Error(`Unexpected backend request: ${route.request().url()}`); });
});

test('a judge picks a person and the guide follows the full loop', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto('/?jury=1');
  await expect(page.locator('.panel')).toHaveCount(0);
  await page.getByRole('button', { name: /Juliette, 26/ }).click();
  await expect(page.locator('.phone h1')).toContainText('Juliette');
  const guide = page.getByRole('dialog', { name: 'Demo guide' });
  await expect(guide).toContainText('Start as a freelancer');
  await page.getByRole('button', { name: "Let's go" }).click();
  await expect(page.getByRole('button', { name: 'Demo guide · 0/3' })).toBeVisible();

  await page.getByRole('button', { name: 'Goals', exact: true }).click();
  await page.locator('.gs-option.suggested').first().click();
  await page.getByRole('button', { name: 'Approve & start', exact: true }).click();
  await expect(guide.locator('li.done')).toHaveCount(1);
  await page.getByRole('button', { name: 'Hide guide' }).click();

  await page.locator('.eco-step').filter({ hasText: 'Peppol' }).getByRole('button', { name: /approve/ }).click();
  await page.getByRole('button', { name: /Approve & share/ }).click();
  await expect(guide.locator('li.done')).toHaveCount(2);
  await page.getByRole('button', { name: 'Hide guide' }).click();

  await page.locator('.sheet.full').getByRole('button', { name: /close/i }).first().click();
  await page.getByRole('button', { name: 'Kate', exact: true }).click();
  await page.getByRole('button', { name: 'Make the text bigger' }).first().click();
  await page.getByRole('button', { name: 'Use large text' }).click();
  await expect(guide).toContainText("That's the full loop");
  await expect(page.locator('.phone')).toContainText('Juliette');
  await expect(page.locator('body')).not.toContainText('Lotte');

  // Another person keeps Juliette's progress; restart wipes it.
  await guide.getByRole('button', { name: 'Another person' }).click();
  await page.getByRole('button', { name: /Juliette, 26/ }).click();
  await expect(guide).toContainText("That's the full loop");
  await guide.getByRole('button', { name: 'Restart' }).click();
  await page.getByRole('button', { name: /Juliette, 26/ }).click();
  await expect(guide.locator('li.done')).toHaveCount(0);
  expect(errors).toEqual([]);
});
