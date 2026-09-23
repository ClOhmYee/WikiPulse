import { test, expect } from "@playwright/test";

const toggle = (page) =>
  page.getByRole("button", { name: /모드 사용 중, .* 모드로 전환/ });
const theme = (page) => page.locator("html");

test("white page background covers the full scroll height on desktop and mobile", async ({
  page,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem("wikipulse.theme", "light"),
  );
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/#/issues");
    await expect(page.locator(".event-row").first()).toBeVisible();
    await page.evaluate(() =>
      scrollTo(0, document.documentElement.scrollHeight),
    );
    expect(await page.evaluate(() => scrollY)).toBeGreaterThan(844);
    expect((await page.locator(".workspace-header").boundingBox()).y).toBe(0);
    await expect(toggle(page)).toBeInViewport();
    await expect(theme(page)).toHaveCSS(
      "background-color",
      "rgb(243, 247, 255)",
    );
    await expect(page.locator(".workspace")).toHaveCSS(
      "background-color",
      "rgb(243, 247, 255)",
    );
    await toggle(page).click();
    await expect(theme(page)).toHaveAttribute("data-theme", "dark");
    expect((await page.locator(".workspace-header").boundingBox()).y).toBe(0);
    await toggle(page).click();
  }
});

test("pastel map keeps original gradient, halo and title layers", async ({
  page,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem("wikipulse.theme", "dark"),
  );
  await page.goto("/#/pulse");
  const map = page.locator(".document-map");
  await map
    .locator('.document-cluster[data-rank="0"]')
    .getByRole("button", { name: /클러스터 확대/ })
    .click();
  await expect(map).toHaveAttribute("data-overview", "false");
  const cluster = map.locator('.document-cluster[data-rank="0"]');
  const paints = () =>
    cluster.evaluate((el) =>
      Object.fromEntries(
        [
          ".document-node__body",
          ".document-node__halo",
          ".document-cluster__field",
          ".document-cluster__title-glow",
          ".document-cluster__title-shine",
        ].map((selector) => {
          const style = getComputedStyle(el.querySelector(selector));
          return [
            selector,
            {
              fill: style.fill,
              display: style.display,
              strokeWidth: style.strokeWidth,
            },
          ];
        }),
      ),
    );
  const original = await paints();
  await toggle(page).click();
  expect(await paints()).toEqual(original);
  const stop = map
    .locator("defs > g")
    .first()
    .locator("radialGradient")
    .first()
    .locator("stop")
    .first();
  await expect(stop).toHaveCSS("stop-color", "rgb(255, 255, 255)");
  await expect(map).toHaveCSS("background-color", "rgb(255, 255, 255)");
});

test("defaults white, remembers selection and keeps onboarding dark", async ({
  page,
}) => {
  await page.goto("/#/issues");
  await expect(theme(page)).toHaveAttribute("data-theme", "light");
  await toggle(page).focus();
  await page.keyboard.press("Enter");
  await expect(theme(page)).toHaveAttribute("data-theme", "dark");
  await expect(toggle(page)).toHaveAttribute("aria-pressed", "false");
  await page.reload();
  await expect(theme(page)).toHaveAttribute("data-theme", "dark");
  await page.goto("/#/stocks");
  await expect(theme(page)).toHaveAttribute("data-theme", "dark");
  await toggle(page).click();
  await page.goto("/#/");
  await expect(theme(page)).toHaveAttribute("data-theme", "dark");
  expect(
    await page.evaluate(() => localStorage.getItem("wikipulse.theme")),
  ).toBe("light");
  await page.goto("/#/issues");
  await expect(theme(page)).toHaveAttribute("data-theme", "light");
});

test("invalid and unavailable storage safely fall back, session toggling still works", async ({
  page,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem("wikipulse.theme", "invalid"),
  );
  await page.goto("/#/issues");
  await expect(theme(page)).toHaveAttribute("data-theme", "light");
  await page.addInitScript(() => {
    Storage.prototype.getItem = () => {
      throw new Error("storage blocked");
    };
    Storage.prototype.setItem = () => {
      throw new Error("storage blocked");
    };
  });
  await page.reload();
  await expect(theme(page)).toHaveAttribute("data-theme", "light");
  await toggle(page).click();
  await expect(theme(page)).toHaveAttribute("data-theme", "dark");
  await toggle(page).click();
  await expect(theme(page)).toHaveAttribute("data-theme", "light");
});

test("theme repaint preserves mounted map, camera, selection and snapshot", async ({
  page,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem("wikipulse.theme", "dark"),
  );
  await page.goto("/#/pulse");
  const map = page.locator(".document-map");
  await map
    .locator('.document-cluster[data-rank="0"]')
    .getByRole("button", { name: /클러스터 확대/ })
    .click();
  await expect(map).toHaveAttribute("data-overview", "false");
  await page.waitForTimeout(700);
  const selected = await map
    .locator('.document-cluster[data-selected="true"]')
    .getAttribute("data-issue-key");
  const before = await map.getAttribute("data-zoom");
  const snapshot = await page.getByRole("slider").inputValue();
  await map.evaluate((el) => {
    window.__themeMap = el;
  });
  const requests = [];
  page.on("request", (r) => {
    if (r.url().includes("/api/")) requests.push(r.url());
  });
  await toggle(page).click();
  await expect(theme(page)).toHaveAttribute("data-theme", "light");
  expect(await map.evaluate((el) => el === window.__themeMap)).toBe(true);
  await expect(map).toHaveAttribute("data-zoom", before);
  await expect(
    map.locator('.document-cluster[data-selected="true"]'),
  ).toHaveAttribute("data-issue-key", selected);
  await expect(page.getByRole("slider")).toHaveValue(snapshot);
  expect(requests).toEqual([]);
  await page
    .getByRole("button", { name: "펄스맵 전체화면", exact: true })
    .click();
  await expect(page.locator(".pulse-fullscreen")).toHaveCSS(
    "background-color",
    "rgb(255, 255, 255)",
  );
  await expect(page.locator(".document-map")).toHaveCSS(
    "background-color",
    "rgb(255, 255, 255)",
  );
  await page.keyboard.press("Escape");
  await expect(page.locator(".pulse-fullscreen")).toHaveCount(0);
});

test("search, filter and login input survive switching; mobile toggle stays reachable", async ({
  page,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem("wikipulse.theme", "dark"),
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#/issues");
  await page
    .getByRole("textbox", { name: "사건 검색", exact: true })
    .fill("반도체");
  await page
    .getByRole("combobox", { name: "분석 상태", exact: true })
    .selectOption({ index: 1 });
  const status = await page
    .getByRole("combobox", { name: "분석 상태", exact: true })
    .inputValue();
  await toggle(page).click();
  await expect(
    page.getByRole("textbox", { name: "사건 검색", exact: true }),
  ).toHaveValue("반도체");
  await expect(
    page.getByRole("combobox", { name: "분석 상태", exact: true }),
  ).toHaveValue(status);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  const input = page.locator('input[type="email"]');
  await input.fill("theme@example.com");
  // Native modal makes the header inert; exercise the same mounted toggle handler.
  await toggle(page).dispatchEvent("click");
  await expect(input).toHaveValue("theme@example.com");
  await expect(theme(page)).toHaveAttribute("data-theme", "dark");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
