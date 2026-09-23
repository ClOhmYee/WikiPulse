import { test, expect } from "@playwright/test";
import { issueId, pageId } from "../src/data/mock/identity.js";
import { isNewIssue } from "../src/data/pulse/time.js";
import {
  dates,
  timestamp,
  snapshotAt,
} from "../src/data/mock/fixtures/history.js";

for (const width of [1440, 390]) {
  test(`fullscreen restores the launch scroll position at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/#/pulse");
    const open = page.getByRole("button", {
      name: "펄스맵 전체화면",
      exact: true,
    });
    const dialog = page.getByRole("dialog", { name: "펄스맵 전체화면" });
    for (const [index, closeWithEscape] of [false, true].entries()) {
      await open.scrollIntoViewIfNeeded();
      // Keep the opener visible, but use a different position on each visit.
      await page.evaluate(
        (offset) => window.scrollBy({ top: offset, behavior: "instant" }),
        index * 40,
      );
      const before = await page.evaluate(() => ({ x: scrollX, y: scrollY }));
      expect(before.y).toBeGreaterThan(100);
      await open.click();
      await expect(dialog).toBeVisible();
      if (closeWithEscape) await page.keyboard.press("Escape");
      else
        await dialog
          .getByRole("button", { name: "전체화면 닫기", exact: true })
          .click();
      await expect(dialog).toHaveCount(0);
      await expect(open).toBeFocused();
      await expect
        .poll(() => page.evaluate(() => ({ x: scrollX, y: scrollY })))
        .toEqual(before);
      // Check after layout/focus/scroll anchoring have had time to settle too.
      await page.waitForTimeout(250);
      expect(await page.evaluate(() => ({ x: scrollX, y: scrollY }))).toEqual(
        before,
      );
    }
  });
}

test("fullscreen map opens a right-hand panel and both panels link to the report", async ({
  page,
}) => {
  const target = snapshotAt(dates.at(-1)).data.clusters.find(
    (cluster) => cluster.issueKey === "digital-assets",
  );
  await page.goto("/#/pulse");
  await page
    .getByRole("button", { name: "펄스맵 전체화면", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "펄스맵 전체화면" });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator(".pulse-fullscreen__heading")).toHaveCount(0);
  const controls = dialog.locator(".document-map__controls");
  await expect(controls.getByRole("button").last()).toHaveAttribute(
    "aria-label",
    "전체화면 닫기",
  );
  await expect(dialog.getByRole("complementary")).toHaveCount(0);
  const bounds = await dialog.boundingBox();
  expect(bounds.width).toBeGreaterThan(1400);
  expect(bounds.height).toBeGreaterThan(950);
  await dialog
    .locator(
      `.document-cluster[data-issue-key="${target.issueKey}"] .document-cluster__title`,
    )
    .click();
  const panel = dialog.getByRole("complementary", { name: "선택한 사건" });
  await expect(panel).toBeVisible();
  await expect(panel.locator("h2")).toHaveText(target.label);
  const panelBounds = await panel.boundingBox();
  const mapBounds = await dialog.locator(".document-map").boundingBox();
  expect(mapBounds.y).toBeCloseTo(bounds.y + 1, 0);
  const saveBounds = await panel
    .getByRole("button", { name: "선택한 사건 저장", exact: true })
    .boundingBox();
  const closeBounds = await panel
    .getByRole("button", { name: "클러스터 정보 닫기" })
    .boundingBox();
  expect(closeBounds.x).toBeGreaterThanOrEqual(saveBounds.x + saveBounds.width);
  expect(closeBounds.y).toBeCloseTo(saveBounds.y, 1);
  expect(panelBounds.x).toBeGreaterThanOrEqual(
    mapBounds.x + mapBounds.width - 1,
  );
  const href = await panel
    .getByRole("link", { name: "이슈 리포트 보기" })
    .getAttribute("href");
  await dialog.locator(".document-map > svg").hover();
  await expect(dialog.locator(".pulse-fullscreen__time-drawer")).toBeHidden();
  await expect(
    panel.getByRole("button", { name: "클러스터 정보 닫기" }),
  ).toBeInViewport();
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
  await dialog.locator(".document-map__controls").hover();
  await expect(dialog.locator(".pulse-fullscreen__time-drawer")).toBeHidden();
  await page.screenshot({ path: "test-results/pulse-fullscreen-mobile.png" });
  await dialog.getByRole("button", { name: "클러스터 정보 닫기" }).click();
  await expect(dialog.getByRole("complementary")).toHaveCount(0);
  await dialog
    .getByRole("button", {
      name: `${target.label}, ${target.memberCount}개 문서`,
      exact: true,
    })
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
  await page
    .locator(".pulse-cluster-list button")
    .filter({ hasText: target.label })
    .click();
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
  const clusters = latest.data.clusters;
  const map = page.getByRole("region", { name: "사건 관계 지도" });
  await expect(map.locator(".document-cluster")).toHaveCount(clusters.length);
  await expect(map.locator(".document-node")).toHaveCount(
    clusters.reduce((sum, c) => sum + c.nodes.length, 0),
  );
  await expect(map.locator("[data-edge-id]")).toHaveCount(
    clusters.reduce((sum, c) => sum + c.edges.length, 0),
  );
  // NEW is a badge, not a filter: every snapshot cluster must remain on the map.
  expect(
    await map
      .locator(".document-cluster")
      .evaluateAll((elements) =>
        elements.map((element) => element.dataset.issueKey).sort(),
      ),
  ).toEqual(clusters.map((cluster) => cluster.issueKey).sort());
  const newKeys = clusters
    .filter((cluster) =>
      isNewIssue(
        cluster.firstDetectedAt,
        latest.meta.snapshotTs,
        latest.meta.newWindowHours,
      ),
    )
    .map((cluster) => cluster.issueKey)
    .sort();
  expect(newKeys.length).toBeGreaterThan(0);
  expect(newKeys.length).toBeLessThan(clusters.length);
  expect(
    await map
      .locator(".document-cluster__badge")
      .evaluateAll((badges) =>
        badges
          .map((badge) => badge.closest(".document-cluster").dataset.issueKey)
          .sort(),
      ),
  ).toEqual(newKeys);
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
    await page.getByLabel("캘린더에서 날짜 선택").fill(date);
    await expect(page.locator(".pulse-layout")).toHaveAttribute(
      "data-snapshot",
      timestamp(date),
    );
  }
  await page.getByLabel("캘린더에서 날짜 선택").fill("2026-01-01");
  await slider.focus();
  await page.keyboard.press("ArrowLeft");
  await expect(page.locator(".pulse-layout")).toHaveAttribute(
    "data-snapshot",
    timestamp("2025-12-31"),
  );
  await expect(map.locator(".document-cluster")).toHaveCount(
    snapshotAt("2025-12-31").data.clusters.length,
  );
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
  await page.getByLabel("캘린더에서 날짜 선택").fill("2025-09-01");
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

test("search and category controls align, and the calendar precedes the selected time", async ({
  page,
}) => {
  await page.goto("/#/pulse");
  const searchBounds = await page
    .locator(".pulse-controls .wp-search")
    .boundingBox();
  const otherBounds = await page
    .getByRole("button", { name: "기타", exact: true })
    .boundingBox();
  expect(searchBounds.x + searchBounds.width).toBeCloseTo(
    otherBounds.x + otherBounds.width,
    1,
  );
  const calendarBounds = await page
    .locator(".pulse-timeline__calendar")
    .boundingBox();
  const selectedTimeBounds = await page
    .locator(".pulse-timeline__selection strong")
    .boundingBox();
  expect(calendarBounds.x + calendarBounds.width).toBeLessThanOrEqual(
    selectedTimeBounds.x,
  );
});

test("dense map selection, filtering and desktop/mobile handoff", async ({
  page,
}) => {
  await page.goto("/#/pulse");
  const timeline = page.getByRole("region", { name: "스냅샷 시간 탐색" });
  await expect(timeline).toHaveAttribute("data-compact", "true");
  expect((await timeline.boundingBox()).height).toBeLessThan(75);
  await timeline.screenshot({
    path: "test-results/pulse-timeline-inline-desktop.png",
  });
  const panel = page.getByRole("complementary", { name: "선택한 사건" });
  await expect(panel).toHaveCount(0);
  const latest = snapshotAt(dates.at(-1));
  const clusters = latest.data.clusters;
  const technology = clusters.find(
    (cluster) => cluster.issueKey === "ai-chip-controls",
  );
  const world = clusters.find(
    (cluster) => cluster.issueKey === "iran-hormuz-2025",
  );
  const map = page.getByRole("region", { name: "사건 관계 지도" });
  await expect(map.locator(".document-node")).toHaveCount(
    clusters.reduce((sum, c) => sum + c.nodes.length, 0),
  );
  const node = map.locator(
    `.document-cluster[data-issue-key="${technology.issueKey}"] .document-node[data-page-id="${pageId(technology.nodes[0].pageId)}"]`,
  );
  const radius = await node.locator(".document-node__body").getAttribute("r");
  const position = await node.getAttribute("transform");
  const clusterPositions = () =>
    map
      .locator(".document-cluster")
      .evaluateAll((elements) =>
        elements.map((element) => element.getAttribute("transform")),
      );
  const originalPositions = await clusterPositions();
  await page.getByRole("button", { name: "기술", exact: true }).click();
  const topTechnology = clusters
    .filter((v) => v.category === "technology")
    .sort(
      (a, b) =>
        b.pulseScore - a.pulseScore || a.issueKey.localeCompare(b.issueKey),
    )[0];
  const center = map.locator('.document-cluster[data-rank="0"]');
  await expect(center).toHaveAttribute("transform", "translate(0 0)");
  await expect(center.locator(".document-cluster__title")).toContainText(
    topTechnology.label,
  );
  await expect(node).toHaveAttribute("transform", position);
  await expect(node.locator(".document-node__body")).toHaveAttribute(
    "r",
    radius,
  );
  await page.getByRole("button", { name: "전체", exact: true }).click();
  expect(await clusterPositions()).toEqual(originalPositions);
  await page.screenshot({
    path: "test-results/pulse-desktop.png",
    fullPage: true,
  });
  await page
    .locator(".pulse-cluster-list button")
    .filter({ hasText: technology.label })
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
  await panel.getByRole("button", { name: "클러스터 정보 닫기" }).click();
  await expect(panel).toHaveCount(0);
  await expect(
    map.locator('.document-cluster[data-selected="true"]'),
  ).toHaveCount(0);
  expect((await map.boundingBox()).width).toBeGreaterThan(
    (await page.locator(".pulse-layout").boundingBox()).width - 4,
  );
  // Offscreen clusters stay in the data but leave the map's tab order.
  await map
    .locator('.document-cluster[data-rendered="true"] .document-node')
    .first()
    .focus();
  await page.keyboard.press("Enter");
  await expect(panel).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect((await timeline.boundingBox()).height).toBeLessThan(115);
  await timeline.screenshot({
    path: "test-results/pulse-timeline-inline-mobile.png",
  });
  await page.getByRole("button", { name: "지도 위치 초기화" }).click();
  await page.screenshot({
    path: "test-results/pulse-mobile.png",
    fullPage: true,
  });
  await page
    .locator(".pulse-cluster-list button")
    .filter({ hasText: world.label })
    .click();
  await page
    .locator(".pulse-cluster-list button")
    .filter({ hasText: technology.label })
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
  const panelBounds = await page.locator(".pulse-preview").boundingBox(),
    graph = await map.boundingBox();
  expect(panelBounds.y).toBeGreaterThanOrEqual(graph.y + graph.height - 1);
  await panel.getByRole("button", { name: "클러스터 정보 닫기" }).click();
  await expect(panel).toHaveCount(0);
});
