import { stocks } from "./fixtures/catalog.js";
import {
  DEMO_DATE,
  resolveReport,
  snapshotAt,
  timestamp,
  dates,
  episodeById,
} from "./fixtures/history.js";
import { DataError } from "../contracts.js";
import { listSnapshots, getPulseMap } from "./pulse.js";
import { issueId, legacyIssueId, pageId } from "./identity.js";

const fail = (status, code) => {
  throw new DataError(
    status === 404
      ? "요청한 데이터를 찾을 수 없습니다."
      : "조회 조건을 확인해 주세요.",
    { status, code },
  );
};
const invalid = () => fail(400, "INVALID_QUERY");
const envelope = (data, meta) =>
  structuredClone(meta ? { data, meta } : { data });
function query(params, allowed) {
  for (const key of Object.keys(params)) if (!allowed.includes(key)) invalid();
  if (
    params.source !== undefined &&
    !["live", "replay"].includes(params.source)
  )
    invalid();
  for (const key of ["snapshotTs", "from", "to"])
    if (
      params[key] !== undefined &&
      (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(
        params[key],
      ) ||
        !Number.isFinite(Date.parse(params[key])))
    )
      invalid();
}
function bounds(params) {
  const { offset = 0, limit = 50 } = params;
  if (
    !Number.isInteger(offset) ||
    offset < 0 ||
    !Number.isInteger(limit) ||
    limit < 1 ||
    limit > 100
  )
    invalid();
  return { offset, limit };
}
function paginate(values, params, extra = {}) {
  const { offset, limit } = bounds(params);
  const data = values.slice(offset, offset + limit);
  return envelope(data, {
    ...extra,
    pagination: {
      offset,
      limit,
      total: values.length,
      hasMore: offset + data.length < values.length,
    },
  });
}
function report(id) {
  const value = resolveReport(legacyIssueId(id));
  if (!value) fail(404, "NOT_FOUND");
  return value;
}
function stock(ticker) {
  const value = stocks.find((v) => v.symbol === String(ticker).toUpperCase());
  if (!value) fail(404, "NOT_FOUND");
  return value;
}
function related(reportValue) {
  return reportValue.stockSymbols
    .map((ticker) => {
      const value = stock(ticker);
      const relation = value.relations.find(
        (v) => v.eventId === reportValue.id.split("~")[0],
      );
      return {
        ticker,
        name: value.name,
        exchange: value.market,
        sector: value.sector,
        tier: "EMBEDDING_ONLY",
        matchPath: "PRODUCT_INDUSTRY",
        rationale:
          relation?.explanation ||
          "시연용 문서·사업 영역 연결 예시입니다. 실제 LLM 검증 결과가 아닙니다.",
      };
    })
    .sort((a, b) => a.ticker.localeCompare(b.ticker));
}
function card(cluster, snapshotTs) {
  return {
    id: issueId(cluster.id),
    label: cluster.label,
    pulseScore: cluster.pulseScore,
    status: cluster.status,
    source: "replay",
    snapshotTs,
    memberCount: cluster.memberCount,
    stockCount: episodeById.get(cluster.id.split("~")[0]).topic.symbols.length,
  };
}
let stockIssueIndex;
function issuesForTicker(ticker) {
  if (!stockIssueIndex) {
    stockIssueIndex = new Map(stocks.map((value) => [value.symbol, []]));
    for (const date of dates) {
      for (const cluster of snapshotAt(date).data.clusters) {
        const value = card(cluster, timestamp(date));
        for (const symbol of episodeById.get(cluster.id.split("~")[0]).topic
          .symbols)
          stockIssueIndex.get(symbol).push(value);
      }
    }
    for (const values of stockIssueIndex.values())
      values.sort(
        (a, b) =>
          b.snapshotTs.localeCompare(a.snapshotTs) ||
          b.pulseScore - a.pulseScore,
      );
  }
  return stockIssueIndex.get(ticker) || [];
}
function stockCard(value) {
  return {
    ticker: value.symbol,
    name: value.name,
    exchange: value.market,
    sector: value.sector,
    issueCount: issuesForTicker(value.symbol).length,
  };
}
const handlers = {
  listSnapshots(params = {}) {
    query(params, ["from", "to", "source"]);
    return listSnapshots(params);
  },
  getPulseMap(params = {}) {
    query(params, ["snapshotTs", "source"]);
    return getPulseMap(params);
  },
  listIssues(params = {}) {
    query(params, ["snapshotTs", "status", "source", "offset", "limit"]);
    bounds(params);
    const statuses = params.status
      ? params.status.split(",")
      : ["DETECTED", "VERIFYING", "CONFIRMED"];
    if (
      statuses.some(
        (s) => !["DETECTED", "VERIFYING", "CONFIRMED", "DISCARDED"].includes(s),
      )
    )
      invalid();
    const snapshotTs = params.snapshotTs
      ? new Date(params.snapshotTs).toISOString()
      : timestamp(DEMO_DATE);
    const snapshots = listSnapshots().data;
    const found = snapshots.find(
      (v) =>
        v.snapshotTs === snapshotTs &&
        (!params.source || v.source === params.source),
    );
    const values = found
      ? snapshotAt(snapshotTs.slice(0, 10))
          .data.clusters.filter((v) => statuses.includes(v.status))
          .map((v) => card(v, snapshotTs))
      : [];
    values.sort((a, b) => b.pulseScore - a.pulseScore || a.id - b.id);
    return paginate(values, params, { snapshotTs });
  },
  getIssue(id) {
    const value = report(id);
    const snapshot = snapshotAt(value.date);
    const cluster = snapshot.data.clusters.find((v) => v.id === value.id);
    if (!cluster) fail(404, "NOT_FOUND");
    return envelope({
      id: issueId(value.id),
      label: cluster.label,
      pulseScore: cluster.pulseScore,
      status: cluster.status,
      source: "replay",
      snapshotTs: snapshot.meta.snapshotTs,
      summary: value.summary,
      summaryModel: "mock-authored",
      members: cluster.nodes
        .map((node, index) => ({
          pageId: pageId(node.pageId),
          wiki: node.wiki,
          title: node.title,
          weight: 1 / (index + 1),
          isSeed: node.isSeed,
          editCount: node.editCount,
          views: node.views,
          completeness: node.completeness,
        }))
        .sort(
          (a, b) => Number(b.isSeed) - Number(a.isSeed) || b.weight - a.weight,
        ),
      relatedStocks: related(value).slice(0, 5),
    });
  },
  listIssueStocks(id, params = {}) {
    query(params, ["limit"]);
    const { limit } = bounds(params);
    return envelope(related(report(id)).slice(0, limit));
  },
  listStocks(params = {}) {
    query(params, ["q", "sector", "exchange", "hasIssues", "offset", "limit"]);
    if (params.q !== undefined && typeof params.q !== "string") invalid();
    if (params.hasIssues !== undefined && typeof params.hasIssues !== "boolean")
      invalid();
    const q = (params.q || "").trim().toLowerCase();
    const values = stocks
      .filter(
        (v) =>
          (!q || `${v.name} ${v.symbol}`.toLowerCase().includes(q)) &&
          (!params.sector || v.sector === params.sector) &&
          (!params.exchange || v.market === params.exchange) &&
          (!params.hasIssues || issuesForTicker(v.symbol).length > 0),
      )
      .map(stockCard)
      .sort((a, b) => a.ticker.localeCompare(b.ticker));
    return paginate(values, params);
  },
  getStock(ticker) {
    const value = stock(ticker);
    return envelope({
      ticker: value.symbol,
      name: value.name,
      exchange: value.market,
      sector: value.sector,
      businessSummary: value.description,
    });
  },
  listStockIssues(ticker) {
    const value = stock(ticker);
    const values = issuesForTicker(value.symbol).slice(0, 50);
    return envelope(values);
  },
  getStockPrices(ticker, params = {}) {
    stock(ticker); // 없는 티커는 404 (API 계약과 동일)
    for (const key of Object.keys(params))
      if (!["from", "to"].includes(key)) invalid();
    // 형식(YYYY-MM-DD) + 달력 유효성. 백엔드 LocalDate.parse 와 같은 400 경로.
    for (const key of ["from", "to"])
      if (
        params[key] !== undefined &&
        (!/^\d{4}-\d{2}-\d{2}$/.test(params[key]) ||
          !Number.isFinite(Date.parse(params[key])))
      )
        invalid();
    // from > to 는 백엔드처럼 400.
    if (params.from && params.to && params.from > params.to) invalid();
    // mock 은 가격을 지어내지 않는다(UI_GUIDE) — 항상 빈 구간 → FE 는 empty 상태.
    return envelope([]);
  },
};

/** Mock and API clients expose the same eight raw Spring DTO response shapes. */
export const mockClient = {
  dataSource: "mock",
  resolveIssueAlias: legacyIssueId,
  ...Object.fromEntries(
    Object.entries(handlers).map(([method, handler]) => [
      method,
      async (...args) => {
        const options = ["listIssueStocks", "getStockPrices"].includes(method)
          ? args[2]
          : args[1];
        options?.signal?.throwIfAborted();
        await Promise.resolve();
        options?.signal?.throwIfAborted();
        return handler(...args);
      },
    ]),
  ),
};
