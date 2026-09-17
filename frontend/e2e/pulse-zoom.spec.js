import { test, expect } from "@playwright/test";
import {
  dates,
  timestamp,
  snapshotAt,
} from "../src/data/mock/fixtures/history.js";

const minimum = 0.08 * 1.4 ** 4;
const maximum = 4 / 1.4 ** 3;
const initialZoom = 1 / 1.2;
const zoom = (map) => map.getAttribute("data-zoom").then(Number);

for (const width of [1440, 390]) {
  test(`camera stays synchronized across fullscreen transitions at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/#/pulse");
    const map = page.locator(".document-map");
    const svg = map.locator("svg[role=group]");
    const readView = () =>
      svg.evaluate((element) => {
        const bounds = element.getBoundingClientRect();
        const matrix = element.querySelector(":scope > g").getScreenCTM();
        const center = new DOMPoint(
          bounds.x + bounds.width / 2,
          bounds.y + bounds.height / 2,
        ).matrixTransform(matrix.inverse());
        return {
          zoom: matrix.a / 0.85,
          x: center.x,
          y: center.y,
        };
      });
    const expectView = async (expected) => {
      await expect
        .poll(async () => {
          const actual = await readView();
          return Math.max(
            Math.abs(actual.zoom - expected.zoom),
            Math.abs(actual.x - expected.x),
            Math.abs(actual.y - expected.y),
          );
        })
        .toBeLessThan(0.01);
    };
    for (const selected of [false, true]) {
      if (selected) {
        const beforeSelection = await readView();
        await map
          .locator('.document-cluster[data-rank="0"] > [role="button"]')
          .first()
          .focus();
        await page.keyboard.press("Enter");
        await expect(
          page.getByRole("complementary", { name: "선택한 사건" }),
        ).toBeVisible();
        await expectView(beforeSelection);
      }
      await map.getByRole("button", { name: "지도 확대", exact: true }).click();
      await page.waitForTimeout(800);
      await svg.focus();
      await page.keyboard.press("ArrowLeft");
      await page.keyboard.press("ArrowDown");
      const inlineView = await readView();
      await page.evaluate(() => {
        window.transitionSamples = [];
        const sample = () => {
          const map = document.querySelector(".document-map");
          const matrix = map?.querySelector("svg > g")?.getScreenCTM();
          if (matrix)
            window.transitionSamples.push(matrix.a / Number(map.dataset.zoom));
          if (window.transitionSamples.length < 30)
            requestAnimationFrame(sample);
        };
        requestAnimationFrame(sample);
      });
      await map
        .getByRole("button", { name: "펄스맵 전체화면", exact: true })
        .click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await expectView(inlineView);
      await expect
        .poll(() => page.evaluate(() => window.transitionSamples.length))
        .toBe(30);
      expect(
        await page.evaluate(() =>
          Math.max(
            ...window.transitionSamples.map((scale) => Math.abs(scale - 0.85)),
          ),
        ),
      ).toBeLessThan(0.001);
      await map.getByRole("button", { name: "지도 축소", exact: true }).click();
      await page.waitForTimeout(800);
      await svg.focus();
      await page.keyboard.press("ArrowRight");
      await page.keyboard.press("ArrowUp");
      const fullscreenView = await readView();
      if (selected) await page.keyboard.press("Escape");
      else await map.getByRole("button", { name: "전체화면 닫기" }).click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expectView(fullscreenView);
      await page.waitForTimeout(150);
      await expectView(fullscreenView);
    }
  });
}

test("top timeline slides over the map, hides after leaving and stays open for keyboard use", async ({
  page,
}) => {
  await page.goto("/#/pulse");
  await page
    .getByRole("button", { name: "펄스맵 전체화면", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  const trigger = dialog.getByRole("button", { name: "시간축 표시" });
  const drawer = dialog.locator(".pulse-fullscreen__time-drawer");
  const map = dialog.locator(".document-map");
  const before = await map.boundingBox();
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
  await expect(drawer).toHaveAttribute("inert", "");
  await expect(
    page.getByText(
      "데모 데이터 · 이슈·문서 지표·연결 근거는 화면 체험을 위한 합성 예시입니다.",
    ),
  ).toHaveCount(0);
  await trigger.hover();
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  await expect(drawer).toHaveCSS("transform", "matrix(1, 0, 0, 1, 0, 0)");
  expect((await drawer.boundingBox()).height).toBeLessThan(130);
  const categories = drawer.getByRole("group", { name: "사건 주제" });
  await categories.getByRole("button", { name: "기술", exact: true }).click();
  const topTechnology = snapshotAt(dates.at(-1))
    .data.clusters.filter((v) => v.category === "technology")
    .sort(
      (a, b) =>
        b.pulseScore - a.pulseScore || a.issueKey.localeCompare(b.issueKey),
    )[0];
  const center = map.locator('.document-cluster[data-rank="0"]');
  await expect(center).toHaveAttribute("transform", "translate(0 0)");
  await expect(center.locator(".document-cluster__title")).toContainText(
    topTechnology.label,
  );
  await expect(map.locator(".document-cluster")).toHaveCount(
    snapshotAt(dates.at(-1)).data.clusters.filter(
      (v) => v.category === "technology",
    ).length,
  );
  await expect(
    categories.getByRole("button", { name: "기술", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await categories.getByRole("button", { name: "전체", exact: true }).click();
  expect((await map.boundingBox()).height).toBeCloseTo(before.height, 1);
  const slider = dialog.getByRole("slider", { name: "스냅샷 시각" });
  await slider.hover();
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  await page.screenshot({
    path: "test-results/pulse-timeline-top-desktop.png",
  });
  await map.getByRole("group").hover();
  await page.waitForTimeout(250);
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  // Re-entry cancels the pending dismissal.
  await trigger.hover();
  await page.waitForTimeout(950);
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  await map.getByRole("group").hover();
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
  await expect(drawer).toBeHidden();
  expect((await map.boundingBox()).height).toBeCloseTo(before.height, 1);
  await page.screenshot({ path: "test-results/pulse-timeline-top-hidden.png" });
  await trigger.focus();
  await page.keyboard.press("Tab");
  await expect(dialog.getByRole("button", { name: "이전 시점" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(slider).toBeFocused();
  await page.waitForTimeout(1200);
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  await page.keyboard.press("ArrowLeft");
  await expect(dialog.locator(".pulse-layout")).toHaveAttribute(
    "data-snapshot",
    timestamp(dates.at(-2)),
  );
  await dialog.getByRole("button", { name: "전체화면 닫기" }).focus();
  await expect(drawer).toBeHidden();
  await trigger.hover();
  await categories.getByRole("button", { name: "기술", exact: true }).click();
  await page.keyboard.press("Escape");
  await expect(
    page
      .getByRole("group", { name: "사건 주제" })
      .getByRole("button", { name: "기술", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
});

test.describe("touch timeline", () => {
  test.use({ hasTouch: true, viewport: { width: 390, height: 844 } });
  test("tap reveals controls and tapping the map dismisses them with reduced motion", async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/#/pulse");
    await page
      .getByRole("button", { name: "펄스맵 전체화면", exact: true })
      .tap();
    const dialog = page.getByRole("dialog");
    const trigger = dialog.getByRole("button", { name: "시간축 표시" });
    await trigger.tap();
    const drawer = dialog.locator(".pulse-fullscreen__time-drawer");
    expect(
      await drawer.evaluate((element) =>
        parseFloat(getComputedStyle(element).transitionDuration),
      ),
    ).toBeLessThan(0.001);
    await expect(dialog.getByRole("slider")).toBeInViewport();
    expect((await drawer.boundingBox()).height).toBeLessThan(175);
    const categories = drawer.getByRole("group", { name: "사건 주제" });
    await categories.getByRole("button", { name: "기타", exact: true }).tap();
    await expect(
      categories.getByRole("button", { name: "기타", exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
    await categories.getByRole("button", { name: "전체", exact: true }).tap();
    await page.screenshot({
      path: "test-results/pulse-timeline-top-touch.png",
    });
    await dialog.getByRole("button", { name: "이전 시점" }).tap();
    await expect(dialog.locator(".pulse-layout")).toHaveAttribute(
      "data-snapshot",
      timestamp(dates.at(-2)),
    );
    await dialog
      .locator(".document-map > svg")
      .tap({ position: { x: 20, y: 220 } });
    await expect(drawer).toBeHidden();
    await trigger.tap();
    await expect(drawer).toBeVisible();
  });
});

for (const fullscreen of [false, true]) {
  test(`${fullscreen ? "fullscreen" : "inline"} wheel zoom is continuous, anchored and bounded with readable labels`, async ({
    page,
  }) => {
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("/#/pulse");
    if (fullscreen)
      await page
        .getByRole("button", { name: "펄스맵 전체화면", exact: true })
        .click();
    const map = page.getByRole("region", { name: "사건 관계 지도" });
    const svg = map.getByRole("group", { name: "이슈와 문서 관계 그래프" });
    await svg.scrollIntoViewIfNeeded();
    await expect.poll(() => zoom(map)).toBe(initialZoom);
    const bounds = await svg.boundingBox();
    const pointer = {
      x: bounds.x + bounds.width * 0.62,
      y: bounds.y + bounds.height * 0.57,
    };
    await page.mouse.move(pointer.x, pointer.y);
    const worldPoint = () =>
      svg.evaluate((element, point) => {
        const matrix = element
          .querySelector(":scope > g")
          .getScreenCTM()
          .inverse();
        const p = new DOMPoint(point.x, point.y).matrixTransform(matrix);
        return { x: p.x, y: p.y };
      }, pointer);
    const before = await worldPoint();
    const scrollY = await page.evaluate(() => window.scrollY);
    await svg.evaluate((element) => {
      window.zoomSamples = [];
      const sample = () => {
        window.zoomSamples.push(Number(element.parentElement.dataset.zoom));
        if (window.zoomSamples.length < 40) requestAnimationFrame(sample);
      };
      requestAnimationFrame(sample);
    });
    await page.mouse.wheel(0, -100);
    await expect
      .poll(() => zoom(map))
      .toBeCloseTo(initialZoom * Math.exp(0.18), 3);
    const after = await worldPoint();
    // Browser wheel coordinates are rounded to CSS pixels.
    expect(Math.abs(after.x - before.x)).toBeLessThan(1);
    expect(Math.abs(after.y - before.y)).toBeLessThan(1);
    expect(await page.evaluate(() => window.scrollY)).toBe(scrollY);
    expect(
      await page.evaluate(() => new Set(window.zoomSamples).size),
    ).toBeGreaterThan(3);

    for (let i = 0; i < 5; i++) await page.mouse.wheel(0, 240);
    await expect.poll(() => zoom(map)).toBe(minimum);
    await expect(
      map.getByRole("button", { name: "지도 축소", exact: true }),
    ).toBeDisabled();
    await expect(
      map.locator('.document-node[data-label-visible="true"]'),
    ).toHaveCount(0);
    const title = map.locator(".document-cluster__title").first();
    const fontAtMinimum = await title.evaluate((e) =>
      parseFloat(getComputedStyle(e).fontSize),
    );
    const screenSize = await title.evaluate(
      (e) => parseFloat(getComputedStyle(e).fontSize) * e.getScreenCTM().a,
    );
    expect(screenSize).toBeGreaterThanOrEqual(16);
    await page.screenshot({
      path: `test-results/pulse-zoom-${fullscreen ? "full" : "inline"}-min.png`,
    });

    for (let i = 0; i < 6; i++) await page.mouse.wheel(0, -240);
    await expect.poll(() => zoom(map)).toBe(maximum);
    await expect(
      map.getByRole("button", { name: "지도 확대", exact: true }),
    ).toBeDisabled();
    await expect(
      map.locator('.document-node[data-label-visible="false"]'),
    ).toHaveCount(0);
    expect(
      await title.evaluate((e) => parseFloat(getComputedStyle(e).fontSize)),
    ).toBeLessThan(fontAtMinimum);
    expect(
      await title.evaluate(
        (e) => parseFloat(getComputedStyle(e).fontSize) * e.getScreenCTM().a,
      ),
    ).toBeCloseTo(screenSize, 1);
    await page.screenshot({
      path: `test-results/pulse-zoom-${fullscreen ? "full" : "inline"}-max.png`,
    });
    await map.getByRole("button", { name: "지도 위치 초기화" }).click();
    await expect.poll(() => zoom(map)).toBe(initialZoom);
    await svg.focus();
    await page.keyboard.press("ArrowRight");
    await expect.poll(() => zoom(map)).toBe(initialZoom);
    expect(errors).toEqual([]);
  });
}

test("fullscreen timeline keeps its date after closing and remains reachable on mobile", async ({
  page,
}) => {
  await page.goto("/#/pulse");
  await page
    .getByRole("button", { name: "펄스맵 전체화면", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "펄스맵 전체화면" });
  const slider = dialog.getByRole("slider", { name: "스냅샷 시각" });
  await dialog.getByRole("button", { name: "시간축 표시" }).hover();
  await expect(slider).toBeInViewport();
  await slider.focus();
  await page.keyboard.press("Home");
  await expect(dialog.locator(".pulse-layout")).toHaveAttribute(
    "data-snapshot",
    timestamp(dates[0]),
  );
  await expect(
    dialog.getByRole("button", { name: "이전 시점" }),
  ).toBeDisabled();
  await page.keyboard.press("ArrowRight");
  await expect(dialog.locator(".pulse-layout")).toHaveAttribute(
    "data-snapshot",
    timestamp(dates[1]),
  );
  await dialog.getByRole("button", { name: "다음 시점" }).click();
  await expect(dialog.locator(".pulse-layout")).toHaveAttribute(
    "data-snapshot",
    timestamp(dates[2]),
  );
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("slider", { name: "스냅샷 시각" })).toHaveValue(
    String(Date.parse(timestamp(dates[2]))),
  );
  await page.getByRole("button", { name: "최신으로 이동" }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .getByRole("button", { name: "펄스맵 전체화면", exact: true })
    .click();
  await dialog.getByRole("button", { name: "시간축 표시" }).hover();
  await expect(slider).toBeInViewport();
  await dialog
    .locator('.document-cluster[data-rank="0"] > [role="button"]')
    .first()
    .focus();
  await page.keyboard.press("Enter");
  await dialog.getByRole("button", { name: "시간축 표시" }).hover();
  await expect(slider).toBeInViewport();
  const box = await slider.boundingBox();
  expect(
    await page.evaluate(
      ({ x, y }) => document.elementFromPoint(x, y)?.tagName,
      { x: box.x + box.width / 2, y: box.y + box.height / 2 },
    ),
  ).toBe("INPUT");
  await page.screenshot({ path: "test-results/pulse-timeline-mobile.png" });
  await dialog.getByRole("button", { name: "이전 시점" }).click();
  await expect(dialog.locator(".pulse-layout")).toHaveAttribute(
    "data-snapshot",
    timestamp(dates.at(-2)),
  );
  await dialog.getByRole("button", { name: "최신으로 이동" }).click();
  await expect(dialog.locator(".pulse-layout")).toHaveAttribute(
    "data-snapshot",
    timestamp(dates.at(-1)),
  );
  await expect(
    dialog.getByRole("button", { name: "다음 시점" }),
  ).toBeDisabled();
});

test("reduced motion retains small wheel increments and resets pending zoom", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/#/pulse");
  const map = page.locator(".document-map");
  const svg = map.locator("svg[role=group]");
  await svg.hover();
  await expect.poll(() => zoom(map)).toBe(initialZoom);
  await page.mouse.wheel(0, -2);
  await expect
    .poll(() => zoom(map))
    .toBeCloseTo(initialZoom * Math.exp(0.0036), 5);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.mouse.wheel(0, -240);
  await map.getByRole("button", { name: "지도 위치 초기화" }).click();
  await expect.poll(() => zoom(map)).toBe(initialZoom);
  // A stale animation must not undo the explicit reset on later frames.
  await page.evaluate(
    () =>
      new Promise((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(resolve)),
      ),
  );
  await expect.poll(() => zoom(map)).toBe(initialZoom);
});
