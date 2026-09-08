import { chromium } from '@playwright/test';
import { createRequire } from 'node:module';
import { writeFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const axePath = require.resolve('axe-core/axe.min.js');
const browser = await chromium.launch({ headless: true });
const results = [];
const routes = ['/pulse', '/explore', '/events/iran-hormuz-2025', '/intelligence/strait-of-hormuz', '/stocks', '/stocks/NVDA', '/saved'];
for (const width of [1440, 820, 390, 320]) {
  const context = await browser.newContext({ viewport: { width, height: 900 }, reducedMotion: 'reduce' });
  const page = await context.newPage();
  for (const route of routes) {
    await page.goto(`http://127.0.0.1:5174/#${route}`);
    await page.locator('h1').waitFor();
    await page.evaluate(() => document.fonts.ready);
    await page.addScriptTag({ path: axePath });
    const states = route.startsWith('/events/') ? ['overview', 'discussion-expanded'] : ['default'];
    for (const state of states) {
    if (state === 'discussion-expanded') {
      await page.getByRole('tab', { name: '토론', exact: true }).click();
      await page.locator('.dc-thread').first().getByRole('button', { name: /답글/ }).click();
    }
    const result = await page.evaluate(async () => {
      const report = await window.axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] } });
      return { violations: report.violations.map(item => ({ id: item.id, impact: item.impact, description: item.description, nodes: item.nodes.map(node => ({ selector: node.target, message: node.failureSummary })) })), incomplete: report.incomplete.map(item => item.id) };
    });
    results.push({ width, route, state, ...result });
    }
  }
  await context.close();
}
await browser.close();
const output = fileURLToPath(new URL('../test-results/accessibility.json', import.meta.url));
await mkdir(fileURLToPath(new URL('../test-results/', import.meta.url)), { recursive: true });
await writeFile(output, JSON.stringify(results, null, 2));
const failing = results.filter(item => item.violations.length);
console.log(JSON.stringify({ pages: results.length, failingPages: failing.length, results: failing }, null, 2));
if (failing.length) process.exitCode = 1;
