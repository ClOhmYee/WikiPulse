import test from "node:test";
import assert from "node:assert/strict";
import {
  rankIssues,
  rankingWindow,
  validateRankings,
} from "../src/data/rankings.js";
import { createApiClient } from "../src/data/api/client.js";

test("rolling windows use 30 days and a KST calendar year including leap day", () => {
  assert.deepEqual(rankingWindow("2024-02-29T03:00:00Z"), {
    asOf: "2024-02-29T03:00:00.000Z",
    monthFrom: "2024-01-30T03:00:00.000Z",
    yearFrom: "2023-02-28T03:00:00.000Z",
  });
  assert.equal(
    rankingWindow("2025-02-28T16:00:00Z").yearFrom,
    "2024-02-29T16:00:00.000Z",
  );
});
test("rankings deduplicate stable issues at their peak and exclude out-of-window and discarded rows", () => {
  const window = rankingWindow("2026-09-22T00:00:00Z");
  const row = (id, key, score, time = window.asOf, status = "CONFIRMED") => ({
    id,
    issueKey: key,
    label: `Issue ${id}`,
    pulseScore: score,
    snapshotTs: time,
    status,
  });
  const rows = [
    row(1, "a", 10),
    row(2, "a", 20, window.monthFrom),
    row(3, "b", 15),
    row(4, "c", 99, "2026-08-01T00:00:00Z"),
    row(5, "d", 100, "2026-09-23T00:00:00Z"),
    row(6, "e", 100, window.asOf, "DISCARDED"),
    row(7, null, 2),
    row(8, null, 2),
  ];
  assert.deepEqual(
    rankIssues(rows, window.monthFrom, window.asOf).map((row) => row.id),
    [2, 3, 7, 8],
  );
  assert.deepEqual(
    rankIssues(rows, window.yearFrom, window.asOf).map((row) => row.id),
    [4, 2, 3, 7, 8],
  );
  const tied = Array.from({ length: 12 }, (_, i) =>
    row(i + 20, `unique${i}`, 30),
  );
  assert.deepEqual(
    rankIssues(tied.reverse(), window.monthFrom, window.asOf).map(
      (row) => row.id,
    ),
    Array.from({ length: 10 }, (_, i) => i + 20),
  );
});
test("rankings request uses one endpoint and rejects malformed data without fallback", async () => {
  const data = {
    ...rankingWindow("2026-09-22T00:00:00Z"),
    monthly: [],
    yearly: [],
  };
  const controller = new AbortController();
  const client = createApiClient("/api/v1", async (url, options) => {
    assert.equal(url, "/api/v1/issues/rankings");
    assert.equal(options.signal, controller.signal);
    return { ok: true, json: async () => ({ data }) };
  });
  assert.deepEqual(
    (await client.getIssueRankings({}, { signal: controller.signal })).data,
    data,
  );
  assert.throws(
    () => validateRankings({ data: { ...data, monthly: [{ id: 0 }] } }),
    /순위 응답/,
  );
});
