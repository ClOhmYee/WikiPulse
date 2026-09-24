import { test, expect } from "@playwright/test";

const metadata = [
  {
    id: 1,
    source: "replay",
    issue_key: "replay:enwiki:The Odyssey (2026 film)",
    label: "The Odyssey (2026 film)",
    snapshot_ts: "2026-07-17T01:00:00+00:00",
    status: "CONFIRMED",
    pulse_score: 10.1,
  },
  {
    id: 2,
    source: "replay",
    issue_key: "replay:enwiki:The Odyssey (2026 film)",
    label: "The Odyssey (2026 film)",
    snapshot_ts: "2026-07-18T01:00:00+00:00",
    status: "DETECTED",
    pulse_score: 9.2,
  },
  {
    id: 3,
    source: "replay",
    issue_key: "replay:enwiki:The Odyssey (1997 miniseries)",
    label: "The Odyssey (1997 miniseries)",
    snapshot_ts: "2026-07-18T02:00:00+00:00",
    status: "DETECTED",
    pulse_score: 8.1,
  },
];
const details = [
  {
    ...metadata[0],
    members: [
      { pageId: 11, title: "A", editCount: 6 },
      { pageId: 12, title: "B", editCount: 3 },
    ],
    summary: "첫날 요약",
    stocks: [{ ticker: "AAA", name: "첫날 종목", rationale: "연결 근거" }],
  },
];
const reports = [
  {
    id: 1,
    summary: "첫날 요약",
    sections: [{ id: "overview", body: "첫날 DB 본문", evidenceIds: ["11"] }],
    model: "테스트 모델",
    generated_at: "2026-07-17T03:00:00+00:00",
  },
];

test("운영 이슈 탐색 형식의 대표 문서 목록에서 달력과 날짜별 DB 리포트를 탐색한다", async ({
  page,
}) => {
  for (const [name, rows] of Object.entries({ metadata, details, reports })) {
    await page.route(
      `**/__local_issue_history_preview/${name}.jsonl`,
      (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/x-ndjson",
          body: rows.map(JSON.stringify).join("\n"),
        }),
    );
  }
  await page.goto("/#/issue-history-preview");
  await expect(page.getByRole("heading", { name: "이슈 탐색" })).toBeVisible();
  await expect(
    page
      .getByRole("navigation", { name: "주 메뉴" })
      .getByRole("link", { name: "이슈 탐색" }),
  ).toHaveAttribute("aria-current", "page");
  await expect(page.locator(".explore-layout .event-row")).toHaveCount(2);
  await page
    .getByRole("searchbox", { name: "사건 검색" })
    .fill("The Odyssey (2026 film)");
  await expect(page.locator(".explore-layout .event-row")).toHaveCount(1);
  await expect(page.locator(".event-row")).toContainText("2개 기록");
  await page.locator(".event-row").dblclick();
  await expect(
    page.getByRole("heading", { name: "The Odyssey (2026 film)" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "날짜별 기록" }),
  ).toBeVisible();
  await expect(page.getByTestId("calendar-day-2026-07-17")).toBeEnabled();
  await expect(page.getByTestId("calendar-day-2026-07-18")).toBeDisabled();
  await expect(page.getByTestId("calendar-day-2026-07-19")).toBeDisabled();
  await expect(page.getByText("첫날 DB 본문")).toBeVisible();
  await expect(page.getByText("AAA", { exact: true })).toBeVisible();
  await page.getByTestId("calendar-day-2026-07-17").click();
  await expect(page.getByText("첫날 DB 본문")).toBeVisible();
  await page.goto("/#/issue-history-preview/3");
  await expect(
    page.getByText("이 대표 문서에 저장된 리포트가 없습니다."),
  ).toBeVisible();
  await expect(page.getByTestId("calendar-day-2026-07-18")).toBeDisabled();
  await expect(page.getByText("이 날짜의 DB 리포트가 없습니다.")).toBeVisible();
});
