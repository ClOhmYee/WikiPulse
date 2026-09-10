import test from 'node:test';
import assert from 'node:assert/strict';
import sources from '../src/data/mock/fixtures/sources.json' with { type: 'json' };
import { dates, documents, episodes, timestamp, snapshotAt, resolveReport, universe, DEMO_DATE } from '../src/data/mock/fixtures/history.js';
import { events, stocks } from '../src/data/mock/fixtures/catalog.js';
import { mockClient } from '../src/data/mock/client.js';
import { loadPageData } from '../src/data/resources.js';
import { validateMap } from '../src/data/pulse/contract.js';

test('verified real Wikipedia identities, fixed Nasdaq-100 universe and a continuous daily archive', () => {
  assert.equal(dates[0], '2025-09-01'); assert.equal(dates.at(-1), '2026-09-10');
  assert.equal(dates.length, 375); assert(documents.length >= 270); assert(episodes.length >= 450);
  assert.equal(new Set(stocks.map(s => s.symbol)).size, universe.stocks.length);
  assert.deepEqual(stocks.map(s => s.symbol).sort(), sources.universe.stocks.map(s => s.symbol).sort());
  assert(stocks.every(s => s.market === 'NASDAQ' && s.currency === 'USD'));
  assert(stocks.every(s => s.eventIds.length > 0), 'every constituent is reachable from a report');
  for (const doc of documents) {
    assert(doc.source.pageId > 0 && doc.source.firstRevisionId > 0);
    assert(doc.source.firstRevisionAt <= timestamp(DEMO_DATE));
    assert(doc.source.url.startsWith('https://en.wikipedia.org/wiki/'));
  }
});

test('every daily cluster has a matching report, sums, article identities and valid Nasdaq links', () => {
  let clusterCount = 0;
  for (const date of dates) {
    const map = validateMap(snapshotAt(date));
    assert(map.data.clusters.length > 0, date);
    const seen = new Map();
    for (const cluster of map.data.clusters) {
      clusterCount++;
      const report = resolveReport(cluster.id);
      assert(report, cluster.id); assert.equal(report.date, date);
      assert.deepEqual(report.articleIds, cluster.nodes.map(n => n.pageId));
      assert.equal(report.edits, cluster.nodes.reduce((s, n) => s + n.editCount, 0));
      assert.equal(report.baseline, cluster.nodes.reduce((s, n) => s + n.editBaseline, 0));
      assert.equal(report.pulse, cluster.pulseScore);
      for (const metric of ['edits', 'baseline', 'pageviews']) assert.equal(report.chart.at(-1)[metric], report[metric]);
      assert(report.timeline.every(t => t.time <= map.meta.snapshotTs));
      assert(report.chart.every(p => p.date <= date && p.date >= dates[0]));
      assert(report.stockSymbols.length > 0);
      for (const symbol of report.stockSymbols) assert(stocks.some(s => s.symbol === symbol));
      for (const node of cluster.nodes) {
        if (seen.has(node.pageId)) assert.deepEqual(node, seen.get(node.pageId));
        seen.set(node.pageId, node);
        assert(documents.find(d => d.id === node.pageId).source.firstRevisionAt <= map.meta.snapshotTs);
      }
    }
  }
  assert(clusterCount > 9000);
  console.log(`${documents.length} Wikipedia documents / ${events.length} reports / ${clusterCount} daily cluster reports / ${stocks.length} Nasdaq-100 securities`);
});

test('historical map -> report -> stocks keeps the selected date and reverse relation', async () => {
  for (const date of ['2025-09-01', '2025-12-15', '2026-02-10', '2026-06-10', DEMO_DATE]) {
    const cluster = snapshotAt(date).data.clusters[0];
    const response = await mockClient.getEvent(cluster.id);
    assert.equal(response.meta.asOf, date);
    assert.deepEqual(response.data.articleIds, response.included.entities.map(e => e.id));
    assert.equal(response.data.edits, response.included.entities.reduce((s, e) => s + e.edits, 0));
    const detail = await loadPageData(mockClient, 'eventStocks', { id: cluster.id }, {});
    assert(detail.stocks.length > 0);
    for (const stock of detail.stocks) {
      assert(stock.eventIds.includes(cluster.id));
      assert(stock.relations.some(r => r.eventId === cluster.id));
      if (date < DEMO_DATE) assert.equal(stock.price, null);
    }
    const saved = await loadPageData(mockClient, 'saved', { savedEvents: [cluster.id], savedStocks: [] }, {});
    assert.equal(saved.events[0].date, date);
  }
  assert.equal(resolveReport('ai-chip-controls~2027-01-01'), null);
  await assert.rejects(mockClient.getEvent('ai-chip-controls~2025-09-01'), { status: 404 });
  await assert.rejects(mockClient.listStocks({ eventId: 'missing' }), { status: 404 });
});
