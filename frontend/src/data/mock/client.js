import {
  categories,
  entities,
  events,
  stocks,
  DEMO_DATE,
  HISTORY_START,
} from "./fixtures/catalog.js";
import { resolveReport, articleAt } from "./fixtures/history.js";
import { DataError } from "../contracts.js";
import { listSnapshots, getPulseMap } from "./pulse.js";

const meta = {
  dataMode: "mock",
  asOf: DEMO_DATE,
  timezone: "Asia/Seoul",
  window: "24h",
  availableRange: { from: HISTORY_START, to: DEMO_DATE, interval: "day" },
};
const omit = (value, keys) =>
  Object.fromEntries(
    Object.entries(value).filter(([key]) => !keys.includes(key)),
  );
const eventSummary = (value) => omit(value, ["timeline", "news", "insights"]);
const entitySummary = (value) => omit(value, ["chart", "changes"]);
const stockSummary = (value) => omit(value, ["chart"]);
function stockForReport(stock, event) {
  const baseId = event.id.split("~")[0];
  return {
    ...stockSummary(stock),
    // This projection belongs to the selected report, not today's quote/history.
    price: event.date === DEMO_DATE ? stock.price : null,
    change: event.date === DEMO_DATE ? stock.change : null,
    eventIds: [event.id],
    relations: stock.relations
      .filter((r) => r.eventId === baseId)
      .map((r) => ({ ...r, eventId: event.id })),
  };
}
const match = (text, query = "") =>
  text.toLowerCase().includes(query.trim().toLowerCase());
const invalid = () => {
  throw new DataError("조회 조건을 확인해 주세요.", {
    status: 400,
    code: "INVALID_QUERY",
  });
};
function validate(params, allowed, enums = {}) {
  for (const key of Object.keys(params)) if (!allowed.includes(key)) invalid();
  if (
    params.q !== undefined &&
    (typeof params.q !== "string" || params.q.length > 200)
  )
    invalid();
  for (const [key, values] of Object.entries(enums))
    if (params[key] !== undefined && !values.includes(params[key])) invalid();
}
function envelope(data, included = {}, extra = {}) {
  // Clone to prevent a view accidentally changing future fixture responses.
  return structuredClone({ data, included, meta: { ...meta, ...extra } });
}
function paginate(values, params, includedFor, extra = {}) {
  const { offset = 0, limit = 50 } = params;
  if (
    !Number.isInteger(offset) ||
    offset < 0 ||
    !Number.isInteger(limit) ||
    limit < 1 ||
    limit > 100
  )
    invalid();
  const data = values.slice(offset, offset + limit);
  return envelope(data, includedFor(data), {
    ...extra,
    pagination: {
      offset,
      limit,
      total: values.length,
      hasMore: offset + data.length < values.length,
    },
  });
}
function find(values, id, key = "id") {
  const value = values.find((item) => item[key] === id);
  if (!value)
    throw new DataError("요청한 데이터를 찾을 수 없습니다.", {
      status: 404,
      code: "NOT_FOUND",
    });
  return value;
}
const referenced = (values, ids, project) =>
  values.filter((item) => ids.includes(item.id ?? item.symbol)).map(project);
const eventIncluded = (values) => ({
  entities: [...new Set(values.flatMap((item) => item.articleIds))].map(
    (id) => {
      const latest = values
        .filter((item) => item.articleIds.includes(id))
        .sort((a, b) => b.date.localeCompare(a.date))[0];
      return entitySummary(
        articleAt(
          id,
          latest.date,
          values
            .filter((item) => item.articleIds.includes(id))
            .map((item) => item.id),
        ),
      );
    },
  ),
});
const stockIncluded = (values) => ({
  events: referenced(
    events,
    values.flatMap((item) => item.eventIds),
    eventSummary,
  ),
});

const handlers = {
  listSnapshots,
  getPulseMap,
  listCategories: () => envelope(categories),
  listEvents(params = {}) {
    validate(params, ["q", "category", "window", "sort", "offset", "limit"], {
      category: ["all", ...categories.map((item) => item.id)],
      window: ["24h", "3d", "7d"],
      sort: ["pulse", "recent", "documents"],
    });
    const window = params.window || "24h";
    const values = events
      .filter(
        (event) =>
          match(
            `${event.title} ${event.summary} ${event.keywords.join(" ")}`,
            params.q,
          ) &&
          (!params.category ||
            params.category === "all" ||
            event.category === params.category),
      )
      .map((event) => {
        const value = eventSummary(event);
        if (window !== "24h") {
          const points = event.chart.slice(-(window === "3d" ? 3 : 7));
          for (const metric of ["edits", "baseline", "pageviews"])
            value[metric] = points.reduce(
              (sum, point) => sum + point[metric],
              0,
            );
          value.pulse = Math.round((value.edits / value.baseline) * 10) / 10;
        }
        return value;
      })
      .sort((a, b) =>
        params.sort === "recent"
          ? b.startAt.localeCompare(a.startAt)
          : params.sort === "documents"
            ? b.articleIds.length - a.articleIds.length
            : b.pulse - a.pulse,
      );
    return paginate(values, params, eventIncluded, { window });
  },
  getEvent(id) {
    const event = resolveReport(id);
    if (!event) find([], id);
    return envelope(
      event,
      {
        entities: event.articleIds.map((pageId) =>
          entitySummary(articleAt(pageId, event.date, [event.id])),
        ),
        stocks: stocks
          .filter((stock) => event.stockSymbols.includes(stock.symbol))
          .map((stock) => stockForReport(stock, event)),
      },
      { asOf: event.date, snapshotTs: event.updatedAt },
    );
  },
  listEntities(params = {}) {
    validate(params, ["q", "offset", "limit"]);
    return paginate(
      entities
        .filter((entity) => match(`${entity.name} ${entity.title}`, params.q))
        .map(entitySummary),
      params,
      () => ({}),
    );
  },
  getEntity(id) {
    const entity = find(entities, id);
    return envelope(entity, {
      entities: referenced(entities, entity.relatedIds, entitySummary),
      events: referenced(events, entity.eventIds, eventSummary),
    });
  },
  listStocks(params = {}) {
    validate(
      params,
      ["q", "sector", "eventId", "relationType", "sort", "offset", "limit"],
      {
        sort: ["events", "name"],
        relationType: ["all", "direct", "industry", "supply", "region"],
      },
    );
    if (params.sector !== undefined && typeof params.sector !== "string")
      invalid();
    if (params.relationType !== undefined && !params.eventId) invalid();
    const event = params.eventId ? resolveReport(params.eventId) : null;
    if (params.eventId && !event) find([], params.eventId);
    const values = stocks
      .filter(
        (stock) =>
          (!event ||
            stock.eventIds.includes(event.id) ||
            event.stockSymbols.includes(stock.symbol)) &&
          match(
            `${stock.symbol} ${stock.name} ${stock.sector} ${stock.description}`,
            params.q,
          ) &&
          (!params.sector ||
            params.sector === "all" ||
            stock.sector === params.sector) &&
          (!params.relationType ||
            params.relationType === "all" ||
            stockForReport(stock, event).relations.some(
              (relation) =>
                relation.eventId === params.eventId &&
                relation.type === params.relationType,
            )),
      )
      .map((stock) =>
        event ? stockForReport(stock, event) : stockSummary(stock),
      )
      .sort(
        (a, b) =>
          (params.sort === "name"
            ? 0
            : b.eventIds.length - a.eventIds.length) ||
          a.symbol.localeCompare(b.symbol),
      );
    return paginate(
      values,
      params,
      event ? () => ({ events: [eventSummary(event)] }) : stockIncluded,
      event ? { asOf: event.date } : {},
    );
  },
  getStock(symbol) {
    const stock = find(stocks, String(symbol).toUpperCase(), "symbol");
    const included = stockIncluded([stock]);
    included.events.sort((a, b) => b.date.localeCompare(a.date));
    return envelope(stock, included);
  },
  searchWorkspace(params = {}) {
    validate(params, ["q", "limit"]);
    const { q = "", limit = 7 } = params;
    if (!Number.isInteger(limit) || limit < 1 || limit > 7) invalid();
    const values = [
      ...events.map((item) => ({
        kind: "event",
        id: item.id,
        title: item.title,
        detail: "사건",
        words: item.keywords.join(" "),
      })),
      ...entities.map((item) => ({
        kind: "entity",
        id: item.id,
        title: item.name,
        detail: item.title,
        words: item.title,
      })),
      ...stocks.map((item) => ({
        kind: "stock",
        id: item.symbol,
        title: item.name,
        detail: item.symbol,
        words: item.symbol,
      })),
    ];
    return envelope(
      q.trim()
        ? values
            .filter((item) =>
              match(`${item.title} ${item.detail} ${item.words}`, q),
            )
            .slice(0, limit)
            .map((item) => omit(item, ["words"]))
        : [],
    );
  },
};

/** @type {import('../contracts.js').DataClient} */
export const mockClient = Object.fromEntries(
  Object.entries(handlers).map(([method, handler]) => [
    method,
    async (...args) => {
      const options = method === "listCategories" ? args[0] : args[1];
      options?.signal?.throwIfAborted();
      await Promise.resolve();
      options?.signal?.throwIfAborted();
      return handler(...args);
    },
  ]),
);
