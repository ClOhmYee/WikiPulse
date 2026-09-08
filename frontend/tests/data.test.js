import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import Ajv from "ajv";
import yaml from "js-yaml";
import { mockClient } from "../src/data/mock/client.js";
import { events, entities, stocks } from "../src/data/mock/fixtures/catalog.js";
import { readDataConfig } from "../src/data/config.js";
import { describeSource } from "../src/data/contracts.js";
import { createApiClient } from "../src/data/api/client.js";
import { loadPageData, readAll } from "../src/data/resources.js";

test("configuration defaults to mock, validates source and preserves explicit API URL", () => {
  assert.deepEqual(readDataConfig(), { source: "mock", baseURL: "/api/v1" });
  assert.deepEqual(readDataConfig({ VITE_DATA_SOURCE: "api", VITE_API_BASE_URL: "https://example.test/v1/" }), { source: "api", baseURL: "https://example.test/v1" });
  assert.throws(() => readDataConfig({ VITE_DATA_SOURCE: "false" }), { code: "INVALID_CONFIG" });
  assert.throws(() => readDataConfig({ VITE_DATA_SOURCE: "api", VITE_API_BASE_URL: "" }), { code: "INVALID_CONFIG" });
  assert.throws(() => readDataConfig({ VITE_DATA_SOURCE: "api", VITE_API_BASE_URL: "//external.test" }), { code: "INVALID_CONFIG" });
  assert.equal(describeSource({ dataMode: "mock" }).label, "데모 데이터");
  assert.equal(describeSource({ dataMode: "api" }).label, "출처 확인 필요");
});

test("mock responses conform to the proposed OpenAPI schemas", async () => {
  const spec = yaml.load(readFileSync(new URL("../docs/openapi.yaml", import.meta.url), "utf8"));
  const ajv = new Ajv({ allErrors: true, nullable: true, unknownFormats: "ignore", schemaId: "auto" });
  // OpenAPI annotations are not JSON Schema validation keywords.
  ajv.addSchema({ $id: "contract", components: spec.components });
  for (const [schema, method, args] of [
    ["CategoryResponse", "listCategories", []], ["EventListResponse", "listEvents", [{ limit: 2 }]],
    ["EventResponse", "getEvent", [events[0].id]], ["EntityListResponse", "listEntities", [{}]],
    ["EntityResponse", "getEntity", [entities[0].id]], ["StockListResponse", "listStocks", [{}]],
    ["StockResponse", "getStock", [stocks[0].symbol]], ["SearchResponse", "searchWorkspace", [{ q: "Iran" }]],
  ]) {
    const validate = ajv.compile({ $ref: `contract#/components/schemas/${schema}` });
    const response = await mockClient[method](...args);
    assert.equal(validate(response), true, `${method}: ${JSON.stringify(validate.errors)}`);
  }
});

test("mock filtering, projection, empty data, encoded symbols and cancellation", async () => {
  const response = await mockClient.listEvents({ category: events[0].category, limit: 1 });
  assert.equal(response.data.length, 1);
  assert.equal(response.data[0].category, events[0].category);
  assert.equal(response.data[0].timeline, undefined);
  assert.ok((await mockClient.getEvent(events[0].id)).data.timeline);
  assert.deepEqual((await mockClient.listStocks({ q: "no-such-stock" })).data, []);
  assert.deepEqual((await mockClient.searchWorkspace({ q: " " })).data, []);
  assert.equal((await mockClient.getStock(stocks[0].symbol.toLowerCase())).data.symbol, stocks[0].symbol);
  await assert.rejects(mockClient.getEntity("missing"), { status: 404 });
  await assert.rejects(mockClient.listEvents({ limit: 0 }), { status: 400 });
  await assert.rejects(mockClient.listEvents({ window: "bad" }), { status: 400 });
  await assert.rejects(mockClient.listStocks({ relationType: "direct" }), { status: 400 });
  const controller = new AbortController(); controller.abort();
  await assert.rejects(mockClient.listEvents({}, { signal: controller.signal }), { name: "AbortError" });
  const full = await mockClient.getEvent(events[0].id); full.data.title = "changed";
  assert.equal((await mockClient.getEvent(events[0].id)).data.title, events[0].title);
});

test("all pages and their included objects are merged without treating page one as the catalogue", async () => {
  const offsets = [];
  const list = (params, options) => { offsets.push(params.offset); return mockClient.listEvents({ ...params, limit: 2 }, options); };
  const response = await readAll(list, {}, {});
  assert.deepEqual(offsets, [0, 2, 4]);
  assert.equal(response.data.length, events.length);
  assert.equal(new Set(response.included.entities.map((item) => item.id)).size, response.included.entities.length);
  assert.equal(response.meta.pagination, undefined);
  await assert.rejects(readAll(async () => ({ data: [], meta: { pagination: { offset: 0, total: 5, hasMore: true } } }), {}, {}), { code: "INVALID_PAGINATION" });
});

test("page loaders preserve detail fields, related data, and only selected saved records", async () => {
  for (const [resource, id, field] of [["event", events[0].id, "events"], ["entity", entities[0].id, "entities"], ["stock", stocks[0].symbol, "stocks"]]) {
    const value = await loadPageData(mockClient, resource, { id }, {});
    assert.ok(value[field].find((item) => (item.id ?? item.symbol) === id).chart);
    assert.ok(value.categories.length);
  }
  const saved = await loadPageData(mockClient, "saved", { savedEvents: [events[0].id, "missing"], savedStocks: [stocks[0].symbol] }, {});
  assert.deepEqual(saved.events.map((item) => item.id), [events[0].id]);
  assert.deepEqual(saved.stocks.map((item) => item.symbol), [stocks[0].symbol]);
  const unavailable = { ...mockClient, getEvent: async () => { throw new Error("offline"); } };
  await assert.rejects(loadPageData(unavailable, "saved", { savedEvents: [events[0].id] }, {}), /offline/);
});

test("HTTP client encodes paths and queries, forwards cancellation and rejects HTTP/invalid/network responses", async () => {
  let captured;
  const signal = new AbortController().signal;
  const api = createApiClient("https://example.test/api/v1/", async (url, options) => {
    captured = { url, options };
    return Response.json(await mockClient.getEvent(events[0].id));
  });
  await api.getEvent("a/b 한글", { signal });
  assert.equal(captured.url, `https://example.test/api/v1/events/${encodeURIComponent("a/b 한글")}`);
  assert.equal(captured.options.signal, signal);
  const search = createApiClient("/api/v1", async (url) => { captured = url; return Response.json(await mockClient.searchWorkspace({ q: "호르무즈" })); });
  await search.searchWorkspace({ q: "호르무즈 & A", limit: 7 });
  assert.equal(new URL(captured, "https://local.test").searchParams.get("q"), "호르무즈 & A");
  for (const status of [404, 500]) {
    const failed = createApiClient("/api/v1", async () => Response.json({ error: { code: "TEST" } }, { status }));
    await assert.rejects(failed.getEvent("x"), { status });
  }
  await assert.rejects(createApiClient("/api/v1", async () => Response.json({ data: {} })).getEvent("x"), { code: "INVALID_RESPONSE" });
  await assert.rejects(createApiClient("/api/v1", async () => { throw new TypeError("offline"); }).getEvent("x"), { code: "REQUEST_FAILED" });
});
