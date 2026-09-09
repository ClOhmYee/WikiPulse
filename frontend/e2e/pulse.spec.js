import { test, expect } from '@playwright/test';
import { pulseMaps } from '../src/data/mock/fixtures/pulse.js';

test('document graph, history, selection loss, missing data and keyboard navigation', async ({ page }) => {
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto('/#/pulse');
  const latest = pulseMaps.at(-1);
  const map = page.getByRole('region', { name: '사건 관계 지도' });
  await expect(map.locator('.document-node')).toHaveCount(latest.meta.nodeCount);
  await expect(map.locator('[data-edge-id]')).toHaveCount(latest.meta.edgeCount);
  const radii = await map.locator('.document-node__body').evaluateAll(nodes => nodes.map(v => v.getAttribute('r')));
  expect(new Set(radii).size).toBeGreaterThan(2);
  await expect(page.locator('.pulse-cluster-list')).toContainText('HOT');
  await expect(page.locator('.pulse-cluster-list')).toContainText('NEW');
  await page.locator('.pulse-cluster-list button').filter({ hasText: '클라우드 보안' }).click();
  const panel = page.getByRole('complementary', { name: '선택한 사건' });
  await panel.getByRole('button', { name: 'Cloud computing 연관 문서' }).click();
  await expect(panel.getByRole('region', { name: '선택한 문서' })).toContainText('집계 중');
  await expect(panel).toContainText('Wikidata');
  await page.getByRole('button', { name: '이전 시점' }).click();
  await expect(map).toHaveAttribute('data-snapshot', '2025-06-23T15:00:00Z');
  await expect(page.locator('.pulse-notice')).toContainText('선택한 이슈가 이 시점에 없어');
  await expect(panel.getByRole('heading', { name: '이슈의 맥락을 따라가세요' })).toBeVisible();
  await page.getByRole('combobox', { name: '스냅샷 날짜' }).selectOption('2025-06-22');
  await expect(map).toHaveAttribute('data-snapshot', '2025-06-22T05:00:00Z');
  const slider = page.getByRole('slider', { name: '스냅샷 시각' });
  await slider.focus(); await page.keyboard.press('ArrowLeft');
  await expect(map).toHaveAttribute('data-snapshot', '2025-06-22T00:00:00Z');
  await page.keyboard.press('End');
  await expect(map).toHaveAttribute('data-snapshot', '2025-06-22T05:00:00Z');
  await expect(page.locator('option[value="2025-06-21"]')).toHaveJSProperty('disabled', true);
  await page.getByRole('combobox', { name: '스냅샷 날짜' }).selectOption('2025-06-20');
  await expect(page.getByRole('heading', { name: '이 시점에 포착된 이슈가 없습니다' })).toBeVisible();
  await page.getByRole('button', { name: '최신으로 이동' }).click();
  await expect(map).toHaveAttribute('data-snapshot', latest.meta.snapshotTs);
  const first = map.locator('.document-node').first();
  await first.focus(); await page.keyboard.press('Enter');
  await expect(first).toHaveAttribute('aria-pressed', 'true');
  expect(errors).toEqual([]);
});

test('desktop and mobile visual handoff and filter stability', async ({ page }) => {
  await page.goto('/#/pulse');
  const map = page.getByRole('region', { name: '사건 관계 지도' });
  await expect(map.locator('.document-node')).toHaveCount(14);
  const node = map.locator('[data-page-id="semiconductor"]');
  const radius = await node.locator('.document-node__body').getAttribute('r');
  const position = await node.getAttribute('transform');
  await page.getByRole('button', { name: '기술', exact: true }).click();
  await expect(node).toHaveAttribute('transform', position);
  await expect(node.locator('.document-node__body')).toHaveAttribute('r', radius);
  await page.getByRole('button', { name: '전체', exact: true }).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'test-results/pulse-desktop.png', fullPage: true });
  await page.locator('.pulse-cluster-list button').first().click();
  await page.getByRole('complementary', { name: '선택한 사건' }).locator('.pulse-document').first().click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'test-results/pulse-desktop-selected.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: '지도 위치 초기화' }).click();
  const labels = await map.locator('.document-cluster__title').evaluateAll(elements => elements.map(element => {
    const { left, right, top, bottom } = element.getBoundingClientRect();
    return { left, right, top, bottom };
  }));
  for (let i = 0; i < labels.length; i++) for (let j = i + 1; j < labels.length; j++) {
    const a = labels[i], b = labels[j];
    expect(a.right > b.left && a.left < b.right && a.bottom > b.top && a.top < b.bottom).toBe(false);
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'test-results/pulse-mobile.png', fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  const panel = await page.locator('.pulse-preview').boundingBox();
  const graph = await map.boundingBox();
  expect(panel.y).toBeGreaterThanOrEqual(graph.y + graph.height - 1);
});
