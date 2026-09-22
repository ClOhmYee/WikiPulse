import assert from "node:assert/strict";
import { mockClient } from "../src/data/mock/client.js";
import { issueDetail } from "../src/data/api/adapters.js";
import { loadSchema } from "./contract-schema.mjs";

// Validates implemented wire DTOs and the optional frontend report extension
// separately. Report generation is not part of the implemented Spring contract.
const { spec, validate } = loadSchema("../docs/openapi.yaml");
const operations = Object.values(spec.paths).flatMap((path) =>
  Object.values(path).map((operation) => operation.operationId),
);
assert.deepEqual(
  [...operations].sort(),
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
  ].sort(),
);
for (const [path, item] of Object.entries(spec.paths)) {
  assert.deepEqual(
    Object.keys(item),
    ["get"],
    `${path}: only implemented GET routes belong here`,
  );
  for (const [, name] of path.matchAll(/\{([^}]+)\}/g)) {
    assert(
      item.get.parameters.some(
        (p) => p.in === "path" && p.name === name && p.required,
      ),
      `${path}: missing required path parameter`,
    );
  }
}
let checked = 0;
let frontendReportsChecked = 0;
const check = (schema, body) => {
  let wireBody = body;
  if (schema === "IssueDetailResponse" && "report" in body.data) {
    assert(issueDetail(body.data), "Invalid frontend report extension");
    frontendReportsChecked += 1;
    wireBody = structuredClone(body);
    delete wireBody.data.report;
  }
  validate(schema, wireBody);
  checked += 1;
  return body;
};
async function collect(method, schema) {
  const rows = [];
  let offset = 0;
  do {
    const response = check(
      schema,
      await mockClient[method]({ offset, limit: 20 }),
    );
    const p = response.meta.pagination;
    assert.equal(p.offset, offset);
    assert.equal(p.hasMore, p.offset + response.data.length < p.total);
    rows.push(...response.data);
    if (!p.hasMore) break;
    assert(response.data.length > 0, "A page with hasMore must advance");
    offset += response.data.length;
  } while (offset < 10000);
  return rows;
}
const issues = await collect("listIssues", "IssueListResponse");
check("IssueRankingsResponse", await mockClient.getIssueRankings());
for (const issue of issues) {
  const detail = check(
    "IssueDetailResponse",
    await mockClient.getIssue(String(issue.id)),
  );
  assert.equal(detail.data.id, issue.id);
  assert(detail.data.relatedStocks.length <= 5, "detail is a preview");
  check(
    "RelatedStocksResponse",
    await mockClient.listIssueStocks(String(issue.id), { limit: 100 }),
  );
}
const stocks = await collect("listStocks", "StockListResponse");
for (const stock of stocks) {
  check("StockDetailResponse", await mockClient.getStock(stock.ticker));
  check("StockIssuesResponse", await mockClient.listStockIssues(stock.ticker));
  // mock 은 가격을 지어내지 않는다 — 빈 배열이지만 봉투·항목 스키마는 지켜야 한다.
  check("StockPricesResponse", await mockClient.getStockPrices(stock.ticker));
}
if (stocks.length) {
  check(
    "StockPricesResponse",
    await mockClient.getStockPrices(stocks[0].ticker, {
      from: "2026-01-01",
      to: "2026-09-01",
    }),
  );
}
// mock 은 가격을 지어내지 않아 항목이 배열에 안 실린다. StockPrice 항목 스키마
// (필드명·nullable·required 6개·additionalProperties)를 대표 샘플로 능동 검증한다.
check("StockPrice", {
  tradeDate: "2026-09-05",
  open: 178.2,
  high: 181.0,
  low: 177.4,
  close: 180.6,
  volume: 41203300,
});
check("StockPrice", {
  tradeDate: "2026-09-05",
  open: null,
  high: null,
  low: null,
  close: 180.6,
  volume: null,
});
const snapshots = check("SnapshotResponse", await mockClient.listSnapshots());
if (snapshots.data.length) {
  const { snapshotTs, source } = snapshots.data[0];
  check("MapResponse", await mockClient.getPulseMap({ snapshotTs, source }));
}
check(
  "IssueListResponse",
  await mockClient.listIssues({ offset: 999999, limit: 20 }),
);
check(
  "StockListResponse",
  await mockClient.listStocks({ q: "no-such-ticker-xyz", limit: 20 }),
);
if (issues.length) {
  const omitted = structuredClone(
    await mockClient.getIssue(String(issues[0].id)),
  );
  for (const key of ["label", "summary", "summaryModel"])
    delete omitted.data[key];
  for (const member of omitted.data.members) {
    delete member.editCount;
    delete member.views;
    // ko 표시명은 선택 필드다(NON_NULL 직렬화로 빠진다). 빠져도 계약을 지켜야 한다.
    delete member.titleKo;
  }
  check("IssueDetailResponse", omitted);
}
check("Error", { error: { code: "NOT_FOUND", message: "issue not found" } });
console.log(
  JSON.stringify(
    {
      routes: operations.length,
      schemas: Object.keys(spec.components.schemas).length,
      responses: checked,
      frontendReportsChecked,
      issueCards: issues.length,
      stockCards: stocks.length,
      liveBackendCalled: false,
    },
    null,
    2,
  ),
);
