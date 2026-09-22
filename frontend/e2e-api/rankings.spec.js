import { test, expect } from "@playwright/test";
import { serve } from "./server.js";
import { mockClient } from "../src/data/mock/client.js";
import { rankingWindow } from "../src/data/rankings.js";

const issue = (await mockClient.getIssue("iran-hormuz-2025")).data;
const payload = {
  ...rankingWindow("2026-09-22T00:00:00Z"),
  monthly: [{ id: issue.id, label: "최근 30일 최고점 이슈", pulseScore: 19.5 }],
  yearly: [{ id: issue.id, label: "최근 1년 최고점 이슈", pulseScore: 29.5 }],
};

test("rankings are independent of list filters and link to the peak snapshot", async ({
  page,
}) => {
  const calls = await serve(page, async ({ route, url }) => {
    if (url.pathname !== "/api/v1/issues/rankings") return false;
    await route.fulfill({ json: { data: payload } });
    return true;
  });
  await page.goto("/#/issues");
  const aside = page.getByRole("complementary", { name: "기간별 이슈 Top 10" });
  await expect(aside.locator("a")).toHaveCount(1);
  await expect(
    aside.getByRole("heading", { name: "TOP 10", exact: true }),
  ).toHaveCount(1);
  await aside.getByRole("button", { name: "1년", exact: true }).click();
  await expect(
    aside.getByRole("button", { name: "1년", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(aside.locator("a")).toContainText("최근 1년 최고점 이슈");
  await aside.getByRole("button", { name: "30일", exact: true }).click();
  await expect(aside.locator("a")).toContainText("최근 30일 최고점 이슈");
  await expect(
    page.locator('.wp-segment[aria-label="이슈 보기 방식"] button'),
  ).toHaveText(["리스트", "카드"]);
  const left = await page.locator(".explore-results").boundingBox();
  const right = await aside.boundingBox();
  expect(right.x).toBeGreaterThan(left.x + left.width);
  expect(left.width / right.width).toBeGreaterThan(2);
  expect(left.width / right.width).toBeLessThan(3);
  const search = await page
    .getByRole("textbox", { name: "사건 검색", exact: true })
    .boundingBox();
  const viewToggle = await page
    .locator('.wp-segment[aria-label="이슈 보기 방식"]')
    .boundingBox();
  expect(viewToggle.x).toBeGreaterThan(search.x + search.width);
  expect(Math.abs(viewToggle.y - search.y)).toBeLessThan(8);
  await page.evaluate(() => window.scrollTo(0, 600));
  await expect
    .poll(async () => Math.round((await aside.boundingBox()).y))
    .toBe(100);
  await page
    .getByRole("combobox", { name: "분석 상태", exact: true })
    .selectOption("CONFIRMED");
  await expect(aside.locator("a")).toHaveCount(1);
  expect(
    calls.filter((url) => url.pathname === "/api/v1/issues/rankings"),
  ).toHaveLength(1);
  await aside.getByRole("link", { name: /최근 30일 최고점 이슈/ }).click();
  await expect(page).toHaveURL(new RegExp(`/issues/${issue.id}$`));
  await expect(page.locator(".dt-page")).toBeVisible();
});

test("empty and failed rankings preserve the list and retry independently", async ({
  page,
}) => {
  let fail = true;
  await serve(page, async ({ route, url }) => {
    if (url.pathname !== "/api/v1/issues/rankings") return false;
    await route.fulfill(
      fail
        ? { status: 500, json: { error: { code: "TEST_FAILURE" } } }
        : { json: { data: { ...payload, monthly: [], yearly: [] } } },
    );
    return true;
  });
  await page.goto("/#/issues");
  await expect(page.locator(".event-row")).toHaveCount(20);
  await expect(
    page.getByRole("button", { name: "순위 다시 불러오기" }),
  ).toBeVisible();
  fail = false;
  await page.getByRole("button", { name: "순위 다시 불러오기" }).click();
  await expect(page.getByText("이 기간에 포착된 이슈가 없습니다.")).toHaveCount(
    1,
  );
  await expect(page.locator(".event-row")).toHaveCount(20);
});

test("mobile rankings stack below the list without horizontal overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await serve(page);
  await page.goto("/#/issues");
  const aside = page.locator(".explore-rankings");
  await expect(aside.locator("a")).toHaveCount(10);
  await expect(aside).toHaveCSS("position", "static");
  await aside.scrollIntoViewIfNeeded();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({ path: "test-results/api/rankings-mobile.png" });
});
