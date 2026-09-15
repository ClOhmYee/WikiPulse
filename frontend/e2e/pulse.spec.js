import { isNewIssue } from "../src/data/pulse/time.js";
import { test, expect } from "@playwright/test";
import { issueId, pageId } from "../src/data/mock/identity.js";
import {
  dates,
  timestamp,
  snapshotAt,
} from "../src/data/mock/fixtures/history.js";

test("fullscreen map opens a right-hand panel and both panels link to the report", async ({
  page,
}) => {
  await page.goto("/#/pulse");
  await page
    .getByRole("button", { name: "펄스맵 전체화면", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "펄스맵 전체화면" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("complementary")).toHaveCount(0);
  const bounds = await dialog.boundingBox();
  expect(bounds.width).toBeGreaterThan(1400);
  expect(bounds.height).toBeGreaterThan(950);
  await dialog
    .locator('.document-cluster[data-rank="0"] .document-cluster__title')
    .click();
  const panel = dialog.getByRole("complementary", { name: "선택한 사건" });
  await expect(panel).toBeVisible();
  const panelBounds = await panel.boundingBox();
  const mapBounds = await dialog.locator(".document-map").boundingBox();
  expect(panelBounds.x).toBeGreaterThanOrEqual(
    mapBounds.x + mapBounds.width - 1,
  );
  const href = await panel
    .getByRole("link", { name: "이슈 리포트 보기" })
    .getAttribute("href");
  await page.screenshot({ path: "test-results/pulse-fullscreen-desktop.png" });
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "펄스맵 전체화면", exact: true }),
  ).toBeFocused();
  await expect(
    page.getByRole("link", { name: "이슈 리포트 보기" }),
  ).toHaveAttribute("href", href);
  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .getByRole("button", { name: "펄스맵 전체화면", exact: true })
    .click();
  await expect(
    dialog.getByRole("link", { name: "이슈 리포트 보기" }),
  ).toBeInViewport();
  await page.screenshot({ path: "test-results/pulse-fullscreen-mobile.png" });
  await dialog.getByRole("button", { name: "클러스터 정보 닫기" }).click();
  await expect(dialog.getByRole("complementary")).toHaveCount(0);
  await dialog
    .locator('.document-cluster[data-rank="0"] > [role="button"]:first-child')
    .focus();
  await page.keyboard.press("Enter");
  await dialog
    .getByRole("button", { name: "전체화면 닫기", exact: true })
    .click();
  await expect(dialog).toHaveCount(0);
  await page.getByRole("link", { name: "이슈 리포트 보기" }).click();
  await expect(page).toHaveURL(new RegExp(`${href.slice(1)}$`));
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  expect(await page.evaluate(() => document.body.style.overflow)).not.toBe(
    "hidden",
  );
  await page.goBack();
  await page.locator(".pulse-cluster-list button").first().click();
  await page
    .getByRole("button", { name: "펄스맵 전체화면", exact: true })
    .click();
  await dialog.getByRole("link", { name: "이슈 리포트 보기" }).click();
  await expect(page).toHaveURL(new RegExp(`${href.slice(1)}$`));
  await expect(dialog).toHaveCount(0);
  expect(await page.evaluate(() => document.body.style.overflow)).not.toBe(
    "hidden",
  );
});

test("full-year slider, month boundaries and archived report -> stock journey", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/#/pulse");
  const latest = snapshotAt(dates.at(-1));
  const fresh = latest.data.clusters.filter((c) =>
    isNewIssue(
      c.firstDetectedAt,
      latest.meta.snapshotTs,
      latest.meta.newWindowHours,
    ),
  );
  const map = page.getByRole("region", { name: "사건 관계 지도" });
  await expect(map.locator(".document-node")).toHaveCount(
    fresh.reduce((sum, c) => sum + c.nodes.length, 0),
  );
  await expect(map.locator("[data-edge-id]")).toHaveCount(
    fresh.reduce((sum, c) => sum + c.edges.length, 0),
  );
  await expect(page.locator(".pulse-cluster-list")).not.toContainText("HOT");
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
    await expect(page.locator(".pulse-layout")).toHaveAttribute(
      "data-snapshot",
      timestamp(date),
    );
  }
  await page
    .getByRole("combobox", { name: "스냅샷 날짜" })
    .selectOption("2026-01-01");
  await slider.focus();
  await page.keyboard.press("ArrowLeft");
  await expect(page.locator(".pulse-layout")).toHaveAttribute(
    "data-snapshot",
    timestamp("2025-12-31"),
  );
  await expect(
    page.getByRole("heading", {
      name: "이 시점에 새로 감지된 이슈가 없습니다",
    }),
  ).toBeVisible();
  await expect(map).toHaveCount(0);
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
  await panel.getByRole("link", { name: "이슈 리포트 보기" }).click();
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
  const fresh = latest.data.clusters.filter((c) =>
    isNewIssue(
      c.firstDetectedAt,
      latest.meta.snapshotTs,
      latest.meta.newWindowHours,
    ),
  );
  const map = page.getByRole("region", { name: "사건 관계 지도" });
  await expect(map.locator(".document-node")).toHaveCount(
    fresh.reduce((sum, c) => sum + c.nodes.length, 0),
  );
  const node = map
    .locator(`[data-page-id="${pageId(fresh[0].nodes[0].pageId)}"]`)
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
    .filter({ hasText: fresh[0].label })
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
    .filter({ hasText: fresh[1].label })
    .click();
  await page
    .locator(".pulse-cluster-list button")
    .filter({ hasText: fresh[0].label })
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
