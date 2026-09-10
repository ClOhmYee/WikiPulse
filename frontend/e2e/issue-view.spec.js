import { test, expect } from '@playwright/test';
import { events } from '../src/data/mock/fixtures/catalog.js';

test('issue presentation preserves query, sorting and saved state', async ({ page }) => {
  await page.goto('/#/issues');
  await page.getByRole('textbox', { name: '사건 검색', exact: true }).fill('호르무즈');
  await page.getByRole('combobox', { name: '사건 정렬' }).selectOption('recent');
  await expect(page.locator('.event-row')).toHaveCount(events.filter(e => e.title.includes('호르무즈')).length);
  const row = page.locator('.event-row').first();
  await row.getByRole('button', { name: /저장/ }).click();
  await page.getByRole('button', { name: '카드', exact: true }).click();
  await expect(page.locator('.event-list')).toHaveAttribute('data-view', 'card');
  await expect(row.getByRole('button', { name: /저장 해제/ })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: '리스트', exact: true }).click();
  await expect(page.locator('.event-list')).toHaveAttribute('data-view', 'list');
  await expect(page.getByRole('textbox', { name: '사건 검색', exact: true })).toHaveValue('호르무즈');
  await expect(page.getByRole('combobox', { name: '사건 정렬' })).toHaveValue('recent');
  await page.goto('/#/pulse');
  await expect(page.getByRole('heading', { name: '세상의 변화가 모이는 곳' })).toBeVisible();
  await expect(page.locator('[aria-label="탐색 보기"]')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '카드', exact: true })).toHaveCount(0);
});
