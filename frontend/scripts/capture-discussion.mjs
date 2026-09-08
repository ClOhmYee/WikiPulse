import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const output = fileURLToPath(new URL('../../.impeccable/review/', import.meta.url));
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const results = [];
for (const [device, width] of [['desktop', 1440], ['mobile', 390]]) {
  const context = await browser.newContext({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' });
  const page = await context.newPage();
  await page.goto('http://127.0.0.1:5174/#/events/iran-hormuz-2025');
  await page.getByRole('heading', { level: 1 }).waitFor();
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: `${output}/report-overview-${device}.png`, fullPage: true, animations: 'disabled' });
  await page.getByRole('button', { name: '토론 참여하기' }).click();
  await page.getByLabel('내 의견 작성', { exact: true }).fill('문서의 편집 전후와 연결 근거를 함께 확인해 보고 싶어요.');
  await page.getByRole('button', { name: '토론 등록', exact: true }).click();
  const thread = page.locator('.dc-thread').first();
  await thread.getByRole('button', { name: /답글/ }).click();
  await thread.getByRole('textbox').fill('확인할 문서와 근거를 비교해 보는 답글 예시입니다.');
  await thread.getByRole('button', { name: '답글 등록' }).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `${output}/report-discussion-${device}.png`, fullPage: true, animations: 'disabled' });
  results.push(await page.evaluate(() => ({ width: innerWidth, documentWidth: document.documentElement.scrollWidth, threads: document.querySelectorAll('.dc-thread').length, replyVisible: !!document.querySelector('.dc-replies:not([hidden])') })));
  await context.close();
}
await browser.close();
await writeFile(`${output}/report-discussion-measurements.json`, JSON.stringify(results, null, 2));
console.log(JSON.stringify(results, null, 2));
