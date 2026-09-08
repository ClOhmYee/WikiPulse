import { DataError } from "./contracts.js";

const unique = (items) => [
  ...new Map(items.map((item) => [item.id ?? item.symbol, item])).values(),
];
export async function readAll(list, params, options) {
  let offset = 0;
  const data = [];
  const included = {};
  let meta;
  while (true) {
    options?.signal?.throwIfAborted();
    const result = await list({ ...params, offset, limit: 100 }, options);
    const page = result.meta.pagination;
    if (
      !page ||
      page.offset !== offset ||
      (page.hasMore && result.data.length === 0)
    ) {
      throw new DataError("목록의 페이지 정보를 확인할 수 없습니다.", {
        code: "INVALID_PAGINATION",
      });
    }
    if (
      meta &&
      (meta.asOf !== result.meta.asOf ||
        meta.dataMode !== result.meta.dataMode ||
        meta.pagination.total !== page.total)
    ) {
      throw new DataError(
        "목록이 조회 중 변경되었습니다. 다시 시도해 주세요.",
        { code: "INCONSISTENT_PAGINATION" },
      );
    }
    data.push(...result.data);
    for (const [key, values] of Object.entries(result.included || {}))
      included[key] = unique([...(included[key] || []), ...values]);
    meta = result.meta;
    offset += result.data.length;
    if (!page.hasMore) break;
    if (offset >= page.total)
      throw new DataError("목록의 페이지 정보가 일치하지 않습니다.", {
        code: "INVALID_PAGINATION",
      });
  }
  if (
    data.length !== meta.pagination.total ||
    unique(data).length !== data.length
  ) {
    throw new DataError(
      "전체 목록을 불러오지 못했습니다. 다시 시도해 주세요.",
      { code: "INVALID_PAGINATION" },
    );
  }
  const { pagination: _pagination, ...sourceMeta } = meta;
  return { data, included, meta: sourceMeta };
}

async function optionalDetail(method, id, options) {
  try {
    return await method(id, options);
  } catch (error) {
    if (error.status === 404) return null;
    throw error;
  }
}

/** Load only the data needed by a route. Views never receive partial loading data. */
export async function loadPageData(client, resource, params, options) {
  const snapshot = {
    categories: [],
    events: [],
    entities: [],
    stocks: [],
    meta: null,
  };
  function merge(result, kind) {
    if (!result) return;
    for (const [key, values] of Object.entries(result.included || {}))
      snapshot[key] = unique([...(snapshot[key] || []), ...values]);
    snapshot[kind] = unique([
      ...snapshot[kind],
      ...(Array.isArray(result.data) ? result.data : [result.data]),
    ]);
    if (kind !== "categories") snapshot.meta = result.meta;
  }
  const categoryTask = client.listCategories(options);
  const pageTask = (async () => {
    switch (resource) {
      case "explore":
        merge(await readAll(client.listEvents, {}, options), "events");
        break;
      case "event":
        merge(
          await optionalDetail(client.getEvent, params.id, options),
          "events",
        );
        break;
      case "entity":
        merge(
          await optionalDetail(client.getEntity, params.id, options),
          "entities",
        );
        break;
      case "stock":
        merge(
          await optionalDetail(client.getStock, params.id, options),
          "stocks",
        );
        break;
      case "stocks":
        merge(await readAll(client.listStocks, {}, options), "stocks");
        break;
      case "eventStocks": {
        const event = await optionalDetail(client.getEvent, params.id, options);
        if (event) {
          merge(event, "events");
          merge(
            await readAll(client.listStocks, { eventId: params.id }, options),
            "stocks",
          );
        }
        break;
      }
      case "saved": {
        const [eventResults, stockResults] = await Promise.all([
          Promise.all(
            (params.savedEvents || []).map((id) =>
              optionalDetail(client.getEvent, id, options),
            ),
          ),
          Promise.all(
            (params.savedStocks || []).map((id) =>
              optionalDetail(client.getStock, id, options),
            ),
          ),
        ]);
        // Only saved records belong in this view; related records are not saved entries.
        for (const result of eventResults)
          if (result) {
            snapshot.events.push(result.data);
            snapshot.meta = result.meta;
          }
        for (const result of stockResults)
          if (result) {
            snapshot.stocks.push(result.data);
            snapshot.meta = result.meta;
          }
        break;
      }
      default:
        throw new DataError("알 수 없는 데이터 화면입니다.");
    }
  })();
  const [categoryResult] = await Promise.all([categoryTask, pageTask]);
  merge(categoryResult, "categories");
  snapshot.meta ||= categoryResult.meta;
  return snapshot;
}
