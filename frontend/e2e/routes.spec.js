import { test, expect } from "@playwright/test";
import { events } from "../src/data/mock/fixtures/catalog.js";

test("account routes are separate, reloadable and reachable without pretending to authenticate", async ({
  page,
}) => {
  const requests = [];
  page.on("request", (request) => {
    if (request.method() !== "GET") requests.push(request.url());
  });
  await page.goto("/#/pulse");
  await page
    .getByRole("navigation", { name: "주 메뉴" })
    .getByRole("link", { name: "마이페이지" })
    .click();
  for (const [route, title, next] of [
    ["/mypage", "마이페이지", "로그인 페이지"],
    ["/login", "로그인", "회원가입 페이지"],
    ["/signup", "회원가입", "로그인 페이지"],
  ]) {
    await expect(page).toHaveURL(new RegExp(`#${route}$`));
    await page.reload();
    await expect(
      page.getByRole("heading", { level: 1, name: title, exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "준비 중입니다" }),
    ).toBeVisible();
    await expect(page.locator("input[type=password]")).toHaveCount(0);
    await page
      .getByRole("main")
      .getByRole("link", { name: next, exact: true })
      .click();
  }
  expect(requests).toEqual([]);
});

test("direct stock URLs normalize case and slashes while preserving queries and reloads", async ({
  page,
}) => {
  await page.goto("/#/stocks/nvda/?q=a%2Fb&range=7");
  await expect(page).toHaveURL(/#\/stocks\/NVDA\?q=a%2Fb&range=7$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "엔비디아", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(page).toHaveURL(/#\/stocks\/NVDA\?q=a%2Fb&range=7$/);
});

test("removed page paths recover and reports keep source links without internal document destinations", async ({
  page,
}) => {
  test.setTimeout(90000);
  for (const route of [
    "/intelligence/strait-of-hormuz",
    "/explore",
    "/events/iran-hormuz-2025",
    "/onboarding",
  ]) {
    await page.goto(`/#${route}`);
    await expect(
      page.getByRole("heading", { name: "페이지를 찾을 수 없습니다" }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Pulse Map으로 이동" }),
    ).toHaveAttribute("href", "#/pulse");
  }
  const representatives = events.filter(
    (event, index) => !event.id.includes("--") || index % 36 === 0,
  );
  for (const event of representatives) {
    await page.goto(`/#/issues/${event.id}`);
    await expect(
      page.getByRole("heading", { level: 1, name: event.title, exact: true }),
    ).toBeVisible();
    await expect(
      page.locator(
        'a[href^="#/intelligence"], a[href^="#/events"], a[href^="#/explore"]',
      ),
    ).toHaveCount(0);
    await page.getByRole("tab", { name: /^근거 문서/ }).click();
    for (const link of await page.locator(".dt-evidence-row").all()) {
      await expect(link).toHaveAttribute(
        "href",
        /^https:\/\/en\.wikipedia\.org\/wiki\//,
      );
      await expect(link).toHaveAttribute("target", "_blank");
    }
  }
});

test("mobile account navigation and stock search results remain usable", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#/issues");
  const search = page.getByRole("combobox", {
    name: "빠른 종목 검색",
    exact: true,
  });
  await search.fill("NVDA");
  await expect(page.getByRole("listbox")).toBeVisible();
  await expect(page.getByText("검색 중…", { exact: true })).toHaveCount(0);
  await expect(page.locator('a[href^="#/intelligence"]')).toHaveCount(0);
  await page.keyboard.press("Escape");
  await page
    .getByRole("navigation", { name: "주 메뉴" })
    .getByRole("link", { name: "마이페이지" })
    .click();
  await expect(
    page.getByRole("heading", { level: 1, name: "마이페이지" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/routes-mobile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole("link", { name: "로그인 페이지", exact: true }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "로그인", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/routes-desktop.png",
    fullPage: true,
  });
});
