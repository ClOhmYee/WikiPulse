import { DataError } from "../contracts.js";
import { issueCategories } from "../categories.js";
const id = (v) => typeof v === "string" && v.length > 0;
const time = (v) =>
  typeof v === "string" && /Z$/.test(v) && Number.isFinite(Date.parse(v));
const number = (v) => Number.isFinite(v) && v >= 0;
const nullable = (fn, v) => v === null || fn(v);
const count = (v) => Number.isInteger(v) && v >= 0;
const source = (v) => ["live", "replay"].includes(v);
function requireContract(ok, field) {
  if (!ok)
    throw new DataError(`펄스맵 데이터 형식을 확인해 주세요 (${field}).`, {
      code: "INVALID_PULSE_RESPONSE",
    });
}
function unique(values, field) {
  requireContract(new Set(values).size === values.length, field);
}
export function validateSnapshots(body) {
  requireContract(body && Array.isArray(body.data), "snapshots");
  for (const item of body.data)
    requireContract(
      time(item.snapshotTs) && source(item.source) && count(item.clusterCount),
      "snapshot",
    );
  unique(
    body.data.map((v) => `${v.source}:${v.snapshotTs}`),
    "snapshot identity",
  );
  return {
    ...body,
    data: [...body.data].sort(
      (a, b) =>
        a.snapshotTs.localeCompare(b.snapshotTs) ||
        a.source.localeCompare(b.source),
    ),
  };
}
export function validateMap(body, requested = {}) {
  requireContract(
    body && body.data && Array.isArray(body.data.clusters) && body.meta,
    "map",
  );
  const {
    meta,
    data: { clusters },
  } = body;
  requireContract(
    time(meta.snapshotTs) &&
      source(meta.source) &&
      id(meta.scoreVersion) &&
      number(meta.newWindowHours) &&
      meta.newWindowHours > 0 &&
      typeof meta.truncated === "boolean",
    "meta",
  );
  requireContract(
    !requested.snapshotTs || meta.snapshotTs === requested.snapshotTs,
    "snapshotTs mismatch",
  );
  requireContract(
    !requested.source || meta.source === requested.source,
    "source mismatch",
  );
  unique(
    clusters.map((v) => v.id),
    "cluster id",
  );
  unique(
    clusters.map((v) => v.issueKey),
    "issueKey",
  );
  let nodes = 0,
    edges = 0;
  for (const cluster of clusters) {
    requireContract(
      id(cluster.id) &&
        id(cluster.issueKey) &&
        id(cluster.label) &&
        nullable(id, cluster.summary) &&
        typeof cluster.hot === "boolean" &&
        number(cluster.pulseScore) &&
        nullable(time, cluster.firstDetectedAt),
      "cluster",
    );
    requireContract(
      issueCategories.some((v) => v.id === cluster.category) &&
        ["DETECTED", "VERIFYING", "CONFIRMED"].includes(cluster.status),
      "category/status",
    );
    requireContract(
      !cluster.firstDetectedAt ||
        Date.parse(cluster.firstDetectedAt) <= Date.parse(meta.snapshotTs),
      "firstDetectedAt",
    );
    requireContract(
      Array.isArray(cluster.nodes) &&
        Array.isArray(cluster.edges) &&
        cluster.memberCount === cluster.nodes.length,
      "members",
    );
    unique(
      cluster.nodes.map((v) => v.pageId),
      "pageId",
    );
    const pageIds = new Set(cluster.nodes.map((v) => v.pageId));
    for (const node of cluster.nodes) {
      requireContract(
        id(node.pageId) &&
          id(node.title) &&
          /^[a-z-]+wiki$/.test(node.wiki) &&
          typeof node.isSeed === "boolean",
        "node",
      );
      requireContract(
        nullable((v) => number(v) && v <= 1, node.sizeScore) &&
          nullable(number, node.spikeScore),
        "score",
      );
      requireContract(
        ["complete", "pending", "unavailable"].includes(node.completeness),
        "completeness",
      );
      for (const field of [
        "editCount",
        "views",
        "editBaseline",
        "viewBaseline",
      ])
        requireContract(nullable(number, node[field]), field);
      requireContract(
        time(node.windowStart) &&
          time(node.windowEnd) &&
          Date.parse(node.windowStart) < Date.parse(node.windowEnd) &&
          Date.parse(node.windowEnd) <= Date.parse(meta.snapshotTs),
        "metric window",
      );
    }
    const signatures = [];
    unique(
      cluster.edges.map((v) => v.id),
      "edge id",
    );
    for (const edge of cluster.edges) {
      requireContract(
        id(edge.id) &&
          pageIds.has(edge.sourcePageId) &&
          pageIds.has(edge.targetPageId) &&
          edge.sourcePageId !== edge.targetPageId &&
          typeof edge.directed === "boolean" &&
          number(edge.weight),
        "edge endpoints",
      );
      requireContract(
        ["clickstream", "wikidata"].includes(edge.kind) &&
          id(edge.evidence?.label),
        "edge evidence",
      );
      if (edge.kind === "clickstream")
        requireContract(
          /^\d{4}-(0[1-9]|1[0-2])$/.test(edge.evidence.month) &&
            edge.evidence.month < meta.snapshotTs.slice(0, 7),
          "clickstream month",
        );
      else
        requireContract(
          time(edge.evidence.observedAt) &&
            Date.parse(edge.evidence.observedAt) <= Date.parse(meta.snapshotTs),
          "wikidata observedAt",
        );
      const pair = [edge.sourcePageId, edge.targetPageId];
      if (!edge.directed) pair.sort();
      signatures.push(JSON.stringify([edge.kind, edge.directed, ...pair]));
    }
    unique(signatures, "duplicate edge");
    nodes += cluster.nodes.length;
    edges += cluster.edges.length;
  }
  for (const [field, actual] of [
    ["clusterCount", clusters.length],
    ["nodeCount", nodes],
    ["edgeCount", edges],
  ])
    requireContract(
      count(meta[field]) &&
        (meta.truncated ? meta[field] >= actual : meta[field] === actual),
      field,
    );
  return {
    ...body,
    data: {
      clusters: [...clusters].sort(
        (a, b) => b.pulseScore - a.pulseScore || a.id.localeCompare(b.id),
      ),
    },
  };
}
