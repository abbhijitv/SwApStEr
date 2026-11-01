import {test, expect} from '@playwright/test';
import {selectProfile} from './profile-helpers';

test('general categories, optional course code, sale listing, search and price sorting', async ({page}) => {
  await page.goto('/marketplace');
  await selectProfile(page, 'Shorya Moses');
  for (const category of ['Electronics', 'Furniture', 'Clothing', 'Home & Living', 'Books', 'Sports', 'Other', 'Calculators', 'Textbooks', 'Lab kits', 'Drafting', 'Housing & Subleases']) {
    await expect(page.getByRole('group', {name: 'Filter by category'}).getByRole('button', {name: category, exact: true})).toBeVisible();
  }
  const title = `Reading chair ${Date.now()}`;
  await page.getByRole('button', {name: 'List an item', exact: true}).click();
  await page.getByLabel('Item name', {exact: true}).fill(title);
  await page.getByLabel('Description', {exact: true}).fill('Comfortable upholstered chair with removable cushion.');
  await page.getByRole('combobox', {name: 'Category', exact: true}).selectOption('Furniture');
  await expect(page.getByLabel('Course code (optional, for academic items)', {exact: true})).toHaveValue('');
  await page.getByRole('combobox', {name: 'Listing type', exact: true}).selectOption('Buy');
  await page.getByLabel('Asking price ($)', {exact: true}).fill('45.50');
  await page.getByLabel('Private minimum ($)', {exact: true}).fill('30');
  await page.getByRole('button', {name: 'Publish listing', exact: true}).click();
  await expect(page.getByRole('button', {name: title, exact: true})).toBeVisible();
  await expect(page.locator('.item-card').filter({hasText: title}).locator('.price')).toHaveText('$45.50');
  await page.reload();
  await selectProfile(page, 'Abbhijit');
  await page.getByRole('button', {name: 'Furniture', exact: true}).click();
  await expect(page.getByRole('button', {name: title, exact: true})).toBeVisible();
  await page.getByRole('textbox', {name: 'Search marketplace'}).fill('upholstered');
  await expect(page.getByRole('button', {name: title, exact: true})).toBeVisible();
  await page.getByRole('button', {name: title, exact: true}).click();
  await expect(page.getByRole('dialog')).toContainText('$45.50');
  await page.getByRole('button', {name: 'Let My AI Negotiate'}).click();
  await expect(page.getByLabel('Rental duration (days)', {exact: true})).toHaveCount(0);
  await expect(page.getByLabel('Preferred completion deadline', {exact: true})).toBeVisible();
  await expect(page.getByLabel('Preferred pickup location', {exact: true})).toHaveValue('');
  await page.getByRole('button', {name: 'Close dialog'}).click();
  await page.getByRole('textbox', {name: 'Search marketplace'}).fill('no-such-item-xyz');
  await page.getByRole('button', {name: 'Clear filters', exact: true}).click();
  await page.getByLabel('Sort listings', {exact: true}).selectOption('price');
  const prices = await page.locator('.item-card .price').allTextContents();
  const amounts = prices.map(price => Number(price.match(/\$([\d.]+)/)![1]));
  expect(amounts).toEqual([...amounts].sort((a, b) => a - b));
});

test('backend-defined categories remain discoverable and platform routes stay available', async ({page}) => {
  await page.route('**/listings', async route => {
    const response = await route.fetch();
    const items = await response.json();
    // Simulates a future backend category without changing persisted data.
    await route.fulfill({json: items.map((item: {id: number; category: string}, index: number) => index === 0 ? {...item, category: 'Musical instruments'} : item)});
  });
  await page.goto('/marketplace');
  await expect(page.getByRole('button', {name: 'Musical instruments', exact: true})).toBeVisible();
  await page.getByRole('button', {name: 'Musical instruments', exact: true}).click();
  await expect(page.locator('.item-card')).toHaveCount(1);
  await page.getByRole('link', {name: 'Platform home'}).click();
  await expect(page).toHaveURL('http://localhost:3000/');
  await page.getByRole('link').filter({hasText: 'B2B Procurement'}).click();
  await expect(page.getByRole('heading', {name: 'SwApStEr Business'})).toBeVisible();
});
