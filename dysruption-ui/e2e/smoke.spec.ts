import { test, expect } from '@playwright/test';

test('dashboard renders', async ({ page }) => {
  await page.goto('/login');

  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  await expect(page.getByRole('button', { name: /continue with github/i })).toBeVisible();
});
