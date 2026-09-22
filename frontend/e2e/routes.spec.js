import { test, expect } from "@playwright/test";
import { events } from "../src/data/mock/fixtures/catalog.js";

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
