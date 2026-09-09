import { events, entities } from "./catalog.js";

// Authored synthetic history, never presented as observed Wikipedia activity.
const times = ["2025-06-20T03:00:00Z", "2025-06-22T00:00:00Z", "2025-06-22T05:00:00Z", "2025-06-23T00:00:00Z", "2025-06-23T14:00:00Z", "2025-06-23T15:00:00Z", "2025-06-24T03:00:00Z"];
// Explicit evidence pairs: membership never implies a relationship.
const relationships = [
  ["strait-of-hormuz", "iran", "clickstream", 4500],
  ["iran", "petroleum", "wikidata", 0.8],
  ["semiconductor", "export-control", "clickstream", 3200],
  ["nvidia", "semiconductor", "wikidata", 0.9],
  ["nuclear-power", "uranium", "clickstream", 1700],
  ["spacex", "reusable-launch-system", "wikidata", 0.8],
  ["lithium", "lithium-ion-battery", "clickstream", 2100],
  ["cybersecurity", "cloud-computing", "wikidata", 0.7],
];
const firstSeen = ["2025-06-18T00:00:00Z", "2025-06-21T12:00:00Z", "2025-06-19T00:00:00Z", "2025-06-22T02:00:00Z", "2025-06-23T00:00:00Z", "2025-06-24T00:00:00Z"];
function makeSnapshot(snapshotTs, index) {
  const latest = index === times.length - 1;
  const clusters = index === 0 ? [] : events.flatMap((event, i) => {
    if (Date.parse(firstSeen[i]) > Date.parse(snapshotTs)) return [];
    // A short-lived signal disappears; this record still has a report fixture.
    if (i === 2 && index === 4) return [];
    const ids = event.articleIds;
    const visible = !latest && i === 0 ? ids.slice(0, 2) : ids;
    const nodes = visible.map((pageId, n) => {
      const entity = entities.find((v) => v.id === pageId);
      const sizeScore = Math.min(1, 0.18 + ((i + n * 3 + index * 2) % 9) / 12);
      const pending = i === 5 && n === 1;
      return { pageId, wiki: "enwiki", title: entity.title, isSeed: n === 0,
        editCount: 15 + index * 11 + n * 8, views: pending ? null : 1800 + index * 560 + n * 770,
        editBaseline: 8 + n, viewBaseline: pending ? null : 720 + n * 80,
        spikeScore: pending ? null : Math.round(sizeScore * 100) / 10, sizeScore: pending ? null : sizeScore,
        completeness: pending ? "pending" : "complete",
        windowStart: new Date(Date.parse(snapshotTs) - 3_600_000).toISOString(), windowEnd: snapshotTs };
    });
    const edges = relationships.filter(([a, b]) => visible.includes(a) && visible.includes(b)).map(([a, b, kind, weight], n) => ({
      id: `${event.id}-${n}`, sourcePageId: a, targetPageId: b, kind, directed: kind === "clickstream", weight,
      evidence: kind === "clickstream" ? { label: "Wikipedia Clickstream · 합성 예시", month: "2025-05" }
        : { label: "Wikidata 주제 관계 · 합성 예시", observedAt: "2025-06-19T00:00:00Z" },
    }));
    return [{ id: latest ? event.id : `${event.id}~${index}`, issueKey: event.id,
      label: event.title, summary: latest ? event.summary : `${event.title} 관련 문서의 변화가 포착되었습니다. 이 시점의 합성 요약입니다.`,
      category: event.category, firstDetectedAt: firstSeen[i], hot: (i + index) % 3 !== 0,
      pulseScore: Math.round((3 + ((6 - i) * 0.8 + index) / 2) * 10) / 10,
      status: latest ? "CONFIRMED" : "DETECTED", memberCount: nodes.length, nodes, edges }];
  });
  return { data: { clusters }, meta: { snapshotTs, source: "replay", dataMode: "mock", scoreVersion: "synthetic-v1", newWindowHours: 24,
    clusterCount: clusters.length, nodeCount: clusters.reduce((n, c) => n + c.nodes.length, 0), edgeCount: clusters.reduce((n, c) => n + c.edges.length, 0), truncated: false } };
}
export const pulseMaps = times.map(makeSnapshot);
export const pulseSnapshots = { data: pulseMaps.map(({ meta }) => ({ snapshotTs: meta.snapshotTs, source: meta.source, clusterCount: meta.clusterCount })) };

export function makeStressMap() {
  const snapshotTs = times.at(-1);
  const clusters = Array.from({ length: 20 }, (_, i) => {
    const nodes = Array.from({ length: 25 }, (_, n) => ({
      pageId: `page-${i}-${n}`, wiki: "enwiki", title: `검증 문서 ${i + 1}-${n + 1}`, isSeed: n === 0,
      editCount: 20 + n, views: 2000 + n * 200, editBaseline: 5, viewBaseline: 500,
      spikeScore: 1 + n / 4, sizeScore: (n + 1) / 25, completeness: "complete",
      windowStart: "2025-06-24T02:00:00Z", windowEnd: snapshotTs,
    }));
    const edges = nodes.flatMap((node, n) => [1, 3].map((step) => ({
      id: `e-${i}-${n}-${step}`, sourcePageId: node.pageId, targetPageId: nodes[(n + step) % 25].pageId,
      kind: "clickstream", directed: true, weight: 1000 + n * 20,
      evidence: { label: "부하 검증용 합성 관계", month: "2025-05" },
    })));
    return { id: `stress-${i}`, issueKey: `stress-${i}`, label: `성능 검증 이슈 ${i + 1}`, summary: "성능 검증용 합성 데이터", category: "technology", firstDetectedAt: "2025-06-23T23:00:00Z", hot: true, pulseScore: 20 - i / 2, status: "CONFIRMED", memberCount: 25, nodes, edges };
  });
  return { data: { clusters }, meta: { snapshotTs, source: "replay", dataMode: "mock", scoreVersion: "synthetic-v1", newWindowHours: 24, clusterCount: 20, nodeCount: 500, edgeCount: 1000, truncated: false } };
}
