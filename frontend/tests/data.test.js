import test from "node:test";
import assert from "node:assert/strict";
import { mockClient } from "../src/data/mock/client.js";
import { events, stocks } from "../src/data/mock/fixtures/catalog.js";
import { readDataConfig } from "../src/data/config.js";
import { describeSource } from "../src/data/contracts.js";
import { createApiClient } from "../src/data/api/client.js";
import { loadPageData } from "../src/data/resources.js";
import { issueId } from "../src/data/mock/identity.js";
import { createDataClient, presentPulseMap } from "../src/data/index.js";

const issue = {
  id: 42,
  label: null,
  pulseScore: 8.4,
  status: "DETECTED",
  source: "replay",
  snapshotTs: "2025-06-12T05:00:00Z",
  members: [
    {
      pageId: 901,
      wiki: "enwiki",
      title: "Strait of Hormuz",
      weight: 1,
      isSeed: true,
      completeness: "pending",
    },
  ],
  relatedStocks: [],
};
const stock = {
  ticker: "NVDA",
  name: "NVIDIA Corporation",
  exchange: "NASDAQ",
};
const report = {
  status: "generating",
  generatedAt: "2025-06-12T05:05:00Z",
  model: "test-model",
  sections: [{ id: "conclusion", title: "결론", body: null, evidenceIds: [] }],
};

test("configuration and source labels do not infer a live service", () => {
  assert.deepEqual(readDataConfig(), { source: "mock", baseURL: "/api/v1" });
  assert.deepEqual(
    readDataConfig({
      VITE_DATA_SOURCE: "api",
      VITE_API_BASE_URL: "https://example.test/v1/",
    }),
    { source: "api", baseURL: "https://example.test/v1" },
  );
  for (const env of [
    { VITE_DATA_SOURCE: "false" },
    { VITE_DATA_SOURCE: "api", VITE_API_BASE_URL: "" },
    { VITE_DATA_SOURCE: "api", VITE_API_BASE_URL: "//external.test" },
  ])
    assert.throws(() => readDataConfig(env), { code: "INVALID_CONFIG" });
  assert.equal(describeSource({ dataMode: "mock" }).label, "데모 데이터");
  assert.equal(describeSource({ dataMode: "api" }).label, "API 데이터");
  assert.equal(describeSource(null).label, "출처 확인 중");
});

test("Spring responses without meta, dataMode or nullable optional fields load normally", async () => {
  const api = createApiClient("/api/v1", async () =>
    Response.json({ data: issue }),
  );
  const response = await api.getIssue(42);
  assert.equal(response.meta, undefined);
  const value = await loadPageData(api, "event", { id: "42" });
  assert.equal(value.events[0].title, "Strait of Hormuz");
  assert.equal(value.events[0].snapshotTs, issue.snapshotTs);
  assert.equal(value.events[0].startAt, null, "a snapshot is not a start date");
  assert.equal(value.entities[0].edits, null, "an omitted metric is not zero");
  assert.equal(value.entities[0].completeness, "pending");
  assert.equal(
    value.events[0].pulse,
    null,
    "pulseScore is not an edit multiplier",
  );
  for (const field of ["chart", "timeline", "news", "keywords", "insights"])
    assert.deepEqual(value.events[0][field], []);
  assert.equal(value.events[0].report.status, "insufficient_evidence");
  assert.deepEqual(
    value.events[0].report.sections.map((section) => section.id),
    ["conclusion", "change", "context", "evidence"],
  );
  assert.equal(value.meta.dataMode, "api");
});

test("structured report states are accepted without inventing missing sections", async () => {
  const api = createApiClient("/api/v1", async () =>
    Response.json({ data: { ...issue, report } }),
  );
  const value = await loadPageData(api, "event", { id: "42" });
  assert.equal(value.events[0].report.status, "generating");
  assert.equal(value.events[0].report.model, "test-model");
  assert.equal(value.events[0].report.sections[0].body, null);
  assert.deepEqual(
    value.events[0].report.sections.map((section) => section.id),
    ["conclusion", "change", "context", "evidence"],
  );
});

test("invalid configuration rejects an async resource rather than crashing module construction", async () => {
  const client = createDataClient({ VITE_DATA_SOURCE: "invalid" });
  await assert.rejects(client.listIssues(), { code: "INVALID_CONFIG" });
});

test("page resources issue only the supported route requests, with one server page", async () => {
  const requests = [];
  const api = createApiClient("/api/v1", async (url) => {
    requests.push(url);
    return Response.json({
      data: [{ ...stock, issueCount: 3 }],
      meta: { pagination: { offset: 20, limit: 20, total: 41, hasMore: true } },
    });
  });
  const page = await loadPageData(api, "stocks", {
    listParams: { q: "NVIDIA", offset: 20, limit: 20 },
  });
  assert.equal(requests.length, 1);
  assert.equal(
    new URL(requests[0], "https://local").pathname,
    "/api/v1/stocks",
  );
  assert.equal(
    new URL(requests[0], "https://local").searchParams.get("offset"),
    "20",
  );
  assert.equal(page.pagination.total, 41);
  assert.equal(page.stocks[0].price, null);
  assert.equal(page.stocks[0].issueCount, 3);
  assert.deepEqual(page.stocks[0].eventIds, []);
});

test("stock details get linked issue cards separately and never invent relation rationale or prices", async () => {
  const requests = [];
  const api = createApiClient("/api/v1", async (url) => {
    requests.push(url);
    return Response.json(
      url.endsWith("/issues")
        ? {
            data: [
              {
                id: 42,
                label: null,
                pulseScore: 4,
                status: "VERIFYING",
                source: "live",
                snapshotTs: issue.snapshotTs,
                memberCount: 2,
                stockCount: 1,
              },
            ],
          }
        : { data: stock },
    );
  });
  const page = await loadPageData(api, "stock", { id: "nvda" });
  assert.deepEqual(requests, [
    "/api/v1/stocks/NVDA",
    "/api/v1/stocks/NVDA/issues",
  ]);
  assert.deepEqual(page.stocks[0].eventIds, ["42"]);
  assert.deepEqual(page.stocks[0].relations, []);
  assert.equal(page.stocks[0].description, null);
  assert.equal(page.events[0].title, "제목 미제공");
  assert.equal(page.collectionLimit, 50);
});

test("mock filtering, raw response projection, stable legacy aliases and cancellation", async () => {
  const page = await mockClient.listIssues({ limit: 1 });
  const id = page.data[0].id;
  assert.equal(typeof id, "number");
  assert.equal(page.meta.dataMode, undefined);
  assert.equal(page.included, undefined);
  assert.equal(page.data[0].summary, undefined);
  assert.equal(page.data[0].chart, undefined);
  const old = events[0].id;
  const legacy = await mockClient.getIssue(old);
  assert.equal(legacy.data.id, issueId(old));
  assert.deepEqual(legacy, await mockClient.getIssue(legacy.data.id));
  assert.equal(legacy.data.news, undefined);
  assert.equal(legacy.data.report.status, "ready");
  assert.deepEqual(
    legacy.data.report.sections.map((section) => section.id),
    ["conclusion", "change", "context", "evidence"],
  );
  assert.equal(legacy.data.relatedStocks.length <= 5, true);
  assert.deepEqual(
    (await mockClient.listStocks({ q: "no-such-stock" })).data,
    [],
  );
  assert.equal(
    (await mockClient.getStock(stocks[0].symbol.toLowerCase())).data.ticker,
    stocks[0].symbol,
  );
  assert.equal(
    (await mockClient.getStock(stocks[0].symbol)).data.price,
    undefined,
  );
  await assert.rejects(mockClient.getIssue("missing"), { status: 404 });
  await assert.rejects(mockClient.listIssues({ limit: 0 }), { status: 400 });
  await assert.rejects(mockClient.listIssues({ q: "unsupported" }), {
    status: 400,
  });
  await assert.rejects(mockClient.listStocks({ eventId: "unsupported" }), {
    status: 400,
  });
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(
    mockClient.listIssues({}, { signal: controller.signal }),
    { name: "AbortError" },
  );
  legacy.data.label = "changed";
  assert.notEqual((await mockClient.getIssue(old)).data.label, "changed");
});

test("saved records keep original keys, ignore individual 404s and expose removable stale entries", async () => {
  const old = events[0].id;
  const saved = await loadPageData(mockClient, "saved", {
    savedEvents: [old, "missing"],
    savedStocks: [stocks[0].symbol, "MISSING"],
  });
  assert.equal(saved.events[0].id, String(issueId(old)));
  assert.equal(saved.events[0].savedId, old);
  assert(saved.events[0].aliases.includes(old));
  assert.deepEqual(saved.missingSavedEvents, ["missing"]);
  assert.deepEqual(saved.missingSavedStocks, ["MISSING"]);
  assert.deepEqual(saved.entities, []);
  assert.equal(saved.stocks.length, 1);
  const failed = {
    ...mockClient,
    getIssue: async () => {
      throw new Error("offline");
    },
  };
  await assert.rejects(
    loadPageData(failed, "saved", { savedEvents: [old] }),
    /offline/,
  );
});

test("all nine API methods use current paths and query encoding; failures have no mock fallback", async () => {
  let seen;
  const signal = new AbortController().signal;
  const api = createApiClient(
    "https://example.test/api/v1/",
    async (url, options) => {
      seen = { url, options };
      return Response.json({ data: issue });
    },
  );
  await api.getIssue("a/b 한글", { signal });
  assert.equal(
    seen.url,
    `https://example.test/api/v1/issues/${encodeURIComponent("a/b 한글")}`,
  );
  assert.equal(seen.options.signal, signal);
  const related = createApiClient("/api/v1", async (url, options) => {
    seen = { url, options };
    return Response.json({ data: [] });
  });
  await related.listIssueStocks(42, { limit: 100 }, { signal });
  assert.equal(seen.url, "/api/v1/issues/42/stocks?limit=100");
  assert.equal(seen.options.signal, signal);
  // 주가: 티커 대문자화 + from/to 쿼리 인코딩. 응답은 계약 검증(빈 배열 허용).
  const priced = createApiClient("/api/v1", async (url, options) => {
    seen = { url, options };
    return Response.json({ data: [] });
  });
  await priced.getStockPrices(
    "nvda",
    { from: "2026-01-01", to: "2026-09-01" },
    { signal },
  );
  assert.equal(
    seen.url,
    "/api/v1/stocks/NVDA/prices?from=2026-01-01&to=2026-09-01",
  );
  assert.equal(seen.options.signal, signal);
  // 형식이 계약과 다르면 폴백 없이 INVALID_RESPONSE (mock 로 떨어지지 않는다).
  await assert.rejects(
    createApiClient("/api/v1", async () =>
      Response.json({ data: [{ tradeDate: "2026-01-02" }] }),
    ).getStockPrices("NVDA"),
    { code: "INVALID_RESPONSE" },
  );
  for (const status of [404, 500])
    await assert.rejects(
      createApiClient("/api/v1", async () =>
        Response.json({ error: { code: "TEST" } }, { status }),
      ).getIssue("x"),
      { status },
    );
  await assert.rejects(
    createApiClient("/api/v1", async () =>
      Response.json({ data: {} }),
    ).getIssue("x"),
    { code: "INVALID_RESPONSE" },
  );
  await assert.rejects(
    createApiClient("/api/v1", async () => {
      throw new TypeError("offline");
    }).getIssue("x"),
    { code: "REQUEST_FAILED" },
  );
});

test("pulse raw missing labels/keys become presentation fallbacks scoped to one snapshot", async () => {
  const raw = await mockClient.getPulseMap();
  const cluster = raw.data.clusters[0];
  cluster.label = null;
  cluster.issueKey = null;
  const result = presentPulseMap(raw, "mock");
  assert.equal(result.data.clusters[0].label, cluster.nodes[0].title);
  assert.equal(
    result.data.clusters[0].issueKey,
    `${raw.meta.source}:${raw.meta.snapshotTs}:${cluster.id}`,
  );
  assert.equal(raw.meta.dataMode, undefined);
  assert.equal(cluster.label, null);
});

test("equivalent UTC/offset timestamps select the same snapshot and date-only requests reject", async () => {
  const utc = "2026-09-10T00:00:00Z";
  const offset = "2026-09-10T09:00:00+09:00";
  const first = await mockClient.getPulseMap({
    snapshotTs: utc,
    source: "replay",
  });
  const second = await mockClient.getPulseMap({
    snapshotTs: offset,
    source: "replay",
  });
  assert.deepEqual(first, second);
  assert.equal(
    (await mockClient.listSnapshots({ from: offset, to: utc })).data.length,
    1,
  );
  for (const method of ["getPulseMap", "listIssues"])
    await assert.rejects(mockClient[method]({ snapshotTs: "2026-09-10" }), {
      code: "INVALID_QUERY",
    });
  await assert.rejects(mockClient.listSnapshots({ from: "2026-09-10" }), {
    code: "INVALID_QUERY",
  });
});

test("source filtering resolves the latest available snapshot and paging pins it", async () => {
  const seen = [];
  const client = {
    ...mockClient,
    listSnapshots: async (params) => {
      seen.push(["snapshots", params]);
      return mockClient.listSnapshots(params);
    },
    listIssues: async (params) => {
      seen.push(["issues", params]);
      return mockClient.listIssues(params);
    },
  };
  const first = await loadPageData(client, "explore", {
    listParams: { source: "replay", limit: 1 },
  });
  assert.equal(seen[0][0], "snapshots");
  assert.equal(seen[1][1].snapshotTs, first.meta.snapshotTs);
  const { nextListParams } = await import("../src/data/pagination.js");
  const secondParams = nextListParams(
    { source: "replay", offset: 0, limit: 1 },
    { offset: 1 },
    first.meta.snapshotTs,
  );
  seen.length = 0;
  await loadPageData(client, "explore", { listParams: secondParams });
  assert.deepEqual(
    seen.map((v) => v[0]),
    ["issues"],
  );
  assert.equal(seen[0][1].snapshotTs, first.meta.snapshotTs);
  assert.equal(
    nextListParams(secondParams, { source: "live" }, first.meta.snapshotTs)
      .snapshotTs,
    undefined,
  );
  seen.length = 0;
  const empty = await loadPageData(client, "explore", {
    listParams: { source: "live" },
  });
  assert.deepEqual(
    seen.map((v) => v[0]),
    ["snapshots"],
  );
  assert.equal(empty.pagination.total, 0);
});

test("mock stock counts and reverse issue cards describe the published snapshot relations", async () => {
  const ticker = stocks[0].symbol;
  const listing = await mockClient.listStocks({ q: ticker });
  const card = listing.data.find((v) => v.ticker === ticker);
  const related = await mockClient.listStockIssues(ticker);
  assert(card.issueCount >= related.data.length);
  assert.equal(related.data.length, Math.min(50, card.issueCount));
  for (const item of related.data.slice(0, 3)) {
    const detail = (await mockClient.getIssue(item.id)).data;
    assert.equal(item.pulseScore, detail.pulseScore);
    assert.equal(item.status, detail.status);
    assert(
      (await mockClient.listIssueStocks(item.id, { limit: 100 })).data.some(
        (v) => v.ticker === ticker,
      ),
    );
  }
});
