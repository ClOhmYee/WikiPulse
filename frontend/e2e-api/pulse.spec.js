import { test, expect } from '@playwright/test';
import { pulseMaps, pulseSnapshots, makeStressMap } from '../src/data/mock/fixtures/pulse.js';
import { kstTimestamp } from '../src/data/pulse/time.js';

async function serve(page, override) {
  const calls = [];
  await page.route('**/api/v1/issues/**', async route => {
    const url = new URL(route.request().url()); calls.push(url);
    if (override && await override(route, url)) return;
    if (url.pathname.endsWith('/snapshots')) return route.fulfill({ json: pulseSnapshots });
    const map = pulseMaps.find(v => v.meta.snapshotTs === url.searchParams.get('snapshotTs')) || pulseMaps.at(-1);
    const body = structuredClone(map); body.meta.dataMode = 'unverified';
    await route.fulfill({ json: body });
  });
  return calls;
}
test('pulse uses the graph contract without downloading catalogue fixtures', async ({ page }) => {
  const scripts = []; page.on('request', request => { if (request.resourceType() === 'script') scripts.push(request.url()); });
  const calls = await serve(page);
  await page.goto('/#/pulse');
  await expect(page.locator('.document-node')).toHaveCount(14);
  await expect(page.getByRole('button', { name: '출처 확인 필요' })).toBeVisible();
  expect(calls.map(v => v.pathname)).toEqual(['/api/v1/issues/snapshots', '/api/v1/issues/map']);
  expect(scripts.some(v => /data\/mock|fixtures\//.test(v))).toBe(false);
});
test('rapid time changes discard a slower response and preserve graph/panel timestamp', async ({ page }) => {
  let slowStarted; const started = new Promise(resolve => { slowStarted = resolve; });
  let release; const gate = new Promise(resolve => { release = resolve; });
  let finished; const served = new Promise(resolve => { finished = resolve; });
  await serve(page, async (route, url) => {
    if (!url.pathname.endsWith('/map') || url.searchParams.get('snapshotTs') !== '2025-06-23T15:00:00Z') return false;
    slowStarted(); await gate;
    await route.fulfill({ json: pulseMaps[5] }).catch(() => {}); finished(); return true;
  });
  await page.goto('/#/pulse');
  await expect(page.locator('.document-node')).toHaveCount(14);
  await page.locator('.pulse-cluster-list button').first().click();
  await page.getByRole('button', { name: '이전 시점' }).click(); await started;
  await expect(page.locator('.pulse-loading')).toBeVisible();
  await page.getByRole('button', { name: '최신으로 이동' }).click();
  await expect(page.locator('.document-map')).toHaveAttribute('data-snapshot', pulseMaps.at(-1).meta.snapshotTs);
  release(); await served;
  await expect(page.locator('.pulse-preview')).toHaveAttribute('data-snapshot', pulseMaps.at(-1).meta.snapshotTs);
  await expect(page.locator('.pulse-timeline')).toContainText(kstTimestamp(pulseMaps.at(-1).meta.snapshotTs));
});
test('API error retries and mismatched or invalid graph data never masquerade as mock', async ({ page }) => {
  let state = 'error';
  await serve(page, async (route, url) => {
    if (!url.pathname.endsWith('/map')) return false;
    if (state === 'error') { await route.fulfill({ status: 503, json: { error: { code: 'UNAVAILABLE' } } }); return true; }
    if (state === 'invalid') { const body = structuredClone(pulseMaps.at(-1)); body.data.clusters[0].edges[0].targetPageId = 'missing'; await route.fulfill({ json: body }); return true; }
    return false;
  });
  await page.goto('/#/pulse');
  await expect(page.getByRole('heading', { name: '이 시점의 지도를 불러오지 못했습니다' })).toBeVisible();
  await expect(page.locator('.document-map')).toHaveCount(0);
  state = 'invalid'; await page.getByRole('button', { name: '지도 다시 불러오기' }).click();
  await expect(page.getByRole('alert')).toContainText('edge endpoints');
  state = 'ok'; await page.getByRole('button', { name: '지도 다시 불러오기' }).click();
  await expect(page.locator('.document-node')).toHaveCount(14);
});
test('500 nodes and 1000 edges remain interactive in the browser', async ({ page }) => {
  const stress = makeStressMap();
  await serve(page, async (route, url) => {
    if (!url.pathname.endsWith('/map')) return false;
    await route.fulfill({ json: stress }); return true;
  });
  await page.goto('/#/pulse');
  await expect(page.locator('.document-node')).toHaveCount(500);
  await expect(page.locator('[data-edge-id]')).toHaveCount(1000);
  const started = Date.now();
  await page.locator('.pulse-cluster-list button').nth(10).click();
  await page.locator('.pulse-preview .pulse-document').nth(10).click();
  await expect(page.locator('.document-node[data-selected="true"]')).toHaveCount(1);
  await page.getByRole('button', { name: '지도 확대', exact: true }).click();
  expect(Date.now() - started).toBeLessThan(3000);
  await expect(page.locator('.pulse-preview')).toContainText('검증 문서 11-11');
});
