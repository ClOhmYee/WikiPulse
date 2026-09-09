import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { events, stocks } from '../src/data/mock/fixtures/catalog.js';

const output = fileURLToPath(new URL('../../.impeccable/review/', import.meta.url));
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const captures = [
  ['pulse', '/pulse'],
  ['explore', '/issues'],
  ['event', `/issues/${events[0].id}`],
  ['stocks', '/stocks'],
  ['stock', `/stocks/${stocks[0].symbol}`],
  ['saved', '/saved'],
];
const findings = [];
for (const [device, viewport] of [['desktop', { width: 1440, height: 1000 }], ['mobile', { width: 390, height: 844 }]]) {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1, reducedMotion: 'reduce' });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  for (const [name, route] of captures) {
    await page.goto(`http://127.0.0.1:5174/#${route}`);
    await page.locator('h1').waitFor();
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: `${output}/workspace-${name}-${device}.png`, fullPage: true, animations: 'disabled' });
    const measurements = await page.evaluate(() => ({
      title: document.querySelector('h1')?.textContent,
      documentWidth: document.documentElement.scrollWidth,
      viewport: innerWidth,
      height: document.documentElement.scrollHeight,
      mains: document.querySelectorAll('main').length,
      overflow: [...document.querySelectorAll('main *')].filter(el => {
        const rect = el.getBoundingClientRect();
        return rect.width && (rect.right > innerWidth + 2 || rect.left < -2) && getComputedStyle(el).position !== 'absolute' && !(el instanceof SVGElement);
      }).slice(0, 12).map(el => `${el.tagName}.${String(el.className).slice(0, 90)}`),
    }));
    findings.push({ name, device, ...measurements, errors: [...errors] });
    errors.length = 0;
  }
  await context.close();
}
await browser.close();
await writeFile(`${output}/workspace-measurements.json`, JSON.stringify(findings, null, 2));
console.log(JSON.stringify(findings, null, 2));
