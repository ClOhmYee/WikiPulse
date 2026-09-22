import { authenticate } from "./helpers/auth.js";
import { test, expect } from "@playwright/test";
import { mockClient } from "../src/data/mock/client.js";
test.beforeEach(async ({ page }) => {
  await authenticate(page);
});
const issue = (await mockClient.getIssue("iran-hormuz-2025")).data;

test("missing stored IDs remain removable and valid saved entries survive", async ({
  page,
}) => {
  await page.addInitScript(
    ({ id }) => {
      localStorage.setItem(
        "wikipulse.savedEvents",
        JSON.stringify([id, id, "not-found-issue"]),
      );
      localStorage.setItem(
        "wikipulse.savedStocks",
        JSON.stringify(["NVDA", "not-found-stock"]),
      );
    },
    { id: String(issue.id) },
  );
  await page.goto("/#/saved");
  await expect(page.locator(".event-row")).toHaveCount(1);
  await expect(
    page.getByRole("region", { name: "조회할 수 없는 저장 항목" }),
  ).toContainText("not-found-issue");
  await page
    .getByRole("button", { name: "not-found-issue 저장 해제", exact: true })
    .click();
  await expect(
    page.getByRole("button", {
      name: "not-found-issue 저장 해제",
      exact: true,
    }),
  ).toHaveCount(0);
  await expect(page.locator(".event-row")).toHaveCount(1);
});

test("legacy and canonical saved aliases are removed together", async ({
  page,
}) => {
  await page.addInitScript(
    ({ id }) => {
      localStorage.setItem(
        "wikipulse.savedEvents",
        JSON.stringify([id, "iran-hormuz-2025"]),
      );
    },
    { id: String(issue.id) },
  );
  await page.goto("/#/saved");
  await expect(page.locator(".event-row")).toHaveCount(1);
  await page
    .getByRole("button", { name: `${issue.label} 저장 해제`, exact: true })
    .click();
  await expect(page.locator(".event-row")).toHaveCount(0);
  expect(
    await page.evaluate(() =>
      JSON.parse(localStorage.getItem("wikipulse.savedEvents")),
    ),
  ).toEqual([]);
});

test("storage failures preserve a usable session bookmark", async ({
  page,
}) => {
  await page.addInitScript(() => {
    Storage.prototype.setItem = () => {
      throw new DOMException("full", "QuotaExceededError");
    };
  });
  await page.goto(`/#/issues/${issue.id}`);
  await page.getByRole("button", { name: "이벤트 저장", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "저장됨", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".workspace-toast")).toContainText(
    "브라우저 저장 공간",
  );
  await page
    .getByRole("navigation", { name: "주 메뉴" })
    .getByRole("link", { name: "보관함", exact: true })
    .click();
  await expect(page.locator(".event-row")).toHaveCount(1);
});

test("hash query bytes survive reload and local title search declares its scope", async ({
  page,
}) => {
  const query = "AI & 기술? + 공급망";
  await page.goto(`/#/issues?q=${encodeURIComponent(query)}`);
  await expect(
    page.getByRole("textbox", { name: "사건 검색", exact: true }),
  ).toHaveValue(query);
  await expect(
    page.getByRole("heading", {
      name: "현재 페이지에서 일치하는 사건이 없습니다",
    }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("textbox", { name: "사건 검색", exact: true }),
  ).toHaveValue(query);
  await page.getByRole("button", { name: "필터 초기화", exact: true }).click();
  await expect(page.locator(".event-row")).toHaveCount(20);
});

test("tablet navigation retains all five destinations", async ({ page }) => {
  await page.setViewportSize({ width: 820, height: 1180 });
  await page.goto("/#/pulse");
  const nav = page.getByRole("navigation", { name: "주 메뉴" });
  for (const [name, route] of [
    ["이슈 탐색", "/issues"],
    ["마이페이지", "/mypage"],
    ["종목 탐색", "/stocks"],
    ["보관함", "/saved"],
    ["Pulse Map", "/pulse"],
  ]) {
    await nav.getByRole("link", { name, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`#${route}$`));
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth - innerWidth,
      ),
    ).toBeLessThanOrEqual(1);
  }
});

test("WebGL-unavailable onboarding retains a keyboard-operable exit", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type, ...args) {
      return /webgl/i.test(type) ? null : original.call(this, type, ...args);
    };
  });
  await page.goto("/");
  await expect(page.locator(".fallback-experience")).toBeVisible();
  for (const scene of ["Track", "Cluster", "Match"])
    await expect(
      page.getByRole("heading", { name: new RegExp(`^${scene}\\.?$`) }),
    ).toBeVisible();
  await page
    .getByRole("link", { name: "Pulse Map 시작하기", exact: true })
    .focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#\/pulse$/);
});
