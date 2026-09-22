import { readDataConfig } from "./config.js";
import { clusterTitle, documentTitle } from "./titles.js";

// App presentation metadata is never a required server response field.
export function presentPulseMap(result, dataMode, aliasFor) {
  return {
    ...result,
    meta: { ...result.meta, dataMode },
    data: {
      clusters: result.data.clusters.map((cluster) => ({
        ...cluster,
        aliases: aliasFor ? [aliasFor(cluster.id)] : [],
        // 서버가 준 title/titleKo 는 그대로 두고 표시용만 덧붙인다 — 위키 링크는 title 을
        // 쓰고 검색 색인은 둘 다 본다.
        nodes: cluster.nodes.map((node) => ({
          ...node,
          displayTitle: documentTitle(node),
        })),
        label: clusterTitle(cluster),
        issueKey:
          cluster.issueKey ||
          `${result.meta.source}:${result.meta.snapshotTs}:${cluster.id}`,
      })),
    },
  };
}
export function createDataClient(env = {}) {
  let clientPromise;
  function getClient() {
    if (!clientPromise)
      clientPromise = Promise.resolve().then(async () => {
        const config = readDataConfig(env);
        return config.source === "mock"
          ? (await import("./mock/client.js")).mockClient
          : (await import("./api/client.js")).createApiClient(config.baseURL);
      });
    return clientPromise;
  }
  return {
    dataSource: env.VITE_DATA_SOURCE ?? "mock",
    resolveIssueAlias: async (id) =>
      (await getClient()).resolveIssueAlias?.(id) || String(id),
    ...Object.fromEntries(
      [
        "listIssues",
        "getIssueRankings",
        "getIssue",
        "listIssueStocks",
        "listStocks",
        "getStock",
        "listStockIssues",
        "getStockPrices",
        "listSnapshots",
        "getPulseMap",
      ].map((method) => [
        method,
        async (...args) => {
          const client = await getClient();
          const result = await client[method](...args);
          return method === "getPulseMap"
            ? presentPulseMap(
                result,
                client.dataSource,
                client.resolveIssueAlias,
              )
            : result;
        },
      ]),
    ),
  };
}
/** @type {import('./contracts.js').DataClient} */
export const dataClient = createDataClient(import.meta.env);
