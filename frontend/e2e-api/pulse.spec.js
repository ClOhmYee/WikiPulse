import { test, expect } from "@playwright/test";
import { mockClient } from "../src/data/mock/client.js";
import { makeStressMap } from "../src/data/mock/fixtures/pulse.js";
import { kstTimestamp } from "../src/data/pulse/time.js";
import { serve } from "./server.js";

const snapshots = (await mockClient.listSnapshots()).data;
const pulseMaps = await Promise.all(
  snapshots
    .slice(-2)
    .map(({ source, snapshotTs }) =>
      mockClient.getPulseMap({ source, snapshotTs }),
    ),
);
test("pulse uses the graph contract without downloading catalogue fixtures", async ({
  page,
}) => {
  const scripts = [];
  page.on("request", (request) => {
    if (request.resourceType() === "script") scripts.push(request.url());
  });
  const calls = await serve(page);
  await page.goto("/#/pulse");
  await expect(page.locator(".document-node")).toHaveCount(
    pulseMaps.at(-1).meta.nodeCount,
  );
  await expect(
    page.getByRole("button", { name: "API 데이터", exact: true }),
  ).toBeVisible();
  expect(calls.map((v) => v.pathname)).toEqual([
    "/api/v1/issues/snapshots",
    "/api/v1/issues/map",
  ]);
  expect(scripts.some((v) => /data\/mock|fixtures\//.test(v))).toBe(false);
});
test("nullable graph labels and issue keys keep numeric detail navigation", async ({
  page,
}) => {
  const body = structuredClone(pulseMaps.at(-1));
  const cluster = body.data.clusters[0];
  cluster.label = null;
  cluster.issueKey = null;
  const detail = (await mockClient.getIssue(cluster.id)).data;
  const calls = await serve(page, async ({ route, url }) => {
    if (!url.pathname.endsWith("/map")) return false;
    await route.fulfill({ json: body });
    return true;
  });
  await page.goto("/#/pulse");
  await page.locator(".pulse-cluster-list button").first().click();
  await expect(page.locator(".pulse-preview h2")).toHaveText(
    cluster.nodes[0].title,
  );
  const link = page.getByRole("link", {
    name: "사건 자세히 보기",
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
    pulseMaps.at(-1).meta.nodeCount,
  );
  await page.locator(".pulse-cluster-list button").first().click();
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
    pulseMaps.at(-1).meta.nodeCount,
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
  await page.locator(".pulse-cluster-list button").nth(10).click();
  await page.locator(".pulse-preview .pulse-document").nth(10).click();
  await expect(
    page.locator('.document-node[data-selected="true"]'),
  ).toHaveCount(1);
  await page.getByRole("button", { name: "지도 확대", exact: true }).click();
  expect(Date.now() - started).toBeLessThan(3000);
  await expect(page.locator(".pulse-preview")).toContainText("검증 문서 11-11");
});
