import { test, expect } from "@playwright/test";
import { mockClient } from "../src/data/mock/client.js";
import { serve } from "./server.js";
const issue = (await mockClient.getIssue("iran-hormuz-2025")).data;
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

test("HTTP lists request one page at a time and reset offset on filters", async ({
  page,
}) => {
  const calls = await serve(page);
  await page.goto("/#/issues");
  await expect(page.locator(".event-row")).toHaveCount(20);
  expect(calls.filter((url) => url.pathname === "/api/v1/issues")).toHaveLength(
    1,
  );
  await page.getByRole("button", { name: "다음 페이지", exact: true }).click();
  await expect(page.locator(".event-row")).toHaveCount(16);
  expect(calls.at(-1).searchParams.get("offset")).toBe("20");
  const snapshotTs = (await mockClient.listIssues()).meta.snapshotTs;
  expect(calls.at(-1).searchParams.get("snapshotTs")).toBe(snapshotTs);
  await page
    .getByRole("combobox", { name: "AI 검증 상태", exact: true })
    .selectOption("CONFIRMED");
  await expect.poll(() => calls.at(-1).searchParams.get("offset")).toBe("0");
  expect(calls.at(-1).searchParams.get("status")).toBe("CONFIRMED");
  expect(calls.at(-1).searchParams.has("snapshotTs")).toBe(false);
  await page
    .getByRole("combobox", { name: "데이터 출처", exact: true })
    .selectOption("replay");
  await expect.poll(() => calls.at(-1).pathname).toBe("/api/v1/issues");
  await expect
    .poll(() => calls.at(-1).searchParams.get("source"))
    .toBe("replay");
  expect(calls.at(-1).searchParams.get("snapshotTs")).toBe(snapshotTs);
  expect(
    calls.some(
      (url) =>
        url.pathname === "/api/v1/issues/snapshots" &&
        url.searchParams.get("source") === "replay",
    ),
  ).toBe(true);
  expect(
    calls.every(
      (url) => !/events|entities|categories|search/.test(url.pathname),
    ),
  ).toBe(true);
});

test("nullable and omitted DTO fields retain zero and never invent charts or verification", async ({
  page,
}) => {
  await serve(page, async ({ route, url }) => {
    if (url.pathname !== "/api/v1/issues/900") return false;
    await route.fulfill({
      json: {
        data: {
          id: 900,
          pulseScore: 2.7,
          status: "VERIFYING",
          source: "replay",
          snapshotTs: "2025-06-12T04:00:00Z",
          members: [
            {
              pageId: 901,
              wiki: "enwiki",
              title: "Zero Page",
              weight: 1,
              isSeed: true,
              views: 0,
            },
          ],
          relatedStocks: [],
        },
      },
    });
    return true;
  });
  await page.goto("/#/issues/900");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Zero Page");
  await expect(page.locator(".dt-event-header .issue-state")).toHaveAttribute(
    "data-status",
    "VERIFYING",
  );
  await expect(page.locator(".dt-network-detail")).toContainText("0회");
  await expect(page.locator(".dt-network-detail")).toContainText("미제공");
  await expect(page.getByText("시계열 미제공", { exact: true })).toBeVisible();
  await expect(page.locator(".dt-lede")).toContainText(
    "제공된 요약이 없습니다",
  );
});

test("API detail and related stock paths use numeric IDs without loading mock bundles", async ({
  page,
}) => {
  const scripts = [];
  page.on("request", (request) => {
    if (request.resourceType() === "script") scripts.push(request.url());
  });
  const calls = await serve(page);
  await page.goto(`/#/issues/${issue.id}`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(issue.label);
  await expect(
    page.getByRole("button", { name: "API 데이터", exact: true }),
  ).toBeVisible();
  await page
    .locator(".dt-report-actions")
    .getByRole("link", { name: /^연관 주식/ })
    .click();
  await expect(page.locator(".st-stock-row").first()).toBeVisible();
  expect(
    calls.some(
      (url) =>
        url.pathname === `/api/v1/issues/${issue.id}/stocks` &&
        url.searchParams.get("limit") === "100",
    ),
  ).toBe(true);
  const stock = issue.relatedStocks[0];
  await page
    .locator(".st-stock-identity")
    .filter({ hasText: stock.ticker })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(stock.name);
  await expect(
    page.getByText("가격 자료 미제공", { exact: true }),
  ).toBeVisible();
  expect(
    calls.some(
      (url) => url.pathname === `/api/v1/stocks/${stock.ticker}/issues`,
    ),
  ).toBe(true);
  expect(scripts.some((url) => /data\/mock|fixtures\//.test(url))).toBe(false);
});

test("500, malformed responses and network failures expose retry instead of mock fallback", async ({
  page,
}) => {
  let state = "500";
  await serve(page, async ({ route, url }) => {
    if (url.pathname !== "/api/v1/stocks") return false;
    if (state === "500")
      await route.fulfill({
        status: 500,
        json: {
          error: { code: "INTERNAL", message: "private database error" },
        },
      });
    else if (state === "invalid")
      await route.fulfill({ json: { data: [{ ticker: "BAD" }] } });
    else if (state === "offline") await route.abort("failed");
    else return false;
    return true;
  });
  await page.goto("/#/stocks");
  await expect(
    page.getByRole("heading", { name: "데이터를 불러오지 못했습니다" }),
  ).toBeVisible();
  await expect(page.getByRole("main")).not.toContainText(
    "private database error",
  );
  await expect(page.locator(".st-stock-row")).toHaveCount(0);
  for (const next of ["invalid", "offline"]) {
    state = next;
    await page.getByRole("button", { name: "다시 시도", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "데이터를 불러오지 못했습니다" }),
    ).toBeVisible();
  }
  state = "ok";
  await page.getByRole("button", { name: "다시 시도", exact: true }).click();
  await expect(page.locator(".st-stock-row")).toHaveCount(20);
});

test("empty list and missing detail are different states and preserve API bookmarks", async ({
  page,
}) => {
  await page.addInitScript(() => {
    localStorage.setItem(
      "wikipulse.api.savedEvents",
      JSON.stringify(["missing"]),
    );
    localStorage.setItem(
      "wikipulse.savedEvents",
      JSON.stringify(["iran-hormuz-2025"]),
    );
  });
  await serve(page);
  await page.goto("/#/stocks");
  await page
    .getByRole("textbox", { name: "종목 검색", exact: true })
    .fill("no-such-stock");
  await page.getByRole("button", { name: "검색 적용", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "조건에 맞는 종목이 없습니다." }),
  ).toBeVisible();
  await page.goto("/#/issues/999999999");
  await expect(
    page.getByRole("heading", { name: "이벤트를 찾을 수 없어요" }),
  ).toBeVisible();
  await page.goto("/#/saved");
  await expect(
    page.getByRole("region", { name: "조회할 수 없는 저장 항목" }),
  ).toContainText("missing");
  await expect(page.locator(".event-row")).toHaveCount(0);
  expect(
    await page.evaluate(() =>
      JSON.parse(localStorage.getItem("wikipulse.savedEvents")),
    ),
  ).toEqual(["iran-hormuz-2025"]);
});

test("quick stock search ignores a slow prior response and only calls supported stock search", async ({
  page,
}) => {
  let oldFinished = false;
  const calls = await serve(page, async ({ route, url }) => {
    if (
      url.pathname !== "/api/v1/stocks" ||
      url.searchParams.get("q") !== "old"
    )
      return false;
    await pause(900);
    await route
      .fulfill({
        json: {
          data: [
            {
              ticker: "OLD",
              name: "Old result",
              exchange: "NASDAQ",
              sector: null,
              issueCount: 0,
            },
          ],
          meta: {
            pagination: { offset: 0, limit: 7, total: 1, hasMore: false },
          },
        },
      })
      .catch(() => {});
    oldFinished = true;
    return true;
  });
  await page.goto("/#/issues");
  const search = page.getByRole("combobox", {
    name: "빠른 종목 검색",
    exact: true,
  });
  await search.fill("old");
  await expect
    .poll(() => calls.some((url) => url.searchParams.get("q") === "old"))
    .toBe(true);
  await search.fill("NVDA");
  const results = page.getByRole("listbox", { name: "빠른 종목 검색 결과" });
  await expect(results.getByRole("option")).toContainText("NVDA");
  await expect.poll(() => oldFinished).toBe(true);
  await expect(results.getByRole("option")).not.toContainText("Old result");
  expect(
    calls
      .filter((url) => url.searchParams.has("q"))
      .every((url) => url.pathname === "/api/v1/stocks"),
  ).toBe(true);
});

test("API local discussion starts empty, sends no writes, and isolates mock storage", async ({
  page,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem("wikipulse.savedStocks", JSON.stringify(["NVDA"])),
  );
  const writes = [];
  page.on("request", (request) => {
    if (request.method() !== "GET") writes.push(request.url());
  });
  await serve(page);
  await page.goto(`/#/issues/${issue.id}`);
  await page
    .getByRole("button", { name: "토론 참여하기", exact: true })
    .click();
  const board = page.getByRole("region", { name: "이 사건에 대한 토론" });
  await expect(board.locator(".dc-thread")).toHaveCount(0);
  await board
    .getByRole("textbox", { name: "내 의견 작성", exact: true })
    .fill("API 응답을 읽으며 남긴 로컬 의견");
  await board.getByRole("button", { name: "토론 등록", exact: true }).click();
  await expect(board.locator(".dc-thread")).toHaveCount(1);
  await page.reload();
  await page
    .getByRole("button", { name: "토론 참여하기", exact: true })
    .click();
  await expect(
    page.getByText("API 응답을 읽으며 남긴 로컬 의견", { exact: true }),
  ).toBeVisible();
  const keys = await page.evaluate(() => Object.keys(localStorage));
  expect(keys.some((key) => key.startsWith("wikipulse.api.discussion."))).toBe(
    true,
  );
  expect(keys.some((key) => key.startsWith("wikipulse.discussion."))).toBe(
    false,
  );
  expect(writes).toEqual([]);
});
