import { test, expect } from "@playwright/test";
import { authenticate } from "../e2e/helpers/auth.js";
import { mockClient } from "../src/data/mock/client.js";
import { serve } from "./server.js";
const issue = (await mockClient.getIssue("iran-hormuz-2025")).data;
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

test("all sources includes replay confirmed issues alongside live detected issues", async ({
  page,
}) => {
  const times = {
    live: "2026-09-21T12:00:00Z",
    replay: "2025-06-13T00:00:00Z",
  };
  const cards = Object.entries(times).map(([source, snapshotTs], i) => ({
    id: 900 + i,
    label: `${source} filter regression`,
    source,
    snapshotTs,
    status: source === "live" ? "DETECTED" : "CONFIRMED",
    pulseScore: 10 + i,
    memberCount: 1,
    stockCount: i,
  }));
  await serve(page, async ({ route, url }) => {
    if (url.pathname === "/api/v1/issues/snapshots") {
      await route.fulfill({
        json: {
          data: cards
            .filter(
              (card) =>
                !url.searchParams.has("source") ||
                card.source === url.searchParams.get("source"),
            )
            .map((card) => ({
              source: card.source,
              snapshotTs: card.snapshotTs,
              clusterCount: 1,
            })),
        },
      });
      return true;
    }
    if (url.pathname !== "/api/v1/issues") return false;
    const source = url.searchParams.get("source") || "live";
    const status = url.searchParams.get("status");
    const data = cards.filter(
      (card) => card.source === source && (!status || card.status === status),
    );
    await route.fulfill({
      json: {
        data,
        meta: {
          snapshotTs: times[source],
          pagination: {
            offset: 0,
            limit: Number(url.searchParams.get("limit")),
            total: data.length,
            hasMore: false,
          },
        },
      },
    });
    return true;
  });
  await page.goto("/#/issues");
  await expect(page.locator(".event-row")).toHaveCount(2);
  await expect(page.locator(".event-row__title")).toHaveText([
    "live filter regression",
    "replay filter regression",
  ]);
  await expect(page.locator(".event-list")).not.toContainText("실시간 수집");
  await expect(page.locator(".event-list")).not.toContainText("과거 재구성");
  const status = page.getByRole("combobox", { name: "분석 상태", exact: true });
  await expect(
    page.getByRole("combobox", {
      name: "데이터 출처",
      exact: true,
    }),
  ).toHaveCount(0);
  await status.selectOption("CONFIRMED");
  await expect(page.locator(".event-row")).toHaveCount(1);
  await expect(page.locator(".event-row")).toContainText(
    "replay filter regression",
  );
  await status.selectOption("");
  await expect(page.locator(".event-row")).toHaveCount(2);
});

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
    .getByRole("combobox", { name: "분석 상태", exact: true })
    .selectOption("CONFIRMED");
  await expect.poll(() => calls.at(-1).searchParams.get("offset")).toBe("0");
  expect(calls.at(-1).searchParams.get("status")).toBe("CONFIRMED");
  expect(calls.at(-1).searchParams.get("snapshotTs")).toBe(snapshotTs);
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
              completeness: "pending",
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
  await expect(page.locator(".issue-summary p")).toHaveText(
    "이 시점의 요약이 제공되지 않았습니다.",
  );
  await page.getByRole("tab", { name: "탐색", exact: true }).click();
  await expect(page.locator(".dt-network-detail")).toContainText("0회");
  await expect(page.locator(".dt-network-detail")).toContainText("미제공");
  await expect(page.locator(".dt-network-detail")).toContainText(
    "입력을 기다리는 중",
  );
  await expect(page.getByText("시계열 미제공", { exact: true })).toBeVisible();
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
    page.getByRole("button", { name: "로그인", exact: true }),
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
    page.getByText("가격 데이터가 아직 준비되지 않았습니다", {
      exact: true,
    }),
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

test("empty list and missing detail differ; legacy local bookmarks stay untouched", async ({
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
  await authenticate(page);
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
    page.getByRole("heading", {
      name: "다음에 다시 보고 싶은 사건을 담아보세요",
    }),
  ).toBeVisible();
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

test("API detail exposes only server-backed report sections", async ({
  page,
}) => {
  await serve(page);
  await page.goto(`/#/issues/${issue.id}`);
  await expect(page.getByRole("tab")).toHaveCount(3);
  await expect(page.getByRole("tab").first()).toHaveText("리포트");
  await expect(page.getByRole("tab", { name: /^근거 문서/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: "타임라인" })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "관련 소식" })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "토론" })).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "토론 참여하기", exact: true }),
  ).toHaveCount(0);
  await expect(page.getByRole("link", { name: /^연관 주식/ })).toBeVisible();
});
