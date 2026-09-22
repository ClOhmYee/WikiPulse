import { test, expect } from "@playwright/test";
import { mockClient } from "../src/data/mock/client.js";
import { makeStressMap } from "../src/data/mock/fixtures/pulse.js";
import { isNewIssue, kstTimestamp } from "../src/data/pulse/time.js";
import { serve } from "./server.js";

const snapshots = (await mockClient.listSnapshots()).data;
const pulseMaps = await Promise.all(
  snapshots
    .slice(-2)
    .map(({ source, snapshotTs }) =>
      mockClient.getPulseMap({ source, snapshotTs }),
    ),
);

test("fullscreen keeps timeline and exit usable during loading, errors and empty snapshots", async ({
  page,
}) => {
  let mode = "loading";
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  await serve(page, async ({ route, url }) => {
    if (
      !url.pathname.endsWith("/map") ||
      url.searchParams.get("snapshotTs") !== pulseMaps.at(-2).meta.snapshotTs
    )
      return false;
    if (mode === "loading") await gate;
    if (mode === "error") {
      await route.fulfill({
        status: 503,
        json: { error: { code: "UNAVAILABLE" } },
      });
    } else {
      const body = structuredClone(pulseMaps.at(-2));
      body.data.clusters = [];
      Object.assign(body.meta, {
        clusterCount: 0,
        nodeCount: 0,
        edgeCount: 0,
        truncated: false,
      });
      await route.fulfill({ json: body });
    }
    return true;
  });
  await page.goto("/#/pulse");
  await page
    .getByRole("button", { name: "펄스맵 전체화면", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "펄스맵 전체화면" });
  const slider = dialog.getByRole("slider", { name: "스냅샷 시각" });
  await dialog.getByRole("button", { name: "시간축 표시" }).hover();
  await dialog.getByRole("button", { name: "이전 시점" }).click();
  await expect(dialog.locator(".pulse-loading")).toBeVisible();
  await expect(slider).toBeInViewport();
  await expect(
    dialog.getByRole("button", { name: "전체화면 닫기" }),
  ).toBeInViewport();
  mode = "error";
  release();
  await expect(dialog.getByRole("alert")).toContainText(
    "이 시점의 지도를 불러오지 못했습니다",
  );
  await expect(slider).toBeInViewport();
  mode = "empty";
  await dialog.getByRole("button", { name: "지도 다시 불러오기" }).click();
  await expect(
    dialog.getByRole("heading", { name: "이 시점에 감지된 이슈가 없습니다" }),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "시간축 표시" }).hover();
  await expect(slider).toBeInViewport();
  await dialog.getByRole("button", { name: "최신으로 이동" }).click();
  await expect(dialog.locator(".document-map")).toHaveAttribute(
    "data-snapshot",
    pulseMaps.at(-1).meta.snapshotTs,
  );
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "이전 시점" }).click();
  await expect(
    dialog.getByRole("heading", { name: "이 시점에 감지된 이슈가 없습니다" }),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "전체화면 닫기" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("slider", { name: "스냅샷 시각" })).toBeFocused();
  expect(await page.evaluate(() => document.body.style.overflow)).not.toBe(
    "hidden",
  );
});
test("pulse uses the graph contract without downloading catalogue fixtures", async ({
  page,
}) => {
  const scripts = [];
  page.on("request", (request) => {
    if (request.resourceType() === "script") scripts.push(request.url());
  });
  const calls = await serve(page);
  await page.goto("/#/pulse");
  const latest = pulseMaps.at(-1);
  const clusters = latest.data.clusters;
  await expect(page.locator(".document-cluster")).toHaveCount(clusters.length);
  await expect(page.locator(".document-node")).toHaveCount(
    clusters.reduce((sum, c) => sum + c.nodes.length, 0),
  );
  await expect(page.locator("[data-edge-id]")).toHaveCount(
    clusters.reduce((sum, c) => sum + c.edges.length, 0),
  );
  expect(
    await page
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
    await page
      .locator(".document-cluster__badge")
      .evaluateAll((badges) =>
        badges
          .map((badge) => badge.closest(".document-cluster").dataset.issueKey)
          .sort(),
      ),
  ).toEqual(newKeys);
  await expect(page.locator(".pulse-cluster-list")).not.toContainText("HOT");
  await expect(
    page.getByRole("button", { name: "로그인", exact: true }),
  ).toBeVisible();
  expect(
    calls.filter((v) => v.pathname !== "/api/v1/me").map((v) => v.pathname),
  ).toEqual(["/api/v1/issues/snapshots", "/api/v1/issues/map"]);
  expect(scripts.some((v) => /data\/mock|fixtures\//.test(v))).toBe(false);
});
test("nullable graph labels and issue keys keep numeric detail navigation", async ({
  page,
}) => {
  const body = structuredClone(pulseMaps.at(-1));
  const cluster = body.data.clusters.find(
    (c) => c.issueKey === "ai-chip-controls",
  );
  // Nullable fallback and detail navigation must also work for non-NEW issues.
  expect(
    isNewIssue(
      cluster.firstDetectedAt,
      body.meta.snapshotTs,
      body.meta.newWindowHours,
    ),
  ).toBe(false);
  cluster.label = null;
  cluster.issueKey = null;
  const detail = (await mockClient.getIssue(cluster.id)).data;
  const calls = await serve(page, async ({ route, url }) => {
    if (!url.pathname.endsWith("/map")) return false;
    await route.fulfill({ json: body });
    return true;
  });
  await page.goto("/#/pulse");
  await page
    .locator(".pulse-cluster-list button")
    .filter({ hasText: cluster.nodes[0].title })
    .click();
  await expect(page.locator(".pulse-preview h2")).toHaveText(
    cluster.nodes[0].title,
  );
  const link = page.getByRole("link", {
    name: "이슈 리포트 보기",
    exact: true,
  });
  await expect(link).toHaveAttribute("href", `#/issues/${cluster.id}`);
  await link.click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    detail.label,
  );
  expect(calls.some((v) => v.pathname === `/api/v1/issues/${cluster.id}`)).toBe(
    true,
  );
});
test("rapid time changes discard a slower response and preserve graph/panel timestamp", async ({
  page,
}) => {
  let slowStarted;
  const started = new Promise((resolve) => {
    slowStarted = resolve;
  });
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  let finished;
  const served = new Promise((resolve) => {
    finished = resolve;
  });
  await serve(page, async ({ route, url }) => {
    if (
      !url.pathname.endsWith("/map") ||
      url.searchParams.get("snapshotTs") !== pulseMaps.at(-2).meta.snapshotTs
    )
      return false;
    slowStarted();
    await gate;
    await route.fulfill({ json: pulseMaps.at(-2) }).catch(() => {});
    finished();
    return true;
  });
  await page.goto("/#/pulse");
  await expect(page.locator(".document-node")).toHaveCount(
    pulseMaps.at(-1).data.clusters.reduce((sum, c) => sum + c.nodes.length, 0),
  );
  const target = pulseMaps
    .at(-1)
    .data.clusters.find((cluster) => cluster.issueKey === "winter-olympics");
  await page
    .locator(".pulse-cluster-list button")
    .filter({ hasText: target.label })
    .click();
  await expect(page.locator(".pulse-preview h2")).toHaveText(target.label);
  await page.getByRole("button", { name: "이전 시점" }).click();
  await started;
  await expect(page.locator(".pulse-loading")).toBeVisible();
  await page.getByRole("button", { name: "최신으로 이동" }).click();
  await expect(page.locator(".document-map")).toHaveAttribute(
    "data-snapshot",
    pulseMaps.at(-1).meta.snapshotTs,
  );
  release();
  await served;
  await expect(page.locator(".pulse-preview")).toHaveAttribute(
    "data-snapshot",
    pulseMaps.at(-1).meta.snapshotTs,
  );
  await expect(page.locator(".pulse-preview h2")).toHaveText(target.label);
  await expect(page.locator(".pulse-timeline")).toContainText(
    kstTimestamp(pulseMaps.at(-1).meta.snapshotTs),
  );
});
test("API error retries and mismatched or invalid graph data never masquerade as mock", async ({
  page,
}) => {
  let state = "error";
  await serve(page, async ({ route, url }) => {
    if (!url.pathname.endsWith("/map")) return false;
    if (state === "error") {
      await route.fulfill({
        status: 503,
        json: { error: { code: "UNAVAILABLE" } },
      });
      return true;
    }
    if (state === "invalid") {
      const body = structuredClone(pulseMaps.at(-1));
      body.data.clusters[0].edges[0].targetPageId = "missing";
      await route.fulfill({ json: body });
      return true;
    }
    return false;
  });
  await page.goto("/#/pulse");
  await expect(
    page.getByRole("heading", { name: "이 시점의 지도를 불러오지 못했습니다" }),
  ).toBeVisible();
  await expect(page.locator(".document-map")).toHaveCount(0);
  state = "invalid";
  await page.getByRole("button", { name: "지도 다시 불러오기" }).click();
  await expect(page.getByRole("alert")).toContainText("edge endpoints");
  state = "ok";
  await page.getByRole("button", { name: "지도 다시 불러오기" }).click();
  await expect(page.locator(".document-node")).toHaveCount(
    pulseMaps.at(-1).data.clusters.reduce((sum, c) => sum + c.nodes.length, 0),
  );
});
test("500 nodes and 1000 edges remain interactive in the browser", async ({
  page,
}) => {
  const stress = makeStressMap();
  delete stress.meta.dataMode;
  await serve(page, async ({ route, url }) => {
    if (!url.pathname.endsWith("/map")) return false;
    await route.fulfill({ json: stress });
    return true;
  });
  await page.goto("/#/pulse");
  await expect(page.locator(".document-node")).toHaveCount(500);
  await expect(page.locator("[data-edge-id]")).toHaveCount(1000);
  const started = Date.now();
  await page
    .locator(".pulse-cluster-list button")
    .filter({ hasText: "성능 검증 이슈 11" })
    .click();
  await page
    .locator(".pulse-preview .pulse-document")
    .filter({ hasText: "검증 문서 11-11" })
    .click();
  await expect(
    page.locator('.document-node[data-selected="true"]'),
  ).toHaveCount(1);
  await page.getByRole("button", { name: "지도 확대", exact: true }).click();
  expect(Date.now() - started).toBeLessThan(3000);
  await expect(page.locator(".pulse-preview")).toContainText("검증 문서 11-11");
});
