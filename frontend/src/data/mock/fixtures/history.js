import sources from "./sources.json" with { type: "json" };
import { topics } from "./topics.js";
import { newsroomExamples } from "./newsroom.js";

export const HISTORY_START = "2025-09-01";
export const DEMO_DATE = "2026-09-10";
export const DEMO_NOTICE =
  "2025.09.01–2026.09.10 시연 데이터 · 실제 위키 문서와 현재 Nasdaq-100 목록을 사용하며, 급증·리포트·관계·가격은 합성 예시입니다.";
export const DAY = 86_400_000;
export const timestamp = (date) => `${date}T00:00:00.000Z`;
const dateOf = (value) => new Date(value).toISOString().slice(0, 10);
const shift = (date, days) => dateOf(Date.parse(timestamp(date)) + days * DAY);
export const dates = Array.from(
  {
    length:
      Math.round((Date.parse(DEMO_DATE) - Date.parse(HISTORY_START)) / DAY) + 1,
  },
  (_, i) => shift(HISTORY_START, i),
);
const dateIndices = new Map(dates.map((date, i) => [date, i]));
const chartDates = (date) => {
  const end = dateIndices.get(date) + 1;
  return dates.slice(Math.max(0, end - 24), end);
};
export const hash = (text) =>
  [...text].reduce((n, ch) => (n * 31 + ch.charCodeAt(0)) >>> 0, 17);
const round = (n) => Math.round(n * 10) / 10;
const legacyIds = {
  "Computer security": "cybersecurity",
  "Reusable launch vehicle": "reusable-launch-system",
};
const slug = (title) =>
  legacyIds[title] ||
  title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
const docs = new Map();
for (const topic of topics) {
  topic.articleIds = topic.documents.map((doc) => {
    const source = sources.articles[doc.title];
    if (!source) throw new Error(`Unverified Wikipedia title: ${doc.title}`);
    const id = slug(source.title);
    if (!docs.has(id))
      docs.set(id, {
        id,
        title: source.title,
        name: doc.name,
        category: topic.category,
        source,
      });
    return id;
  });
}
export const documents = [...docs.values()];
export const documentById = docs;
export const universe = sources.universe;
const universeSymbols = new Set(universe.stocks.map((s) => s.symbol));
for (const topic of topics)
  for (const symbol of topic.symbols) {
    if (!universeSymbols.has(symbol))
      throw new Error(`Outside Nasdaq-100 fixture universe: ${symbol}`);
  }

// Authored monthly episodes, not observations of historical events.
// ~YYYY-MM-DD pins a daily report; issueKey keeps the topic's map identity stable.
const months = [...new Set(dates.map((date) => date.slice(0, 7)))];
export const episodes = months.flatMap((month) =>
  topics.flatMap((topic, i) => {
    const start = `${month}-${String(1 + (i % 10)).padStart(2, "0")}`;
    if (start > DEMO_DATE) return [];
    const monthEnd = dateOf(
      Date.UTC(Number(month.slice(0, 4)), Number(month.slice(5, 7)), 0),
    );
    const end = [shift(start, 18 + (i % 10)), monthEnd, DEMO_DATE].sort()[0];
    return [
      {
        id:
          month === DEMO_DATE.slice(0, 7) ? topic.id : `${topic.id}--${month}`,
        topic,
        start,
        end,
      },
    ];
  }),
);
export const episodeById = new Map(episodes.map((item) => [item.id, item]));

// One deterministic article/day observation shared by all projections.
export function activity(id, date) {
  const doc = docs.get(id),
    seed = hash(`${doc.source.pageId}:${date}`);
  const baseline = 8 + (doc.source.pageId % 42);
  return {
    date,
    edits: Math.round(baseline * (1.5 + (seed % 108) / 10)),
    baseline,
    pageviews: 1800 + (seed % 240000),
  };
}
export function articleAt(id, date, eventIds = []) {
  const doc = docs.get(id),
    metrics = activity(id, date);
  const chart = chartDates(date)
    .filter((d) => timestamp(d) >= doc.source.firstRevisionAt)
    .map((d) => activity(id, d));
  return {
    id,
    title: doc.title,
    name: doc.name,
    category: doc.category,
    description: `${doc.name}에 관한 실제 Wikipedia 문서입니다. 아래 편집량과 변화 기록은 ${date} 시연용 합성 수치입니다.`,
    edits: metrics.edits,
    baseline: metrics.baseline,
    pageviews: metrics.pageviews,
    editors: Math.max(1, Math.round(metrics.edits * 0.41)),
    pulse: round(metrics.edits / metrics.baseline),
    eventIds,
    relatedIds: [],
    chart,
    changes: [],
  };
}
function aggregate(nodes) {
  const edits = nodes.reduce((sum, n) => sum + n.editCount, 0);
  const baseline = nodes.reduce((sum, n) => sum + n.editBaseline, 0);
  return {
    edits,
    baseline,
    pageviews: nodes.reduce((sum, n) => sum + n.views, 0),
    pulse: round(edits / baseline),
  };
}
export function clusterAt(episode, date) {
  if (!episode || date < episode.start || date > episode.end) return null;
  const snapshotTs = timestamp(date);
  const members = [...new Set(episode.topic.articleIds)].filter(
    (id) => docs.get(id).source.firstRevisionAt <= snapshotTs,
  );
  const nodes = members.map((pageId) => {
    const doc = docs.get(pageId),
      metric = activity(pageId, date),
      spikeScore = round(metric.edits / metric.baseline);
    return {
      pageId,
      wiki: "enwiki",
      title: doc.title,
      isSeed: spikeScore >= 4,
      editCount: metric.edits,
      editBaseline: metric.baseline,
      views: metric.pageviews,
      viewBaseline: Math.round(metric.pageviews / Math.max(1, spikeScore / 2)),
      spikeScore,
      sizeScore: Math.min(1, spikeScore / 12),
      completeness: "complete",
      windowStart: new Date(Date.parse(snapshotTs) - DAY).toISOString(),
      windowEnd: snapshotTs,
    };
  });
  if (nodes.length < 2 || !nodes.some((n) => n.isSeed)) return null;
  const priorMonth = dateOf(
    Date.parse(`${date.slice(0, 7)}-01T00:00:00Z`) - DAY,
  ).slice(0, 7);
  // Explicitly synthetic example topology; never claimed as measured evidence.
  const edges = nodes.slice(1).map((node, index) => ({
    id: `${episode.id}-edge-${index}`,
    sourcePageId: nodes[index].pageId,
    targetPageId: node.pageId,
    kind: "clickstream",
    directed: true,
    weight: 100 + (hash(`${episode.topic.id}:${index}:${date}`) % 9500),
    evidence: {
      label: "문서 관계·탐색량 합성 예시 (실측 아님)",
      month: priorMonth,
    },
  }));
  const totals = aggregate(nodes);
  return {
    id: date === episode.end ? episode.id : `${episode.id}~${date}`,
    issueKey: episode.topic.id,
    label: episode.topic.title,
    summary:
      newsroomExamples[episode.topic.id]?.summary ||
      `${date} 시연: ${nodes
        .slice(0, 3)
        .map((n) => docs.get(n.pageId).name)
        .join(
          "·",
        )} 등 ${nodes.length}개 문서의 합성 편집 신호를 ${episode.topic.focus} 주제로 묶었습니다.`,
    category: episode.topic.category,
    firstDetectedAt: timestamp(episode.start),
    hot: totals.pulse >= 6,
    pulseScore: totals.pulse,
    status: "CONFIRMED",
    memberCount: nodes.length,
    nodes,
    edges,
  };
}
export function reportAt(episode, date = episode?.end) {
  const cluster = clusterAt(episode, date);
  if (!cluster) return null;
  const metrics = aggregate(cluster.nodes),
    topic = episode.topic,
    reportTs = timestamp(date);
  const top = [...cluster.nodes].sort((a, b) => b.spikeScore - a.spikeScore)[0];
  const articleIds = cluster.nodes.map((n) => n.pageId);
  const chart = chartDates(date).map((d) => {
    const values = articleIds
      .filter((id) => docs.get(id).source.firstRevisionAt <= timestamp(d))
      .map((id) => activity(id, d));
    return {
      date: d,
      edits: values.reduce((s, v) => s + v.edits, 0),
      baseline: values.reduce((s, v) => s + v.baseline, 0),
      pageviews: values.reduce((s, v) => s + v.pageviews, 0),
    };
  });
  return {
    id: cluster.id,
    title: cluster.label,
    summary: cluster.summary,
    category: topic.category,
    status:
      metrics.pulse >= 8
        ? "rising"
        : metrics.pulse >= 5
          ? "sustained"
          : "cooling",
    startAt: cluster.firstDetectedAt,
    updatedAt: reportTs,
    date,
    ...metrics,
    editors: null,
    articleIds,
    stockSymbols: [...topic.symbols],
    keywords: [docs.get(articleIds[0]).name, topic.focus],
    chart,
    timeline: [
      {
        id: `${cluster.id}-signal`,
        time: cluster.firstDetectedAt,
        kind: "signal",
        title: "위키 문서 급증 신호 감지",
        body: `${topic.focus} 관련 문서의 합성 급증 신호로 이 에피소드를 시작합니다. 실제 사건 발생일을 의미하지 않습니다.`,
        entityId: articleIds[0],
      },
      {
        id: `${cluster.id}-cluster`,
        time: reportTs,
        kind: "context",
        title: `${articleIds.length}개 문서로 클러스터 구성`,
        body: `${docs.get(top.pageId).name} 문서가 기준선 대비 ${top.spikeScore}배로 가장 높은 편집 배수를 보이는 시연입니다.`,
        entityId: top.pageId,
      },
      {
        id: `${cluster.id}-report`,
        time: reportTs,
        kind: "context",
        title: "클러스터 리포트와 종목 연결",
        body: `${topic.focus} 맥락을 정리하고 현재 Nasdaq-100의 ${topic.symbols.join(", ")} 종목을 사업 영역으로 연결한 예시입니다.`,
        entityId: null,
      },
    ],
    news: articleIds.slice(0, 3).map((id, i) => ({
      id: `${cluster.id}-reference-${i}`,
      title: `${docs.get(id).name} 주제 참고 문서`,
      source: "Wikipedia · 배경 자료",
      publishedAt: reportTs,
      type: "analysis",
      url: docs.get(id).source.url,
      summary: `${topic.focus}을 이해하기 위한 실제 문서 링크입니다. 시각은 시연 리포트의 기준 시각이며 기사 발행일이나 실제 수정일이 아닙니다.`,
    })),
    report: {
      status: "ready",
      generatedAt: reportTs,
      model: "mock-authored",
      sections: [
        {
          id: "article",
          title: cluster.label,
          body: [
            ...(newsroomExamples[topic.id]?.paragraphs || [
              `${topic.focus} 주제를 따라 ${cluster.nodes
                .slice(0, 3)
                .map((node) => docs.get(node.pageId).name)
                .join(
                  ", ",
                )} 문서를 함께 읽습니다. 서로 다른 문서에서 출발한 관심을 연결해 하나의 주제가 어떤 기술과 산업으로 이어지는지 살펴보는 시연입니다.`,
              `연결된 ${topic.symbols.join(", ")} 종목은 기업의 사업 영역을 더 살펴볼 수 있는 후보입니다. 같은 문서 묶음에 포함되었다는 이유로 개별 기업의 실적이나 주가 영향을 판단하지 않습니다.`,
            ]),
            `${date} 기준 시연 화면에는 ${articleIds.length}개 문서가 포함되어 있습니다. 합성 편집량은 ${metrics.edits.toLocaleString("ko-KR")}회로, 기준량 ${metrics.baseline.toLocaleString("ko-KR")}회와 함께 문서 활동을 비교하는 예시로 표시됩니다. 이 수치와 문서 연결은 실제 사건 관측이나 자동 분석 결과가 아닙니다.`,
          ].join("\n\n"),
          evidenceIds: articleIds,
        },
      ],
    },
    insights: [
      {
        title: "급증 문서에서 클러스터로",
        body: `${articleIds.length}개 문서의 합성 편집량 ${metrics.edits.toLocaleString("ko-KR")}회와 기준량 ${metrics.baseline}회를 합산했습니다. 클러스터 전체 편집 배수는 ${metrics.pulse}배입니다.`,
      },
      {
        title: `${topic.focus}의 맥락`,
        body: `${cluster.nodes.map((n) => docs.get(n.pageId).name).join(" → ")} 문서를 함께 읽는 주제 묶음입니다. 자동 클러스터링의 실측 결과가 아니라 사람이 구성한 시나리오입니다.`,
      },
      {
        title: "리포트에서 기업의 사업으로",
        body: `위 주제를 ${topic.symbols.join(", ")}의 사업 영역과 연결합니다. 후보와 연결 근거는 시연용 가설이며 실제 뉴스 동시 출현·LLM 검증 결과가 아닙니다.`,
      },
    ],
  };
}
export function resolveReport(id) {
  const [episodeId, date, extra] = id.split("~"),
    episode = episodeById.get(episodeId);
  if (
    !episode ||
    extra !== undefined ||
    (date !== undefined && !dates.includes(date))
  )
    return null;
  const report = reportAt(episode, date || episode.end);
  return report?.id === id ? report : null;
}
export function snapshotAt(date) {
  const clusters = episodes
    .filter((e) => e.start <= date && date <= e.end)
    .map((e) => clusterAt(e, date))
    .filter(Boolean);
  return {
    data: { clusters },
    meta: {
      snapshotTs: timestamp(date),
      source: "replay",
      dataMode: "mock",
      scoreVersion: "synthetic-article-day-v2",
      newWindowHours: 24,
      clusterCount: clusters.length,
      nodeCount: clusters.reduce((s, c) => s + c.nodes.length, 0),
      edgeCount: clusters.reduce((s, c) => s + c.edges.length, 0),
      truncated: false,
    },
  };
}
