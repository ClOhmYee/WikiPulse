import { chromium } from '@playwright/test';
import { fileURLToPath } from 'node:url';

const output = fileURLToPath(new URL('../../.impeccable/review/', import.meta.url));
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
await page.goto('http://127.0.0.1:5174/#/pulse');
await page.locator('.document-map').waitFor();
await page.evaluate(() => document.fonts.ready);
await page.screenshot({ path: `${output}/workspace-pulse-mobile.png`, fullPage: true });
await page.locator('.document-map').screenshot({ path: `${output}/workspace-map-mobile-fix.png` });
const mobile = await page.evaluate(() => {
  const controls = document.querySelector('.document-map__controls').getBoundingClientRect();
  const labels = [...document.querySelectorAll('.document-cluster__title')].map(element => {
    const bounds = element.getBoundingClientRect();
    return { text: element.textContent, bottom: bounds.bottom, overlaps: bounds.bottom > controls.top && bounds.top < controls.bottom && bounds.right > controls.left && bounds.left < controls.right };
  });
  return { controlsTop: controls.top, labels, documentWidth: document.documentElement.scrollWidth };
});
await page.setViewportSize({ width: 820, height: 1000 });
await page.screenshot({ path: `${output}/workspace-tablet-fix.png`, fullPage: true });
const tablet = await page.locator('.workspace-nav a').evaluateAll(elements => elements.map(element => ({ name: element.getAttribute('aria-label'), title: element.getAttribute('title') })));
console.log(JSON.stringify({ mobile, tablet }, null, 2));
await browser.close();
if (mobile.labels.some(label => label.overlaps) || tablet.some(link => !link.name || !link.title)) process.exitCode = 1;
