import { test, expect } from "@playwright/test";

const metadata = [
  { id: 1, source: "replay", issue_key: "replay:enwiki:The Odyssey (2026 film)", label: "The Odyssey (2026 film)", snapshot_ts: "2026-07-17T01:00:00+00:00", status: "CONFIRMED", pulse_score: 10.1 },
  { id: 2, source: "replay", issue_key: "replay:enwiki:The Odyssey (2026 film)", label: "The Odyssey (2026 film)", snapshot_ts: "2026-07-18T01:00:00+00:00", status: "DETECTED", pulse_score: 9.2 },
  { id: 3, source: "replay", issue_key: "replay:enwiki:The Odyssey (1997 miniseries)", label: "The Odyssey (1997 miniseries)", snapshot_ts: "2026-07-18T02:00:00+00:00", status: "DETECTED", pulse_score: 8.1 },
];
const details = [
  { ...metadata[0], members: [{ pageId: 11, title: "A" }, { pageId: 12, title: "B" }], summary: "첫날 요약", stocks: [{ ticker: "AAA", name: "첫날 종목" }] },
  { ...metadata[1], members: [{ pageId: 11, title: "A" }, { pageId: 13, title: "C" }], summary: null, stocks: [] },
];

test("별도 로컬 화면에서 대표 문서를 한 건으로 묶고 시점별 실제 내용을 분리한다", async ({ page }) => {
  await page.route("**/__local_issue_history_preview/metadata.jsonl", (route) =>
    route.fulfill({ status: 200, contentType: "application/octet-stream", body: metadata.map(JSON.stringify).join("\n") }),
  );
  await page.route("**/__local_issue_history_preview/details.jsonl", (route) =>
    route.fulfill({ status: 200, contentType: "application/octet-stream", body: details.map(JSON.stringify).join("\n") }),
  );
  await page.goto("/#/issue-history-preview");
  await expect(page.getByRole("heading", { name: "과거 이슈 미리보기" })).toBeVisible();
  await page.getByRole("searchbox", { name: "대표 문서 검색" }).fill("The Odyssey (2026 film)");
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /The Odyssey \(2026 film\).*2건/ })).toHaveCount(1);
  await page.getByRole("button", { name: /The Odyssey \(2026 film\).*2건/ }).click();
  await expect(page.getByRole("heading", { name: "날짜별 기록" })).toBeVisible();
  await page.getByTestId("preview-snapshot-1").click();
  await expect(page.getByText("첫날 요약")).toBeVisible();
  await expect(page.getByText("B", { exact: true })).toBeVisible();
  await expect(page.getByText("AAA", { exact: true })).toBeVisible();
  await page.getByTestId("preview-snapshot-2").click();
  await expect(page.getByText("C", { exact: true })).toBeVisible();
  await expect(page.getByText("첫날 요약")).toHaveCount(0);
  await expect(page.getByText("AAA", { exact: true })).toHaveCount(0);
  await expect(page.getByText("이 시점에는 요약이 없습니다.")).toBeVisible();
});
