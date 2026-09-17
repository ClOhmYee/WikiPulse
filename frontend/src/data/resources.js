import { DataError } from "./contracts.js";
import { issueCategories } from "./categories.js";

const unique = (items) => [
  ...new Map(items.map((item) => [item.id ?? item.symbol, item])).values(),
];
const optionalNumber = (value) => (Number.isFinite(value) ? value : null);
const availableText = (value) =>
  typeof value === "string" && value.trim() ? value : null;
export function memberView(member, eventId) {
  const id = String(member.pageId);
  return {
    id,
    pageId: id,
    wiki: member.wiki,
    title: member.title,
    name: member.title,
    isSeed: member.isSeed,
    weight: member.weight,
    edits: optionalNumber(member.editCount),
    views: optionalNumber(member.views),
    pageviews: optionalNumber(member.views),
    editors: null,
    pulse: null,
    baseline: null,
    description: null,
    chart: [],
    changes: [],
    relatedIds: [],
    eventIds: [String(eventId)],
  };
}
const sumOptionalNumber = (values) => {
  const known = values.filter((v) => Number.isFinite(v));
  return known.length ? known.reduce((a, b) => a + b, 0) : null;
};

export function issueView(raw, aliases = []) {
  const members = raw.members || [];
  return {
    id: String(raw.id),
    aliases: [...new Set(aliases.map(String))],
    title: availableText(raw.label) || members[0]?.title || "제목 미제공",
    summary: availableText(raw.summary),
    summaryModel: raw.summaryModel ?? null,
    pulseScore: raw.pulseScore,
    status: raw.status,
    source: raw.source,
    snapshotTs: raw.snapshotTs,
    memberCount: raw.memberCount ?? (raw.members ? members.length : null),
    stockCount: raw.stockCount ?? null,
    articleIds: members.map((v) => String(v.pageId)),
    stockSymbols: (raw.relatedStocks || []).map((v) => v.ticker),
    members: members.map((v) => memberView(v, raw.id)),
    category: null,
    date: null,
    startAt: null,
    startedAt: null,
    updatedAt: null,
    pulse: null,
    // 문서별 editCount 합계. editorCount 는 API 계약에 아직 없어(-36 이후 후속) editors 는 null 유지.
    edits: sumOptionalNumber(members.map((m) => m.editCount)),
    editors: null,
    pageviews: null,
    baseline: null,
    chart: [],
    news: [],
    timeline: [],
    insights: [],
    keywords: [],
  };
}
export function stockView(raw, eventId) {
  const relation =
    eventId === undefined
      ? []
      : [
          {
            eventId: String(eventId),
            matchPath: raw.matchPath ?? null,
            tier: raw.tier ?? null,
            rationale: availableText(raw.rationale),
            similarity: optionalNumber(raw.similarity),
            gdeltLift: optionalNumber(raw.gdeltLift),
          },
        ];
  return {
    symbol: raw.ticker,
    name: raw.name,
    exchange: raw.exchange,
    market: raw.exchange,
    sector: raw.sector ?? null,
    description: availableText(raw.businessSummary),
    cik: raw.cik ?? null,
    issueCount: raw.issueCount ?? null,
    price: null,
    change: null,
    changePercent: null,
    currency: null,
    eventIds: eventId === undefined ? [] : [String(eventId)],
    relations: relation,
    chart: [],
    tier: raw.tier ?? null,
    matchPath: raw.matchPath ?? null,
    rationale: availableText(raw.rationale),
    similarity: optionalNumber(raw.similarity),
    gdeltLift: optionalNumber(raw.gdeltLift),
  };
}
async function optionalDetail(method, id, options) {
  try {
    return await method(id, options);
  } catch (error) {
    if (error.status === 404) return null;
    throw error;
  }
}
const listQuery = (params, allowed) =>
  Object.fromEntries(
    Object.entries(params || {}).filter(
      ([key, value]) =>
        allowed.includes(key) &&
        value !== undefined &&
        value !== null &&
        value !== "",
    ),
  );

/** Fetch one server page or the route's explicit detail endpoints. */
export async function loadPageData(client, resource, params = {}, options) {
  const snapshot = {
    categories: issueCategories,
    events: [],
    entities: [],
    stocks: [],
    meta: { dataMode: client.dataSource || "api" },
    pagination: null,
    collectionLimit: null,
    missingSavedEvents: [],
    missingSavedStocks: [],
  };
  function metadata(result) {
    if (!result) return;
    Object.assign(snapshot.meta, result.meta || {});
    snapshot.meta.dataMode = client.dataSource || "api";
    if (result.meta?.pagination) snapshot.pagination = result.meta.pagination;
  }
  async function issueCards(values) {
    return Promise.all(
      values.map(async (v) =>
        issueView(
          v,
          client.resolveIssueAlias
            ? [await client.resolveIssueAlias(v.id)]
            : [],
        ),
      ),
    );
  }
  async function addIssue(result, requestedId, saved = false) {
    if (!result) return null;
    const aliases = requestedId == null ? [] : [String(requestedId)];
    if (client.resolveIssueAlias)
      aliases.push(await client.resolveIssueAlias(result.data.id));
    const event = issueView(result.data, aliases);
    if (saved) event.savedId = String(requestedId);
    snapshot.events.push(event);
    if (!saved) {
      snapshot.entities.push(...event.members);
      snapshot.stocks.push(
        ...(result.data.relatedStocks || []).map((v) => stockView(v, event.id)),
      );
    }
    metadata(result);
    snapshot.meta.snapshotTs ||= event.snapshotTs;
    snapshot.meta.source ||= event.source;
    return event;
  }
  switch (resource) {
    case "explore": {
      const query = listQuery(params.listParams, [
        "offset",
        "limit",
        "snapshotTs",
        "status",
        "source",
      ]);
      if (query.source && !query.snapshotTs) {
        const snapshots = await client.listSnapshots(
          { source: query.source },
          options,
        );
        const latest = snapshots.data.reduce(
          (last, item) =>
            !last || Date.parse(item.snapshotTs) > Date.parse(last.snapshotTs)
              ? item
              : last,
          null,
        );
        if (!latest) {
          snapshot.pagination = {
            offset: query.offset || 0,
            limit: query.limit || 20,
            total: 0,
            hasMore: false,
          };
          snapshot.meta = {
            ...snapshot.meta,
            source: query.source,
            pagination: snapshot.pagination,
          };
          break;
        }
        query.snapshotTs = latest.snapshotTs;
      }
      const result = await client.listIssues(
        { offset: 0, limit: 20, ...query },
        options,
      );
      snapshot.events = await issueCards(result.data);
      metadata(result);
      break;
    }
    case "event":
      await addIssue(
        await optionalDetail(client.getIssue, params.id, options),
        params.id,
      );
      break;
    case "eventStocks": {
      const event = await addIssue(
        await optionalDetail(client.getIssue, params.id, options),
        params.id,
      );
      if (event) {
        const result = await client.listIssueStocks(
          event.id,
          { limit: 100 },
          options,
        );
        snapshot.stocks = result.data.map((v) => stockView(v, event.id));
        event.stockSymbols = snapshot.stocks.map((v) => v.symbol);
        snapshot.collectionLimit = 100;
        metadata(result);
      }
      break;
    }
    case "stocks": {
      const query = listQuery(params.listParams, [
        "offset",
        "limit",
        "q",
        "sector",
        "exchange",
        "hasIssues",
      ]);
      const result = await client.listStocks(
        { offset: 0, limit: 20, ...query },
        options,
      );
      snapshot.stocks = result.data.map((v) => stockView(v));
      metadata(result);
      break;
    }
    case "stock": {
      const result = await optionalDetail(client.getStock, params.id, options);
      if (result) {
        const related = await client.listStockIssues(params.id, options);
        snapshot.events = await issueCards(related.data);
        const value = stockView(result.data);
        value.eventIds = snapshot.events.map((v) => v.id);
        snapshot.stocks = [value];
        snapshot.collectionLimit = 50;
        metadata(result);
      }
      break;
    }
    case "saved": {
      const eventIds = [...new Set(params.savedEvents || [])];
      const tickers = [...new Set(params.savedStocks || [])];
      const [eventResults, stockResults] = await Promise.all([
        Promise.all(
          eventIds.map((id) => optionalDetail(client.getIssue, id, options)),
        ),
        Promise.all(
          tickers.map((id) => optionalDetail(client.getStock, id, options)),
        ),
      ]);
      for (let i = 0; i < eventResults.length; i++) {
        if (eventResults[i]) await addIssue(eventResults[i], eventIds[i], true);
        else snapshot.missingSavedEvents.push(String(eventIds[i]));
      }
      for (let i = 0; i < stockResults.length; i++) {
        if (stockResults[i])
          snapshot.stocks.push({
            ...stockView(stockResults[i].data),
            savedId: tickers[i],
          });
        else snapshot.missingSavedStocks.push(tickers[i]);
      }
      break;
    }
    default:
      throw new DataError("알 수 없는 데이터 화면입니다.");
  }
  snapshot.events = unique(snapshot.events);
  snapshot.entities = unique(snapshot.entities);
  snapshot.stocks = unique(snapshot.stocks);
  return snapshot;
}
