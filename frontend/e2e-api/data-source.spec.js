import { test, expect } from "@playwright/test";
import { mockClient } from "../src/data/mock/client.js";
import { events, entities, stocks } from "../src/data/mock/fixtures/catalog.js";

const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function serve(page, override) {
  const calls = [];
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    calls.push(url);
    if (override && await override({ route, url, calls })) return;
    const [kind, id] = url.pathname.slice("/api/v1/".length).split("/").map(decodeURIComponent);
    const params = Object.fromEntries(url.searchParams);
    for (const key of ["offset", "limit"]) if (params[key] !== undefined) params[key] = Number(params[key]);
    // A deliberately small server page proves that every page is collected.
    if (["events", "entities", "stocks"].includes(kind) && !id) params.limit = Math.min(params.limit || 50, 2);
    try {
      const methods = { events: ["listEvents", "getEvent"], entities: ["listEntities", "getEntity"], stocks: ["listStocks", "getStock"] };
      const body = kind === "categories" ? await mockClient.listCategories()
        : kind === "search" ? await mockClient.searchWorkspace(params)
        : await mockClient[methods[kind][id ? 1 : 0]](id || params);
      await route.fulfill({ json: body });
    } catch (error) {
      await route.fulfill({ status: error.status || 500, json: { error: { code: error.code || "TEST_ERROR", message: error.message, details: [] } } });
    }
  });
  return calls;
}

test("same pages consume HTTP data including every list page and related objects", async ({ page }) => {
  const scripts = [];
  page.on("request", (request) => { if (request.resourceType() === "script") scripts.push(request.url()); });
  const calls = await serve(page);
  await page.goto("/#/explore");
  await expect(page.locator(".event-row")).toHaveCount(events.length);
  expect(calls.filter((url) => url.pathname === "/api/v1/events").map((url) => url.searchParams.get("offset"))).toEqual(["0", "2", "4"]);
  await expect(page.getByRole("button", { name: "데모 데이터" })).toBeVisible();
  for (const [path, title] of [
    [`/events/${events[0].id}`, events[0].title], [`/intelligence/${entities[0].id}`, entities[0].name],
    ["/stocks", "종목에서 사건의 맥락을 찾으세요."], [`/stocks/${stocks[0].symbol}`, stocks[0].name],
    [`/events/${events[0].id}/stocks`, "이 사건과 연결된 종목"],
  ]) {
    await page.goto(`/#${path}`);
    await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
  }
  expect(scripts.some((url) => /data\/mock|fixtures\/catalog|NodeField|OnboardingPage/.test(url))).toBe(false);
  await page.screenshot({ path: "test-results/api/desktop-stocks.png", fullPage: true });
});

test("server data changes reach the existing page and API transport does not imply LIVE", async ({ page }) => {
  await serve(page, async ({ route, url }) => {
    if (url.pathname !== `/api/v1/events/${events[0].id}`) return false;
    const body = await mockClient.getEvent(events[0].id);
    body.data.title = "서버에서 받은 사건 제목";
    body.meta.dataMode = "unverified";
    body.meta.asOf = "2026-09-08";
    await route.fulfill({ json: body }); return true;
  });
  await page.goto(`/#/events/${events[0].id}`);
  await expect(page.getByRole("heading", { name: "서버에서 받은 사건 제목", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "출처 확인 필요" })).toBeVisible();
  await expect(page.getByText("LIVE", { exact: true })).toHaveCount(0);
});

test("loading preserves saved IDs, 500 does not fall back, retry recovers", async ({ page }) => {
  let fail = true;
  await page.addInitScript((id) => localStorage.setItem("wikipulse.savedEvents", JSON.stringify([id, "missing-server-id"])), events[0].id);
  await serve(page, async ({ route, url }) => {
    if (url.pathname !== `/api/v1/events/${events[0].id}` || !fail) return false;
    await pause(500);
    await route.fulfill({ status: 500, json: { error: { code: "INTERNAL_ERROR" } } }); return true;
  });
  await page.goto(`/#/events/${events[0].id}`);
  await expect(page.getByRole("status", { name: "데이터 불러오는 중" })).toBeVisible();
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem("wikipulse.savedEvents")))).toEqual([events[0].id, "missing-server-id"]);
  await expect(page.getByRole("heading", { name: "데이터를 불러오지 못했습니다" })).toBeVisible();
  await expect(page.getByRole("heading", { name: events[0].title, exact: true })).toHaveCount(0);
  fail = false;
  await page.getByRole("button", { name: "다시 시도", exact: true }).click();
  await expect(page.getByRole("heading", { name: events[0].title, exact: true })).toBeVisible();
  await page.goto("/#/saved");
  await expect(page.locator(".event-row")).toHaveCount(1);
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem("wikipulse.savedEvents")))).toEqual([events[0].id, "missing-server-id"]);
});

test("empty lists, 404 and offline errors have distinct recovery states", async ({ page }) => {
  let offline = false;
  await serve(page, async ({ route, url }) => {
    if (url.pathname !== "/api/v1/events") return false;
    if (offline) { await route.abort("failed"); return true; }
    await route.fulfill({ json: await mockClient.listEvents({ q: "no-such-event" }) }); return true;
  });
  await page.goto("/#/explore");
  await expect(page.getByRole("heading", { name: "사건을 탐색하세요", exact: true })).toBeVisible();
  await expect(page.locator(".event-row")).toHaveCount(0);
  await page.goto("/#/events/missing");
  await expect(page.getByRole("heading", { name: "이벤트를 찾을 수 없어요" })).toBeVisible();
  offline = true;
  await page.goto("/#/explore");
  await expect(page.getByRole("heading", { name: "데이터를 불러오지 못했습니다" })).toBeVisible();
});

test("debounced search uses encoded query and ignores a slower previous response", async ({ page }) => {
  let oldStarted;
  const started = new Promise((resolve) => { oldStarted = resolve; });
  const calls = await serve(page, async ({ route, url }) => {
    if (url.pathname !== "/api/v1/search" || url.searchParams.get("q") !== "old & 한글") return false;
    oldStarted(); await pause(800);
    await route.fulfill({ json: { data: [{ kind: "event", id: "old", title: "이전 검색 결과", detail: "사건" }], meta: { dataMode: "mock" } } }); return true;
  });
  await page.goto("/#/explore");
  const search = page.getByRole("combobox", { name: "전체 검색", exact: true });
  await search.fill("old & 한글");
  await started;
  await search.fill("NVDA");
  await expect(page.getByRole("option", { name: /엔비디아/ })).toBeVisible();
  await pause(850);
  await expect(page.getByRole("option", { name: /이전 검색 결과/ })).toHaveCount(0);
  expect(calls.some((url) => url.searchParams.get("q") === "old & 한글")).toBe(true);
  await search.press("ArrowDown"); await search.press("Enter");
  await expect(page).toHaveURL(/#\/stocks\/NVDA$/);
});

test("rapid route change cannot be overwritten by an older detail response", async ({ page }) => {
  await serve(page, async ({ route, url }) => {
    if (url.pathname !== `/api/v1/events/${events[0].id}`) return false;
    await pause(700); await route.fulfill({ json: await mockClient.getEvent(events[0].id) }); return true;
  });
  await page.goto(`/#/events/${events[0].id}`);
  await page.evaluate((id) => { window.location.hash = `/events/${id}`; }, events[1].id);
  await expect(page.getByRole("heading", { name: events[1].title, exact: true })).toBeVisible();
  await pause(750);
  await expect(page.getByRole("heading", { name: events[0].title, exact: true })).toHaveCount(0);
});

test("mobile HTTP pages keep layout and local discussion performs no writes", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const methods = [];
  page.on("request", (request) => { if (request.url().includes("/api/v1/")) methods.push(request.method()); });
  await serve(page);
  await page.goto(`/#/events/${events[0].id}`);
  await expect(page.getByRole("heading", { name: events[0].title, exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "토론", exact: true }).click();
  const board = page.getByRole("region", { name: "이 사건에 대한 토론" });
  await expect(board).toBeVisible();
  await board.getByRole("textbox", { name: "내 의견 작성", exact: true }).fill("API 모드에서도 이 토론은 로컬에 저장됩니다.");
  await board.getByRole("button", { name: "토론 등록", exact: true }).click();
  await expect(board.getByText("API 모드에서도 이 토론은 로컬에 저장됩니다.", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  expect(methods.every((method) => method === "GET")).toBe(true);
  await page.screenshot({ path: "test-results/api/mobile-event.png", fullPage: true });
});
