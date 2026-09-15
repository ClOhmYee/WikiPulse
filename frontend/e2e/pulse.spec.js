import { test, expect } from "@playwright/test";
import { issueId, pageId } from "../src/data/mock/identity.js";
import {
  dates,
  timestamp,
  snapshotAt,
} from "../src/data/mock/fixtures/history.js";

test("full-year slider, month boundaries and archived report -> stock journey", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/#/pulse");
  const latest = snapshotAt(dates.at(-1));
  const map = page.getByRole("region", { name: "사건 관계 지도" });
  await expect(map.locator(".document-node")).toHaveCount(
    latest.meta.nodeCount,
  );
  await expect(map.locator("[data-edge-id]")).toHaveCount(
    latest.meta.edgeCount,
  );
  await expect(page.locator(".pulse-cluster-list")).toContainText("HOT");
  await expect(page.locator(".pulse-cluster-list")).toContainText("NEW");
  const slider = page.getByRole("slider", { name: "스냅샷 시각" });
  await expect(slider).toHaveAttribute(
    "min",
    String(Date.parse(timestamp(dates[0]))),
  );
  await expect(slider).toHaveAttribute(
    "max",
    String(Date.parse(timestamp(dates.at(-1)))),
  );
  await slider.focus();
  await page.keyboard.press("Home");
  await expect(map).toHaveAttribute("data-snapshot", timestamp("2025-09-01"));
  await expect(page.getByRole("button", { name: "이전 시점" })).toBeDisabled();
  for (const date of ["2025-10-01", "2025-12-31", "2026-01-01", "2026-06-10"]) {
    await page
      .getByRole("combobox", { name: "스냅샷 날짜" })
      .selectOption(date);
    await expect(map).toHaveAttribute("data-snapshot", timestamp(date));
  }
  await page
    .getByRole("combobox", { name: "스냅샷 날짜" })
    .selectOption("2026-01-01");
  await slider.focus();
  await page.keyboard.press("ArrowLeft");
  await expect(map).toHaveAttribute("data-snapshot", timestamp("2025-12-31"));
  await page.keyboard.press("End");
  await expect(map).toHaveAttribute("data-snapshot", latest.meta.snapshotTs);
  await page
    .locator(".pulse-cluster-list button")
    .filter({ hasText: "공공 안전" })
    .click();
  await page.getByRole("button", { name: "이전 시점" }).click();
  await expect(page.locator(".pulse-notice")).toContainText(
    "선택한 이슈가 이 시점에 없어",
  );
  await page
    .getByRole("combobox", { name: "스냅샷 날짜" })
    .selectOption("2025-09-01");
  await page
    .locator(".pulse-cluster-list button")
    .filter({ hasText: "호르무즈" })
    .click();
  const panel = page.getByRole("complementary", { name: "선택한 사건" });
  await expect(panel).toHaveAttribute("data-snapshot", timestamp("2025-09-01"));
  await panel.locator(".pulse-document").first().click();
  await expect(
    panel.getByRole("region", { name: "선택한 문서" }),
  ).toContainText("합성 예시");
  await panel.getByRole("link", { name: "사건 자세히 보기" }).click();
  await expect(page).toHaveURL(
    new RegExp(`${issueId("iran-hormuz-2025--2025-09~2025-09-01")}$`),
  );
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "호르무즈",
  );
  await page.getByRole("link", { name: "종목 연결 근거 보기" }).click();
  await expect(page.locator(".st-stock-row")).toHaveCount(2);
  await expect(
    page.locator(".st-stock-row").filter({ hasText: "BKR" }),
  ).toBeVisible();
  await page.locator(".st-stock-identity").filter({ hasText: "BKR" }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "베이커 휴스" }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("dense map selection, filtering and desktop/mobile handoff", async ({
  page,
}) => {
  await page.goto("/#/pulse");
  const latest = snapshotAt(dates.at(-1));
  const map = page.getByRole("region", { name: "사건 관계 지도" });
  await expect(map.locator(".document-node")).toHaveCount(
    latest.meta.nodeCount,
  );
  const node = map
    .locator(`[data-page-id="${pageId("semiconductor")}"]`)
    .first();
  const radius = await node.locator(".document-node__body").getAttribute("r");
  const position = await node.getAttribute("transform");
  await page.getByRole("button", { name: "기술", exact: true }).click();
  await expect(node).toHaveAttribute("transform", position);
  await expect(node.locator(".document-node__body")).toHaveAttribute(
    "r",
    radius,
  );
  await page.getByRole("button", { name: "전체", exact: true }).click();
  await page.screenshot({
    path: "test-results/pulse-desktop.png",
    fullPage: true,
  });
  await page
    .locator(".pulse-cluster-list button")
    .filter({ hasText: "AI 반도체" })
    .click();
  await page
    .getByRole("complementary", { name: "선택한 사건" })
    .locator(".pulse-document")
    .first()
    .click();
  await page.screenshot({
    path: "test-results/pulse-desktop-selected.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "지도 위치 초기화" }).click();
  await page.screenshot({
    path: "test-results/pulse-mobile.png",
    fullPage: true,
  });
  await page
    .locator(".pulse-cluster-list button")
    .filter({ hasText: "호르무즈" })
    .click();
  await page
    .locator(".pulse-cluster-list button")
    .filter({ hasText: "AI 반도체" })
    .click();
  await page.screenshot({
    path: "test-results/pulse-mobile-selected.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth - innerWidth,
    ),
  ).toBeLessThanOrEqual(1);
  const panel = await page.locator(".pulse-preview").boundingBox(),
    graph = await map.boundingBox();
  expect(panel.y).toBeGreaterThanOrEqual(graph.y + graph.height - 1);
});
