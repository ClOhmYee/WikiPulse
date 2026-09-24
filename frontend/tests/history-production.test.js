import test from "node:test";
import assert from "node:assert/strict";
import { createApiClient } from "../src/data/api/client.js";
import {
  allIssueHistoryReports,
  issueHistoryEnabled,
} from "../src/data/historyProduction.js";

const pagination = { offset: 0, limit: 20, total: 1, hasMore: false };
const group = {
  id: 42,
  label: "The Odyssey (2026 film)",
  source: "replay",
  status: "CONFIRMED",
  pulseScore: 12,
  snapshotTs: "2026-07-18T01:00:00Z",
  firstSeen: "2026-07-17T01:00:00Z",
  occurrenceCount: 10,
  defaultReportId: 41,
  summary: "요약",
  memberCount: 3,
  stockCount: 1,
};

test("새 이슈 탐색은 명시적으로 켠 API 빌드에서만 동작한다", () => {
  assert.equal(issueHistoryEnabled({}, "api"), false);
  assert.equal(
    issueHistoryEnabled({ VITE_ISSUE_HISTORY_ENABLED: "true" }, "mock"),
    false,
  );
  assert.equal(
    issueHistoryEnabled({ VITE_ISSUE_HISTORY_ENABLED: "false" }, "api"),
    false,
  );
  assert.equal(
    issueHistoryEnabled({ VITE_ISSUE_HISTORY_ENABLED: "true" }, "api"),
    true,
  );
});

test("대표 문서 API는 검색어를 서버에 보내고 페이지 계약을 검증한다", async () => {
  let url;
  const client = createApiClient("/api/v1", async (next) => {
    url = next;
    return Response.json({ data: [group], meta: { pagination } });
  });
  const result = await client.listIssueHistoryGroups({
    q: "Odyssey",
    offset: 0,
    limit: 20,
  });
  assert.equal(
    url,
    "/api/v1/issues/history/groups?q=Odyssey&offset=0&limit=20",
  );
  assert.equal(result.data[0].defaultReportId, 41);
  assert.equal(result.meta.pagination.total, 1);
  await assert.rejects(
    createApiClient("/api/v1", async () =>
      Response.json({
        data: [{ ...group, occurrenceCount: -1 }],
        meta: { pagination },
      }),
    ).listIssueHistoryGroups(),
    { code: "INVALID_RESPONSE" },
  );
});

test("리포트 시점 API는 해당 ID만 인코딩하고 리포트 시각을 검증한다", async () => {
  let url;
  const client = createApiClient("/api/v1", async (next) => {
    url = next;
    return Response.json({
      data: [
        {
          id: 41,
          snapshotTs: "2026-07-17T01:00:00Z",
          status: "CONFIRMED",
          pulseScore: 11,
        },
      ],
      meta: { pagination: { offset: 0, limit: 100, total: 1, hasMore: false } },
    });
  });
  const result = await client.listIssueHistoryReports("a/b", {
    offset: 0,
    limit: 100,
  });
  assert.equal(url, "/api/v1/issues/a%2Fb/history/reports?offset=0&limit=100");
  assert.equal(result.data[0].id, 41);
});

test("달력은 리포트 이력의 모든 서버 페이지를 읽는다", async () => {
  const offsets = [];
  const result = await allIssueHistoryReports(
    {
      listIssueHistoryReports: async (_id, params) => {
        offsets.push(params.offset);
        return {
          data: [{ id: params.offset + 1 }],
          meta: { pagination: { hasMore: params.offset === 0 } },
        };
      },
    },
    42,
  );
  assert.deepEqual(offsets, [0, 1]);
  assert.deepEqual(
    result.map((row) => row.id),
    [1, 2],
  );
});
