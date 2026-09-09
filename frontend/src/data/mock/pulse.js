import { pulseMaps, pulseSnapshots } from "./fixtures/pulse.js";
import { validateMap, validateSnapshots } from "../pulse/contract.js";
import { DataError } from "../contracts.js";
import { kstDate } from "../pulse/time.js";
export function listSnapshots(params = {}) {
  const data = pulseSnapshots.data.filter(
    (v) =>
      (!params.from || v.snapshotTs >= params.from) &&
      (!params.to || v.snapshotTs <= params.to) &&
      (!params.source || params.source === v.source),
  );
  return validateSnapshots(structuredClone({ data }));
}
export function getPulseMap(params = {}) {
  const candidates = pulseMaps.filter(
    (v) =>
      (!params.source || v.meta.source === params.source) &&
      (!params.snapshotTs || v.meta.snapshotTs === params.snapshotTs),
  );
  const found = candidates.at(-1);
  if (!found)
    throw new DataError("해당 시점의 스냅샷이 없습니다.", {
      status: 404,
      code: "SNAPSHOT_NOT_FOUND",
    });
  return validateMap(structuredClone(found), params);
}
export function historicalReport(id, catalog) {
  const map = pulseMaps.find((v) => v.data.clusters.some((c) => c.id === id));
  const cluster = map?.data.clusters.find((c) => c.id === id);
  const original = catalog.find((v) => v.id === cluster?.issueKey);
  if (!original || !id.includes("~")) return null;
  const at = Date.parse(map.meta.snapshotTs);
  const data = structuredClone(original);
  const edits = cluster.nodes.reduce(
    (sum, node) => sum + (node.editCount ?? 0),
    0,
  );
  const baseline = cluster.nodes.reduce(
    (sum, node) => sum + (node.editBaseline ?? 0),
    0,
  );
  return {
    data: {
      ...data,
      id,
      title: cluster.label,
      summary: cluster.summary,
      edits,
      baseline,
      editors: null,
      pulse: baseline ? Math.round((edits / baseline) * 10) / 10 : 0,
      pageviews: cluster.nodes.reduce(
        (sum, node) => sum + (node.views ?? 0),
        0,
      ),
      date: kstDate(map.meta.snapshotTs),
      startAt: cluster.firstDetectedAt,
      status: cluster.hot ? "rising" : "sustained",
      stockSymbols: [],
      articleIds: cluster.nodes.map((v) => v.pageId),
      chart: data.chart.filter(
        (v) => Date.parse(`${v.date}T23:59:59+09:00`) <= at,
      ),
      timeline: data.timeline.filter((v) => Date.parse(v.at || v.date) <= at),
      news: [],
      insights: [],
    },
    nodes: cluster.nodes,
    snapshotTs: map.meta.snapshotTs,
  };
}
