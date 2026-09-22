import { DataError } from "./contracts.js";

/** The API's omitted source means LIVE-first, not the union of both sources. */
export async function listExploreIssues(client, params = {}, options) {
  const { sourceSnapshots: pinned, ...query } = params;
  const offset = query.offset ?? 0;
  const limit = query.limit ?? 20;
  let sourceSnapshots =
    pinned ||
    (query.source && query.snapshotTs
      ? { [query.source]: query.snapshotTs }
      : undefined);
  if (!sourceSnapshots) {
    const snapshots = await client.listSnapshots(
      query.source ? { source: query.source } : {},
      options,
    );
    sourceSnapshots = {};
    for (const item of snapshots.data) {
      if (query.source && item.source !== query.source) continue;
      if (
        query.snapshotTs &&
        Date.parse(item.snapshotTs) !== Date.parse(query.snapshotTs)
      )
        continue;
      if (
        !sourceSnapshots[item.source] ||
        Date.parse(item.snapshotTs) > Date.parse(sourceSnapshots[item.source])
      )
        sourceSnapshots[item.source] = item.snapshotTs;
    }
  }
  const sources = Object.entries(sourceSnapshots);
  if (sources.length === 1) {
    const [source, snapshotTs] = sources[0];
    const result = await client.listIssues(
      { ...query, offset, limit, source, snapshotTs },
      options,
    );
    return { ...result, meta: { ...result.meta, sourceSnapshots } };
  }

  // Only the first offset+limit rows of either sorted source can enter this
  // combined page. Respect the API's 100-row cap; never load issue details.
  const pages = await Promise.all(
    sources.map(async ([source, snapshotTs]) => {
      const data = [];
      let total = 0;
      while (data.length < offset + limit) {
        const result = await client.listIssues(
          {
            ...query,
            source,
            snapshotTs,
            offset: data.length,
            limit: Math.min(100, offset + limit - data.length),
          },
          options,
        );
        total = result.meta.pagination.total;
        data.push(...result.data);
        if (!result.meta.pagination.hasMore) break;
        if (!result.data.length)
          throw new DataError("이슈 페이지 응답이 비어 있습니다.", {
            code: "INVALID_RESPONSE",
          });
      }
      return { data, total };
    }),
  );
  const total = pages.reduce((sum, page) => sum + page.total, 0);
  const data = pages
    .flatMap((page) => page.data)
    .sort((a, b) => b.pulseScore - a.pulseScore || Number(a.id) - Number(b.id))
    .slice(offset, offset + limit);
  return {
    data,
    meta: {
      sourceSnapshots,
      pagination: {
        offset,
        limit,
        total,
        hasMore: offset + data.length < total,
      },
    },
  };
}
