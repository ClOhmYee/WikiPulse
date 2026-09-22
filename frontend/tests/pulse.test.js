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

// legacy expansion 산출물(-115, CORE -161 이전)은 non-root 멤버에 집계 구간이 없다.
// 2026-09-21 LIVE 6개 스냅샷이 노드 하나 때문에 통째로 탈락했다 — 12개 클러스터의
// 정상 root 까지 같이 사라졌다. `unavailable` + 양쪽 모두 null 만 통과시킨다.
test("unavailable 멤버의 빈 집계 구간만 통과하고 나머지 조합은 그대로 reject", () => {
  const node = (v) => v.data.clusters[0].nodes[0];
  const check = (label, mutate, shouldPass) => {
    const copy = structuredClone(pulseMaps.at(-1));
    mutate(copy);
    if (shouldPass) {
      const out = validateMap(copy);
      // 노드를 걸러내지 않는다 — memberCount 계약이 유지돼야 한다.
      for (const cluster of out.data.clusters)
        assert.equal(cluster.memberCount, cluster.nodes.length, label);
      assert.equal(out.meta.nodeCount, copy.meta.nodeCount, label);
    } else {
      assert.throws(() => validateMap(copy), /metric window/, label);
    }
  };
  // 1. 일반 노드 + 정상 구간
  check("normal + valid", () => {}, true);
  // 2. 일반 노드 + 빈 구간 → 기존 계약 그대로 거부
  check(
    "normal + null",
    (v) => Object.assign(node(v), { windowStart: null, windowEnd: null }),
    false,
  );
  // 3. unavailable + 양쪽 null → 통과 (이번 완화의 대상)
  check(
    "unavailable + both null",
    (v) =>
      Object.assign(node(v), {
        completeness: "unavailable",
        windowStart: null,
        windowEnd: null,
      }),
    true,
  );
  // 4. unavailable + 한쪽만 null → 비정상 조합이라 거부
  check(
    "unavailable + start null",
    (v) => Object.assign(node(v), { completeness: "unavailable", windowStart: null }),
    false,
  );
  check(
    "unavailable + end null",
    (v) => Object.assign(node(v), { completeness: "unavailable", windowEnd: null }),
    false,
  );
  // 5. unavailable + 정상 구간 → 값이 있으면 검사한다
  check(
    "unavailable + valid",
    (v) => Object.assign(node(v), { completeness: "unavailable" }),
    true,
  );
  // 6. unavailable + 역순 구간 → completeness 로 검사를 면제받지 않는다
  check(
    "unavailable + reversed",
    (v) =>
      Object.assign(node(v), {
        completeness: "unavailable",
        windowStart: node(v).windowEnd,
      }),
    false,
  );
  // pending 은 완화 대상이 아니다 — 조회수 대기는 구간이 이미 정해져 있다.
  check(
    "pending + both null",
    (v) =>
      Object.assign(node(v), {
        completeness: "pending",
        windowStart: null,
        windowEnd: null,
      }),
    false,
  );
});

// 운영 2026-09-21T12:00:00Z (live) 와 같은 구조: root 1개(complete·구간 있음) +
// clickstream expansion 멤버 2개(unavailable·지표 전부 null·구간 없음).
test("2026-09-21 LIVE 와 같은 구조의 legacy 스냅샷이 렌더 대상으로 통과한다", () => {
  const snapshotTs = "2026-09-21T12:00:00Z";
  const member = (pageId, title) => ({
    pageId,
    title,
    wiki: "enwiki",
    isSeed: true, // -115 이후 추가 씨드도 true 로 저장된다
    editCount: null,
    views: null,
    editBaseline: null,
    viewBaseline: null,
    spikeScore: null,
    sizeScore: null,
    completeness: "unavailable",
    windowStart: null,
    windowEnd: null,
  });
  const legacy = {
    meta: {
      snapshotTs,
      source: "live",
      scoreVersion: "v1",
      newWindowHours: 24,
      clusterCount: 1,
      nodeCount: 3,
      edgeCount: 2,
      truncated: false,
    },
    data: {
      clusters: [
        {
          id: "137886",
          issueKey: "live:enwiki:2026 Israeli legislative election",
          label: "2026 Israeli legislative election",
          summary: null,
          category: "other",
          status: "DETECTED",
          firstDetectedAt: snapshotTs,
          hot: true,
          pulseScore: 7.5,
          memberCount: 3,
          nodes: [
            {
              pageId: "500001",
              title: "2026 Israeli legislative election",
              wiki: "enwiki",
              isSeed: true,
              editCount: 12,
              views: 9000,
              editBaseline: null,
              viewBaseline: null,
              spikeScore: 7.5,
              sizeScore: 0.5,
              completeness: "complete",
              windowStart: "2026-09-21T11:00:00Z",
              windowEnd: snapshotTs,
            },
            member("500002", "Amcha Yisrael"),
            member("500003", "Israel First (political party)"),
          ],
          edges: [
            {
              id: "e1",
              sourcePageId: "500001",
              targetPageId: "500002",
              kind: "clickstream",
              directed: true,
              weight: 120,
              evidence: { label: "클릭 이동 120회", month: "2026-08" },
            },
            {
              id: "e2",
              sourcePageId: "500001",
              targetPageId: "500003",
              kind: "clickstream",
              directed: true,
              weight: 45,
              evidence: { label: "클릭 이동 45회", month: "2026-08" },
            },
          ],
        },
      ],
    },
  };
  const out = validateMap(legacy, { snapshotTs, source: "live" });
  const cluster = out.data.clusters[0];
  assert.equal(cluster.memberCount, cluster.nodes.length);
  assert.equal(cluster.nodes.length, 3);
  // 지표가 없는 멤버도 남아 있어야 한다(노드 제거 금지).
  assert.equal(cluster.nodes.filter((v) => v.windowStart === null).length, 2);
});
