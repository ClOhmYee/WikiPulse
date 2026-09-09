import { chromium } from '@playwright/test';
import { strict as assert } from 'node:assert';
import { events, stocks } from '../src/data/mock/fixtures/catalog.js';
import { writeFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
const requests = [];
const errors = [];
page.on('request', request => requests.push(request.url()));
page.on('pageerror', error => errors.push(error.message));
page.on('response', response => { if (response.status() >= 400) errors.push(`${response.status()} ${response.url()}`); });
const response = await page.goto('http://127.0.0.1:4174/#/pulse');
await page.getByRole('heading', { name: '세상의 변화가 모이는 곳' }).waitFor();
await page.evaluate(() => document.fonts.ready);
assert.equal(response.status(), 200);
const directEntry = requests.filter(url => /\.js(?:\?|$)/.test(url));
assert(!directEntry.some(url => /\/OnboardingPage-[^/]+\.js/.test(url)), 'The workspace must not load the onboarding WebGL chunk on direct entry.');
const routes = [
  ['/issues', '사건을 탐색하세요'],
  [`/issues/${events[0].id}`, events[0].title],
  ['/stocks', '종목에서 사건의 맥락을 찾으세요.'],
  [`/stocks/${stocks[0].symbol}`, stocks[0].name],
  ['/saved', '관심의 흐름을 이어가세요'],
];
for (const [path, title] of routes) {
  await page.goto(`http://127.0.0.1:4174/#${path}`);
  await page.getByRole('heading', { name: title, exact: true }).waitFor();
  assert.equal(await page.getByRole('main').count(), 1, path);
}
assert(!requests.some(url => /\/api\//.test(url)), 'Mock app should not issue data API requests.');
await page.goto('http://127.0.0.1:4174/');
await page.getByRole('link', { name: '탐색 시작하기' }).waitFor();
await page.getByRole('link', { name: '탐색 시작하기' }).click();
await page.getByRole('heading', { name: '세상의 변화가 모이는 곳' }).waitFor();
assert.deepEqual(errors, []);
const result = { routes: routes.length + 2, directEntryScripts: directEntry.map(url => url.split('/').at(-1)), noDataApiRequests: true, onboardingExit: true, errors };
const output = fileURLToPath(new URL('../test-results/production-smoke.json', import.meta.url));
await mkdir(fileURLToPath(new URL('../test-results/', import.meta.url)), { recursive: true });
await writeFile(output, JSON.stringify(result, null, 2));
console.log(JSON.stringify(result, null, 2));
await browser.close();
