/** 빌드 플래그와 실제 API 모드가 모두 맞을 때만 새 화면을 연다. */
export const issueHistoryEnabled = (env = {}, dataSource) =>
  env.VITE_ISSUE_HISTORY_ENABLED === "true" && dataSource === "api";

/** 리포트 이력을 끝까지 읽어 달력 날짜가 페이지 경계에서 누락되지 않게 한다. */
export async function allIssueHistoryReports(client, id, { signal } = {}) {
  const reports = [];
  let offset = 0;
  let hasMore = true;
  while (hasMore) {
    const response = await client.listIssueHistoryReports(
      id,
      { offset, limit: 100 },
      { signal },
    );
    reports.push(...response.data);
    hasMore = response.meta.pagination.hasMore;
    offset += response.data.length;
  }
  return reports;
}
