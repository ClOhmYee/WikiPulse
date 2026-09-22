import test from "node:test";
import assert from "node:assert/strict";
import { mockClient } from "../src/data/mock/client.js";
import { pulseMaps, makeStressMap } from "../src/data/mock/fixtures/pulse.js";
import { validateMap, validateSnapshots } from "../src/data/pulse/contract.js";
import {
  isNewIssue,
  kstDate,
  closestSnapshot,
  calendarDays,
  timelineSnapshots,
} from "../src/data/pulse/time.js";
import { createApiClient } from "../src/data/api/client.js";
import { createLayoutEngine, nodeRadius } from "../src/pages/pulse/layout.js";

test("timeline spans sources chronologically and resolves overlapping instants", () => {
  const older = { source: "replay", snapshotTs: "2025-06-01T00:00:00Z" };
  const live = { source: "live", snapshotTs: "2026-09-21T00:00:00Z" };
  const duplicate = {
    source: "replay",
    snapshotTs: "2026-09-21T09:00:00+09:00",
  };
  assert.deepEqual(timelineSnapshots([live, duplicate, older]), [older, live]);
  assert.deepEqual(timelineSnapshots([older, duplicate, live]), [older, live]);
  assert.deepEqual(timelineSnapshots([]), []);
});

test("KST dates, missing dates, NEW boundary and real timestamp snapping", () => {
  assert.equal(kstDate("2025-06-23T15:00:00Z"), "2025-06-24");
  assert.equal(
    isNewIssue("2025-06-23T03:00:00Z", "2025-06-24T03:00:00Z"),
    false,
  );
  assert.equal(
    isNewIssue("2025-06-23T03:00:01Z", "2025-06-24T03:00:00Z"),
    true,
  );
  assert.equal(isNewIssue(null, "2025-06-24T03:00:00Z"), false);
  assert.equal(
    isNewIssue("2025-06-25T00:00:00Z", "2025-06-24T03:00:00Z"),
    false,
  );
  const points = [
    { snapshotTs: "2025-06-20T00:00:00Z" },
    { snapshotTs: "2025-06-22T05:00:00Z" },
  ];
  assert.equal(calendarDays(points)[1].available, false);
  assert.equal(
    closestSnapshot(points, Date.parse("2025-06-22T04:00:00Z")),
    points[1],
  );
});
test("daily history and stress data validate, including empty response support", async () => {
  const list = await mockClient.listSnapshots();
  validateSnapshots(list);
  for (const map of pulseMaps) validateMap(map);
  assert.equal(list.data.length, 375);
  assert(pulseMaps.every((v) => v.meta.clusterCount > 0));
  const empty = structuredClone(pulseMaps[0]);
  empty.data.clusters = [];
  Object.assign(empty.meta, { clusterCount: 0, nodeCount: 0, edgeCount: 0 });
  validateMap(empty);
  const stress = validateMap(makeStressMap());
  assert.equal(stress.meta.nodeCount, 500);
  assert.equal(stress.meta.edgeCount, 1000);
  assert.notDeepEqual(
    pulseMaps[1].data.clusters.map((v) => v.id),
    pulseMaps.at(-1).data.clusters.map((v) => v.id),
  );
  const latest = pulseMaps.at(-1);
  assert(
    latest.data.clusters.some(
      (v) => v.hot && isNewIssue(v.firstDetectedAt, latest.meta.snapshotTs),
    ),
  );
});
test("invalid graph references, duplicates, future evidence and mixed snapshots reject", () => {
  for (const mutate of [
    (v) => {
      v.data.clusters[0].edges[0].targetPageId = "missing";
    },
    (v) => {
      v.data.clusters[0].edges.push({
        ...v.data.clusters[0].edges[0],
        id: "duplicate",
      });
    },
    (v) => {
      v.data.clusters[0].nodes[0].sizeScore = 2;
    },
    (v) => {
      v.data.clusters[0].nodes[0].windowEnd = "2027-01-01T00:00:00Z";
    },
    (v) => {
      v.data.clusters[0].edges[0].evidence.month = "2026-10";
    },
    (v) => {
      v.meta.nodeCount++;
    },
  ]) {
    const copy = structuredClone(pulseMaps.at(-1));
    mutate(copy);
    assert.throws(() => validateMap(copy), /펄스맵 데이터 형식/);
  }
  assert.throws(
    () => validateMap(pulseMaps.at(-1), { snapshotTs: "2025-01-01T00:00:00Z" }),
    /mismatch/,
  );
});
test("API map boundary preserves source, timestamp and cancellation without fallback", async () => {
  const map = pulseMaps.at(-1);
  const controller = new AbortController();
  let seen;
  const client = createApiClient("/api/v1", async (url, options) => {
    seen = { url, options };
    return new Response(JSON.stringify(map));
  });
  await client.getPulseMap(
    { snapshotTs: map.meta.snapshotTs, source: "replay" },
    { signal: controller.signal },
  );
  assert(seen.url.startsWith("/api/v1/issues/map?"));
  assert(seen.url.includes("source=replay"));
  assert.equal(seen.options.signal, controller.signal);
  const broken = createApiClient(
    "/api/v1",
    async () => new Response("{}", { status: 503 }),
  );
  await assert.rejects(broken.getPulseMap(), /불러오지 못했습니다/);
  controller.abort();
  await assert.rejects(
    mockClient.getPulseMap({}, { signal: controller.signal }),
    { name: "AbortError" },
  );
});

test("unlabelled production graphs preserve null label and missing stable issue key", () => {
  const map = structuredClone(pulseMaps.at(-1));
  map.data.clusters[0].label = null;
  map.data.clusters[0].issueKey = null;
  const response = validateMap(map);
  assert.equal(
    response.data.clusters.find((v) => v.id === map.data.clusters[0].id).label,
    null,
  );
  assert.equal(
    response.data.clusters.find((v) => v.id === map.data.clusters[0].id)
      .issueKey,
    null,
  );
});

test("layout preserves identity and fixed score scale and handles 500 nodes", () => {
  const layout = createLayoutEngine();
  const graph = makeStressMap();
  const start = performance.now();
  const first = layout(graph.data.clusters);
  const duration = performance.now() - start;
  assert(duration < 2000, `layout took ${duration}ms`);
  const filtered = layout([graph.data.clusters[3]]);
  assert.deepEqual(filtered.clusters[0].nodes, first.clusters[3].nodes);
  const next = structuredClone(graph.data.clusters);
  next[3].nodes[0].sizeScore = 0.8;
  const changed = layout(next).clusters[3].nodes[0];
  assert.equal(changed.x, first.clusters[3].nodes[0].x);
  assert.equal(changed.y, first.clusters[3].nodes[0].y);
  assert.equal(changed.radius, nodeRadius(0.8));
  for (const c of first.clusters)
    for (const n of c.nodes)
      assert(Number.isFinite(n.x) && Number.isFinite(n.y));
  console.log(`500 nodes / 1000 edges layout: ${duration.toFixed(1)}ms`);
});

test("cluster importance decreases with distance, packing does not overlap, and history cannot change ranking", () => {
  const input = makeStressMap().data.clusters;
  const engine = createLayoutEngine();
  const first = engine(input).clusters;
  const ranked = [...first].sort((a, b) => b.pulseScore - a.pulseScore);
  assert.equal(ranked[0].x, 0);
  assert.equal(ranked[0].y, 0);
  for (let i = 1; i < ranked.length; i++) {
    assert(
      Math.hypot(ranked[i].x, ranked[i].y) >
        Math.hypot(ranked[i - 1].x, ranked[i - 1].y),
    );
    for (let j = 0; j < i; j++) {
      assert(
        Math.hypot(ranked[i].x - ranked[j].x, ranked[i].y - ranked[j].y) >=
          ranked[i].radius + ranked[j].radius + 119,
      );
    }
  }
  const changed = input.map((c, i) => ({ ...c, pulseScore: i }));
  const after = engine(changed).clusters;
  assert.equal(after.at(-1).x, 0);
  assert.equal(after.at(-1).y, 0);
  assert.deepEqual(after, createLayoutEngine()(changed).clusters);
  assert.equal(nodeRadius(0), 12);
  assert.equal(nodeRadius(1), 40);
  assert.deepEqual(engine([]).clusters, []);
});
