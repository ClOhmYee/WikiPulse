import test from "node:test";
import assert from "node:assert/strict";
import { listExploreIssues } from "../src/data/explore.js";
import { nextListParams } from "../src/data/pagination.js";

const times = { live: "2026-09-21T12:00:00Z", replay: "2025-06-13T00:00:00Z" };
function fixture(count = 3) {
  const calls = [];
  const rows = Object.entries(times).flatMap(([source, snapshotTs], index) =>
    Array.from({ length: count }, (_, i) => ({
      id: i * 2 + index + 1,
      source,
      snapshotTs,
      pulseScore: count - i,
      status: source === "live" ? "DETECTED" : "CONFIRMED",
    })),
  );
  const client = {
    listSnapshots: async () => {
      calls.push("snapshots");
      return {
        data: Object.entries(times).flatMap(([source, snapshotTs]) => [
          { source, snapshotTs: "2024-01-01T00:00:00Z", clusterCount: 99 },
          { source, snapshotTs, clusterCount: count },
        ]),
      };
    },
    listIssues: async (params, options) => {
      calls.push({ ...params, signal: options?.signal });
      assert(params.limit <= 100);
      const values = rows.filter(
        (row) =>
          row.source === params.source &&
          row.snapshotTs === params.snapshotTs &&
          (!params.status || row.status === params.status),
      );
      const data = values.slice(params.offset, params.offset + params.limit);
      return {
        data,
        meta: {
          snapshotTs: params.snapshotTs,
          pagination: {
            offset: params.offset,
            limit: params.limit,
            total: values.length,
            hasMore: params.offset + data.length < values.length,
          },
        },
      };
    },
  };
  return { client, calls };
}

test("all sources filters both latest snapshots, including replay-only confirmed issues", async () => {
  const { client, calls } = fixture();
  const all = await listExploreIssues(client);
  assert.deepEqual(
    all.data.map((row) => row.id),
    [1, 2, 3, 4, 5, 6],
  );
  assert.deepEqual(all.meta.sourceSnapshots, times);
  assert.equal(all.meta.snapshotTs, undefined);
  const confirmed = await listExploreIssues(client, { status: "CONFIRMED" });
  assert.deepEqual(
    confirmed.data.map((row) => row.id),
    [2, 4, 6],
  );
  assert.equal(confirmed.meta.pagination.total, 3);
  assert(
    calls
      .filter((call) => typeof call === "object")
      .every((call) => call.source),
  );
});

test("merged pagination preserves global order, totals and both snapshots past the API cap", async () => {
  const { client, calls } = fixture(125);
  const initial = { offset: 0, limit: 20 };
  const first = await listExploreIssues(client, initial);
  const next = nextListParams(
    initial,
    { offset: 200 },
    undefined,
    first.meta.sourceSnapshots,
  );
  client.listSnapshots = () => {
    throw new Error("Paging must not select a newer snapshot");
  };
  const result = await listExploreIssues(client, next);
  assert.deepEqual(
    result.data.map((row) => row.id),
    Array.from({ length: 20 }, (_, i) => i + 201),
  );
  assert.deepEqual(result.meta.pagination, {
    offset: 200,
    limit: 20,
    total: 250,
    hasMore: true,
  });
  const last = await listExploreIssues(client, { ...next, offset: 240 });
  assert.equal(last.data.length, 10);
  assert.equal(last.meta.pagination.hasMore, false);
  const filtered = nextListParams(
    next,
    { status: "CONFIRMED" },
    undefined,
    times,
  );
  assert.equal(filtered.offset, 0);
  assert.equal(filtered.sourceSnapshots, undefined);
  assert(calls.some((call) => call.offset === 100));
});

test("single source keeps server pagination and excludes the other source", async () => {
  const { client } = fixture();
  const result = await listExploreIssues(client, {
    source: "replay",
    status: "CONFIRMED",
    offset: 1,
    limit: 1,
  });
  assert.deepEqual(
    result.data.map((row) => row.id),
    [4],
  );
  assert.equal(result.meta.pagination.total, 3);
  assert.deepEqual(result.meta.sourceSnapshots, { replay: times.replay });
});

test("completed empty snapshots are retained; no snapshots makes no issue request", async () => {
  const { client, calls } = fixture();
  client.listSnapshots = async () => ({
    data: [
      { source: "live", snapshotTs: times.live, clusterCount: 3 },
      { source: "replay", snapshotTs: times.replay, clusterCount: 3 },
      { source: "replay", snapshotTs: "2025-06-14T00:00:00Z", clusterCount: 0 },
    ],
  });
  const empty = await listExploreIssues(client, { status: "CONFIRMED" });
  assert.deepEqual(empty.data, []);
  assert.equal(empty.meta.sourceSnapshots.replay, "2025-06-14T00:00:00Z");
  client.listSnapshots = async () => ({ data: [] });
  calls.length = 0;
  const missing = await listExploreIssues(client);
  assert.equal(missing.meta.pagination.total, 0);
  assert.deepEqual(calls, []);
});

test("a source failure is surfaced instead of presenting an incomplete combined result", async () => {
  const { client, calls } = fixture();
  const controller = new AbortController();
  const original = client.listIssues;
  client.listIssues = async (params, options) => {
    if (params.source === "replay") throw new Error("replay unavailable");
    return original(params, options);
  };
  await assert.rejects(
    listExploreIssues(client, {}, { signal: controller.signal }),
    /replay unavailable/,
  );
  assert.equal(calls[1].signal, controller.signal);
});
