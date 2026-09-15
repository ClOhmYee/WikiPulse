import { test, expect } from "@playwright/test";
import { mockClient } from "../src/data/mock/client.js";

const issue = (await mockClient.getIssue("iran-hormuz-2025")).data;
const stock = issue.relatedStocks[0];
test.beforeEach(async ({ page }) => {
  page.__errors = [];
  page.on("pageerror", (error) => page.__errors.push(error.message));
});
test.afterEach(async ({ page }) => expect(page.__errors).toEqual([]));

test("onboarding exits into the workspace and releases scroll state", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("link", { name: "탐색 시작하기" }).click();
  await expect(
    page.getByRole("heading", { name: "세상의 변화가 모이는 곳" }),
  ).toBeVisible();
  await expect(page.locator("html")).not.toHaveClass(/scene-snap-enabled/);
});

test("issue detail shows supported evidence and unavailable time series/news instead of fabricated data", async ({
  page,
}) => {
  await page.goto(`/#/issues/${issue.id}`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(issue.label);
  await expect(page.getByText("시계열 미제공", { exact: true })).toBeVisible();
  await expect(page.locator(".dt-event-metrics")).not.toContainText("배");
  await page.getByRole("tab", { name: "관련 소식", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "관련 소식 미제공", exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "타임라인", exact: true }).click();
  await expect(
    page.getByText("타임라인 미제공", { exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: /^근거 문서/ }).click();
  await expect(page.locator(".dt-evidence-row").first()).toHaveAttribute(
    "href",
    /^https:\/\/en\.wikipedia\.org\/wiki\//,
  );
  await expect(page.locator(".dt-evidence-row").first()).toHaveAttribute(
    "target",
    "_blank",
  );
  await page.getByRole("tab", { name: /^근거 문서/ }).focus();
  await page.keyboard.press("End");
  await expect(
    page.getByRole("tab", { name: "토론", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
});

test("issue -> verified related stocks -> stock -> issue retains identifiers and evidence limits", async ({
  page,
}) => {
  await page.goto(`/#/issues/${issue.id}`);
  await page
    .locator(".dt-report-actions")
    .getByRole("link", { name: /^연관 주식/ })
    .click();
  await expect(page).toHaveURL(new RegExp(`/issues/${issue.id}/stocks$`));
  await expect(page.locator(".st-stock-row").first()).toContainText(
    "후보 탐색 경로",
  );
  await expect(page.locator(".data-scope")).toContainText(
    "전체 개수는 제공되지 않았습니다",
  );
  await page
    .locator(".st-stock-identity")
    .filter({ hasText: stock.ticker })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(stock.name);
  await expect(
    page.getByText("가격 자료 미제공", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".st-detail-page .data-scope")).toContainText(
    "최대 50개",
  );
  const link = page.locator(`.st-event-title[href="#/issues/${issue.id}"]`);
  await link.click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(issue.label);
  await page.goBack();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(stock.name);
});

test("server-backed stock filters search beyond the first page", async ({
  page,
}) => {
  await page.goto("/#/stocks");
  await expect(page.locator(".st-stock-row")).toHaveCount(20);
  await expect(
    page.getByRole("navigation", { name: "목록 페이지" }),
  ).toContainText("102");
  await page.getByRole("button", { name: "다음 페이지", exact: true }).click();
  await expect(
    page.getByRole("navigation", { name: "목록 페이지" }),
  ).toContainText("21–40");
  await page
    .getByRole("textbox", { name: "종목 검색", exact: true })
    .fill("NVDA");
  await page.getByRole("button", { name: "검색 적용", exact: true }).click();
  await expect(page.locator(".st-stock-row")).toHaveCount(1);
  await expect(page.locator(".st-stock-row")).toContainText("NVDA");
  await expect(
    page.getByRole("button", { name: "이전 페이지", exact: true }),
  ).toBeDisabled();
});

test("saved issue and stock survive reload and remain removable", async ({
  page,
}) => {
  await page.goto(`/#/issues/${issue.id}`);
  await page.getByRole("button", { name: "이벤트 저장", exact: true }).click();
  await page.goto(`/#/stocks/${stock.ticker}`);
  await page
    .getByRole("button", {
      name: `${stock.name} 관심 종목에 추가`,
      exact: true,
    })
    .click();
  await page.goto("/#/saved");
  await page.reload();
  await expect(page.locator(".event-row")).toHaveCount(1);
  await page
    .getByRole("button", { name: `${issue.label} 저장 해제`, exact: true })
    .click();
  await expect(page.locator(".event-row")).toHaveCount(0);
  await page.getByRole("button", { name: /^관심 종목/ }).click();
  await page
    .getByRole("button", { name: `${stock.name} 관심 종목 해제`, exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "궁금한 종목을 저장해 보세요" }),
  ).toBeVisible();
});

test("quick stock search supports keyboard selection and empty recovery", async ({
  page,
}) => {
  await page.goto("/#/issues");
  await page.keyboard.press("Control+k");
  const search = page.getByRole("combobox", {
    name: "빠른 종목 검색",
    exact: true,
  });
  await expect(search).toBeFocused();
  await search.fill("NVDA");
  await expect(page.getByRole("listbox").getByRole("option")).toHaveCount(1);
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#\/stocks\/NVDA$/);
  await search.fill("no-such-stock-xyz");
  await expect(page.getByRole("listbox")).toContainText("결과가 없습니다");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("listbox")).toHaveCount(0);
});

test("compact pages keep the supported data within a 390px viewport", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  for (const route of [
    "/issues",
    `/issues/${issue.id}`,
    `/issues/${issue.id}/stocks`,
    "/stocks",
    `/stocks/${stock.ticker}`,
    "/saved",
  ]) {
    await page.goto(`/#${route}`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth - innerWidth,
      ),
      route,
    ).toBeLessThanOrEqual(1);
  }
});

test("reduced-motion onboarding retains its final exit", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page
    .getByRole("navigation", { name: "온보딩 장면" })
    .getByRole("button")
    .last()
    .click();
  await page
    .getByRole("link", { name: "Pulse Map 시작하기", exact: true })
    .click();
  await expect(page).toHaveURL(/#\/pulse$/);
  await expect(page.locator("html")).not.toHaveClass(/scene-snap-enabled/);
});
