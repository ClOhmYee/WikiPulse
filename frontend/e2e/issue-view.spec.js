import { test, expect } from "@playwright/test";

test("issue pagination, view mode, local title search and server filters state their scope", async ({
  page,
}) => {
  await page.goto("/#/issues");
  await expect(page.locator(".event-row")).toHaveCount(20);
  await expect(
    page.getByRole("navigation", { name: "목록 페이지" }),
  ).toContainText("전체 36개");
  await page.getByRole("button", { name: "카드", exact: true }).click();
  await expect(page.locator(".event-list")).toHaveAttribute(
    "data-view",
    "card",
  );
  await page.getByRole("button", { name: "다음 페이지", exact: true }).click();
  await expect(page.locator(".event-row")).toHaveCount(16);
  await expect(page.locator(".event-list")).toHaveAttribute(
    "data-view",
    "card",
  );
  await page
    .getByRole("textbox", { name: "사건 검색", exact: true })
    .fill("no-such-title");
  await expect(
    page.getByRole("heading", {
      name: "현재 페이지에서 일치하는 사건이 없습니다",
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "필터 초기화", exact: true }).click();
  await expect(page.locator(".event-row")).toHaveCount(20);
  await page
    .getByRole("combobox", { name: "데이터 출처", exact: true })
    .selectOption("live");
  await expect(
    page.getByRole("heading", { name: "이 조건에 해당하는 사건이 없습니다" }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "데이터 출처", exact: true })
    .selectOption("replay");
  await expect(page.locator(".event-row")).toHaveCount(20);
  await page.getByRole("button", { name: "급증 점수란?", exact: true }).click();
  await expect(page.locator(".wp-explainer")).toContainText(
    "AI 검증의 확률이 아닙니다",
  );
});
