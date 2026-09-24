import { test, expect } from "@playwright/test";
import { serve } from "./server.js";
import { mockClient } from "../src/data/mock/client.js";

const original = (await mockClient.getIssue("iran-hormuz-2025")).data;
const group = {
  id: 42,
  label: "The Odyssey (2026 film)",
  source: "replay",
  status: "CONFIRMED",
  pulseScore: 12,
  snapshotTs: "2026-07-18T01:00:00Z",
  firstSeen: "2026-07-17T01:00:00Z",
  occurrenceCount: 2,
  defaultReportId: 41,
  summary: "최신 요약 없음",
  memberCount: 2,
  stockCount: 1,
};
const report = {
  status: "ready",
  model: "test",
  generatedAt: "2026-07-17T03:00:00Z",
  snapshotTs: "2026-07-17T01:00:00Z",
  sections: [
    {
      id: "overview",
      title: "이슈 개요",
      body: "오디세이 DB 본문",
      evidenceIds: [],
    },
  ],
};

test("운영 이슈 탐색에서 대표 문서 한 건과 리포트 보유 날짜만 표시한다", async ({
  page,
}) => {
  const calls = await serve(page, async ({ route, url }) => {
    if (url.pathname === "/api/v1/issues/history/groups") {
      await route.fulfill({
        json: {
          data: url.searchParams.get("q") === "없는 제목" ? [] : [group],
          meta: {
            pagination: { offset: 0, limit: 20, total: 1, hasMore: false },
          },
        },
      });
      return true;
    }
    if (/^\/api\/v1\/issues\/(41|42)\/history\/reports$/.test(url.pathname)) {
      await route.fulfill({
        json: {
          data: [
            {
              id: 41,
              snapshotTs: "2026-07-17T01:00:00Z",
              status: "CONFIRMED",
              pulseScore: 11,
            },
          ],
          meta: {
            pagination: { offset: 0, limit: 100, total: 1, hasMore: false },
          },
        },
      });
      return true;
    }
    if (/^\/api\/v1\/issues\/(41|42)$/.test(url.pathname)) {
      const isReport = url.pathname.endsWith("/41");
      await route.fulfill({
        json: {
          data: {
            ...original,
            id: isReport ? 41 : 42,
            label: group.label,
            source: "replay",
            snapshotTs: isReport ? "2026-07-17T01:00:00Z" : group.snapshotTs,
            summary: isReport ? "오디세이 DB 요약" : null,
            report: isReport ? report : null,
          },
        },
      });
      return true;
    }
    return false;
  });
  await page.goto("/#/issues");
  await expect(page.locator(".explore-layout .event-row")).toHaveCount(1);
  await expect(page.locator(".event-row")).toContainText("2개 기록");
  await expect(page.locator(".event-row")).not.toContainText("과거 재구성");
  await expect(page.locator(".event-row")).not.toContainText("최신 요약 없음");
  await page.getByRole("searchbox", { name: "사건 검색" }).fill("Odyssey");
  await expect
    .poll(() =>
      calls.some(
        (url) =>
          url.pathname === "/api/v1/issues/history/groups" &&
          url.searchParams.get("q") === "Odyssey",
      ),
    )
    .toBe(true);
  await page.locator(".event-row").dblclick();
  await expect(page).toHaveURL(/\/issues\/41\?q=Odyssey$/);
  await expect(page.getByTestId("calendar-day-2026-07-17")).toBeEnabled();
  await expect(page.getByTestId("calendar-day-2026-07-18")).toBeDisabled();
  await expect(page.getByText("오디세이 DB 본문")).toBeVisible();
  await page.goto("/#/issues/42");
  await expect(page.getByTestId("calendar-day-2026-07-17")).toBeEnabled();
  await expect(page.getByTestId("calendar-day-2026-07-18")).toBeDisabled();
});

test("요약만 저장된 날짜도 활성화하고 본문 부재를 정확하게 설명한다", async ({
  page,
}) => {
  await serve(page, async ({ route, url }) => {
    if (url.pathname === "/api/v1/issues/44/history/reports") {
      await route.fulfill({
        json: {
          data: [
            {
              id: 44,
              snapshotTs: "2026-07-17T01:00:00Z",
              status: "CONFIRMED",
              pulseScore: 10,
            },
          ],
          meta: {
            pagination: { offset: 0, limit: 100, total: 1, hasMore: false },
          },
        },
      });
      return true;
    }
    if (url.pathname === "/api/v1/issues/44") {
      await route.fulfill({
        json: {
          data: {
            ...original,
            id: 44,
            label: "요약만 있는 문서",
            source: "replay",
            snapshotTs: "2026-07-17T01:00:00Z",
            summary: "DB에 저장된 요약",
            report: null,
          },
        },
      });
      return true;
    }
    return false;
  });
  await page.goto("/#/issues/44");
  await expect(page.getByTestId("calendar-day-2026-07-17")).toBeEnabled();
  await expect(
    page.getByText("DB에 저장된 요약", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("본문 리포트는 저장되지 않았습니다"),
  ).toBeVisible();
});

test("같은 날짜의 리포트 두 건은 시각별 ID로 구분한다", async ({ page }) => {
  await serve(page, async ({ route, url }) => {
    if (/^\/api\/v1\/issues\/(46|47)\/history\/reports$/.test(url.pathname)) {
      await route.fulfill({
        json: {
          data: [
            {
              id: 47,
              snapshotTs: "2026-07-17T02:00:00Z",
              status: "CONFIRMED",
              pulseScore: 12,
              source: "live",
            },
            {
              id: 46,
              snapshotTs: "2026-07-17T01:00:00Z",
              status: "CONFIRMED",
              pulseScore: 11,
              source: "replay",
            },
          ],
          meta: {
            pagination: { offset: 0, limit: 100, total: 2, hasMore: false },
          },
        },
      });
      return true;
    }
    if (/^\/api\/v1\/issues\/(46|47)$/.test(url.pathname)) {
      const id = Number(url.pathname.split("/").at(-1));
      await route.fulfill({
        json: {
          data: {
            ...original,
            id,
            source: "replay",
            snapshotTs:
              id === 47 ? "2026-07-17T02:00:00Z" : "2026-07-17T01:00:00Z",
            report,
          },
        },
      });
      return true;
    }
    return false;
  });
  await page.goto("/#/issues/47");
  await expect(page.getByTestId("calendar-day-2026-07-17")).toHaveAttribute(
    "aria-label",
    "7월 17일, 리포트 2건",
  );
  await expect(
    page.getByRole("group", { name: "선택한 날짜의 시각별 기록" }).locator("a"),
  ).toHaveCount(2);
  await expect(
    page.locator('.hp-same-day a[href="#/issues/46"]'),
  ).toContainText("과거 재구성");
  await expect(
    page.locator('.hp-same-day a[href="#/issues/47"]'),
  ).toContainText("실시간");
  await page.locator('.hp-same-day a[href="#/issues/46"]').click();
  await expect(page).toHaveURL(/\/issues\/46$/);
});

test("리포트 이력 API가 실패해도 기존 상세는 유지한다", async ({ page }) => {
  await serve(page, async ({ route, url }) => {
    if (url.pathname === "/api/v1/issues/41/history/reports") {
      await route.fulfill({
        status: 500,
        json: { error: { code: "INTERNAL" } },
      });
      return true;
    }
    if (url.pathname === "/api/v1/issues/41") {
      await route.fulfill({
        json: {
          data: {
            ...original,
            id: 41,
            label: group.label,
            source: "replay",
            snapshotTs: "2026-07-17T01:00:00Z",
            summary: "오디세이 DB 요약",
            report,
          },
        },
      });
      return true;
    }
    return false;
  });
  await page.goto("/#/issues/41");
  await expect(
    page.getByText("리포트 날짜를 불러오지 못했습니다.", { exact: false }),
  ).toBeVisible();
  await expect(page.getByText("오디세이 DB 본문")).toBeVisible();
});

test("리포트가 하나도 없는 대표 문서는 달력을 모두 비활성화한다", async ({
  page,
}) => {
  await serve(page, async ({ route, url }) => {
    if (url.pathname === "/api/v1/issues/45/history/reports") {
      await route.fulfill({
        json: {
          data: [],
          meta: {
            pagination: { offset: 0, limit: 100, total: 0, hasMore: false },
          },
        },
      });
      return true;
    }
    if (url.pathname === "/api/v1/issues/45") {
      await route.fulfill({
        json: {
          data: {
            ...original,
            id: 45,
            label: "리포트 없는 대표 문서",
            source: "replay",
            snapshotTs: "2026-07-17T01:00:00Z",
            summary: null,
            report: null,
          },
        },
      });
      return true;
    }
    return false;
  });
  await page.goto("/#/issues/45");
  await expect(
    page.getByText("이 대표 문서에 저장된 리포트가 없습니다."),
  ).toBeVisible();
  await expect(page.getByTestId("calendar-day-2026-07-17")).toBeDisabled();
  await expect(
    page.getByRole("heading", { name: "리포트 없는 대표 문서" }),
  ).toBeVisible();
});
