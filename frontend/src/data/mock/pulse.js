import { dates, snapshotAt, timestamp } from "./fixtures/history.js";
import { validateMap, validateSnapshots } from "../pulse/contract.js";
import { DataError } from "../contracts.js";
import { issueId, pageId } from "./identity.js";
const snapshotIndex = dates.map((date) => ({
  snapshotTs: timestamp(date),
  source: "replay",
  clusterCount: snapshotAt(date).meta.clusterCount,
}));
export function listSnapshots(params = {}) {
  return validateSnapshots({
    data: snapshotIndex
      .filter(
        (v) =>
          (!params.from ||
            Date.parse(v.snapshotTs) >= Date.parse(params.from)) &&
          (!params.to || Date.parse(v.snapshotTs) <= Date.parse(params.to)) &&
          (!params.source || params.source === v.source),
      )
      .map((v) => ({ ...v })),
  });
}
export function getPulseMap(params = {}) {
  const found = snapshotIndex.findLast(
    (v) =>
      (!params.source || v.source === params.source) &&
      (!params.snapshotTs ||
        Date.parse(v.snapshotTs) === Date.parse(params.snapshotTs)),
  );
  if (!found)
    throw new DataError("해당 시점의 스냅샷이 없습니다.", {
      status: 404,
      code: "NOT_FOUND",
    });
  const raw = structuredClone(snapshotAt(found.snapshotTs.slice(0, 10)));
  delete raw.meta.dataMode;
  raw.data.clusters = raw.data.clusters.map((cluster) => ({
    ...cluster,
    id: String(issueId(cluster.id)),
    nodes: cluster.nodes.map((node) => ({
      ...node,
      pageId: String(pageId(node.pageId)),
    })),
    edges: cluster.edges.map((edge, index) => ({
      ...edge,
      id: `${issueId(cluster.id)}:${index + 1}`,
      sourcePageId: String(pageId(edge.sourcePageId)),
      targetPageId: String(pageId(edge.targetPageId)),
    })),
  }));
  return validateMap(raw, params);
}
