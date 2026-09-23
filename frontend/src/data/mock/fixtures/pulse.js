// Test/contract fixtures only. The application creates one requested map at a time.
import { dates, snapshotAt, timestamp } from "./history.js";
export const pulseMaps = dates.map(snapshotAt);
export const pulseSnapshots = {
  data: pulseMaps.map(({ meta }) => ({
    snapshotTs: meta.snapshotTs,
    source: meta.source,
    clusterCount: meta.clusterCount,
  })),
};
const times = dates.map(timestamp);
export function makeStressMap() {
  const snapshotTs = times.at(-1);
  const clusters = Array.from({ length: 20 }, (_, i) => {
    const nodes = Array.from({ length: 25 }, (_, n) => ({
      pageId: `page-${i}-${n}`,
      wiki: "enwiki",
      title: `검증 문서 ${i + 1}-${n + 1}`,
      // ko 있음/없음을 한 스냅샷에 섞어 둔다 — 계약 검증이 두 경로를 다 지나야 한다.
      // 실측상 클러스터 편입 문서의 절반 가까이가 ko 판이 없다(2026-09-22).
      titleKo: n % 2 === 0 ? `검증 문서 한국어 ${i + 1}-${n + 1}` : null,
      // ko 도 번역도 없는 노드를 남겨 영문 폴백 경로까지 계약 검증이 지나게 한다.
      titleKoFallback: n % 3 === 0 ? `검증 문서 번역 ${i + 1}-${n + 1}` : null,
      isSeed: n === 0,
      editCount: 20 + n,
      views: 2000 + n * 200,
      editBaseline: 5,
      viewBaseline: 500,
      spikeScore: 1 + n / 4,
      sizeScore: (n + 1) / 25,
      completeness: "complete",
      windowStart: new Date(Date.parse(snapshotTs) - 3_600_000).toISOString(),
      windowEnd: snapshotTs,
    }));
    const edges = nodes.flatMap((node, n) =>
      [1, 3].map((step) => ({
        id: `e-${i}-${n}-${step}`,
        sourcePageId: node.pageId,
        targetPageId: nodes[(n + step) % 25].pageId,
        kind: "clickstream",
        directed: true,
        weight: 1000 + n * 20,
        evidence: { label: "부하 검증용 합성 관계", month: "2026-08" },
      })),
    );
    return {
      id: `stress-${i}`,
      issueKey: `stress-${i}`,
      label: `성능 검증 이슈 ${i + 1}`,
      summary: "성능 검증용 합성 데이터",
      category: "technology",
      firstDetectedAt: new Date(
        Date.parse(snapshotTs) - 3_600_000,
      ).toISOString(),
      hot: true,
      pulseScore: 20 - i / 2,
      status: "CONFIRMED",
      memberCount: 25,
      nodes,
      edges,
    };
  });
  return {
    data: { clusters },
    meta: {
      snapshotTs,
      source: "replay",
      dataMode: "mock",
      scoreVersion: "synthetic-v1",
      newWindowHours: 24,
      clusterCount: 20,
      nodeCount: 500,
      edgeCount: 1000,
      truncated: false,
    },
  };
}
