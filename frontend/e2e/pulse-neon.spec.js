import { test, expect } from "@playwright/test";
import { createRequire } from "node:module";

const axePath = createRequire(import.meta.url).resolve("axe-core/axe.min.js");

test("scan meets nodes after camera movement and pause survives fullscreen", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/#/pulse");
  const map = page.locator(".document-map");
  const svg = map.locator("svg[role=group]");
  await map.scrollIntoViewIfNeeded();
  await expect(svg).toHaveAttribute("data-scan-state", "running");
  const snapshot = await map.getAttribute("data-snapshot");
  await map.getByRole("button", { name: "지도 확대", exact: true }).click();
  await svg.focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowDown");
  const origin = await svg.evaluate((element) => {
    const wave = element.querySelector(".pulse-scan__wave");
    const center = new DOMPoint(0, 0).matrixTransform(wave.getScreenCTM());
    const mapCenter = new DOMPoint(0, 0).matrixTransform(
      element.querySelector('.document-cluster[data-rank="0"]').getScreenCTM(),
    );
    const bounds = element.getBoundingClientRect();
    return {
      fromMap: Math.hypot(center.x - mapCenter.x, center.y - mapCenter.y),
      fromViewport: Math.hypot(
        center.x - bounds.x - bounds.width / 2,
        center.y - bounds.y - bounds.height / 2,
      ),
    };
  });
  expect(origin.fromMap).toBeLessThan(1);
  expect(origin.fromViewport).toBeGreaterThan(50);
  // Measure rendered geometry, independently of the hook's world projection.
  await expect
    .poll(
      () =>
        svg.evaluate((element) => {
          const wave = element.querySelector(".pulse-scan__wave");
          const origin = new DOMPoint(0, 0).matrixTransform(
            wave.getScreenCTM(),
          );
          const radius = Number(wave.getAttribute("r")) * wave.getScreenCTM().a;
          return [...element.querySelectorAll(".document-node")].some(
            (node) => {
              const strength = Number(
                node.style.getPropertyValue("--scan-strength"),
              );
              const position = new DOMPoint(0, 0).matrixTransform(
                node.getScreenCTM(),
              );
              const distance = Math.hypot(
                position.x - origin.x,
                position.y - origin.y,
              );
              return strength > 0.65 && Math.abs(distance - radius) < 60;
            },
          );
        }),
      { timeout: 6000, intervals: [16] },
    )
    .toBe(true);
  await map.getByRole("button", { name: "스캔 효과 일시정지" }).click();
  await expect(svg).toHaveAttribute("data-scan-state", "paused");
  await expect(map.locator(".pulse-scan__wave")).toHaveCSS("opacity", "0");
  await expect(map).toHaveAttribute("data-snapshot", snapshot);
  await map
    .getByRole("button", { name: "펄스맵 전체화면", exact: true })
    .click();
  await expect(svg).toHaveAttribute("data-scan-state", "paused");
  await map.getByRole("button", { name: "스캔 효과 재생" }).click();
  await expect(svg).toHaveAttribute("data-scan-state", "running");
  await page.keyboard.press("Escape");
  await expect(svg).toHaveAttribute("data-scan-state", "running");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(svg).toHaveAttribute("data-scan-state", "reduced");
  await expect(
    map.getByRole("button", { name: "모션 감소 설정으로 스캔 효과 꺼짐" }),
  ).toBeDisabled();
  await expect(map.locator(".pulse-scan")).toBeHidden();
  await page.addScriptTag({ path: axePath });
  const violations = await page.evaluate(async () => {
    const result = await window.axe.run(".document-map", {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] },
    });
    return result.violations.map(({ id, nodes }) => ({
      id,
      targets: nodes.map(({ target }) => target),
    }));
  });
  expect(violations).toEqual([]);
  const focusedNode = map
    .locator('.document-cluster[data-rank="0"] .document-node')
    .first();
  const fullTitle = (await focusedNode.getAttribute("aria-label")).replace(
    /, (급증 감지 문서|연관 문서)$/u,
    "",
  );
  await focusedNode.focus();
  await expect(map.locator(".document-label-callout text")).toHaveText(
    fullTitle.replaceAll("_", " "),
  );
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "선택한 문서" })).toBeVisible();
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await expect(svg).toHaveAttribute("data-scan-state", "running");
  // Offscreen maps stop spending animation frames.
  await page.setViewportSize({ width: 1440, height: 300 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await expect(svg).toHaveAttribute("data-scan-state", "paused");
  expect(errors).toEqual([]);
});

for (const width of [1536, 390]) {
  test(`neon visual evidence and scan alignment after resize at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1024 });
    await page.goto("/#/pulse");
    const map = page.locator(".document-map");
    await expect(map.locator(".document-node").first()).toBeAttached();
    await page.evaluate(() => document.fonts.ready);
    await map.scrollIntoViewIfNeeded();
    if (width < 720) {
      await map.evaluate((element) =>
        window.scrollBy(0, element.getBoundingClientRect().top - 100),
      );
      const controls = await map
        .locator(".document-map__controls")
        .boundingBox();
      expect(controls.y + controls.height).toBeLessThan(844 - 70);
    }
    await map.screenshot({ path: `test-results/neon-inline-${width}.png` });
    await expect(map.locator(".document-node-label")).toHaveCount(
      await map.locator(".document-node").count(),
    );
    expect(
      await map.evaluate((element) =>
        [
          ...element.querySelectorAll(
            '.document-cluster[data-rendered="true"] .document-node',
          ),
        ].every((node) => {
          const label = node
            .closest(".document-cluster")
            .querySelector(
              `.document-node-label[data-page-id="${node.dataset.pageId}"]`,
            );
          const center = new DOMPoint(0, 0).matrixTransform(
            node.getScreenCTM(),
          );
          const radius =
            Number(
              node.querySelector(".document-node__body").getAttribute("r"),
            ) * node.getScreenCTM().a;
          const box = label.getBoundingClientRect();
          return (
            label.textContent.trim().length > 0 &&
            [box.left, box.right].every((x) =>
              [box.top, box.bottom].every(
                (y) => Math.hypot(x - center.x, y - center.y) < radius,
              ),
            )
          );
        }),
      ),
    ).toBe(true);
    await map
      .getByRole("button", { name: "펄스맵 전체화면", exact: true })
      .click();
    const svg = map.locator("svg[role=group]");
    await expect(svg).toHaveAttribute("data-scan-state", "running");
    if (width > 720) {
      await map.getByRole("button", { name: "지도 축소", exact: true }).click();
      await map.getByRole("button", { name: "지도 축소", exact: true }).click();
    }
    await expect
      .poll(
        () =>
          svg.evaluate((element) => {
            const wave = element.querySelector(".pulse-scan__wave");
            const radius =
              Number(wave.getAttribute("r")) * wave.getScreenCTM().a;
            return (
              radius > element.clientHeight * 0.32 &&
              radius < element.clientHeight * 0.48
            );
          }),
        { intervals: [50], timeout: 6000 },
      )
      .toBe(true);
    const waveCenter = await svg.evaluate((element) => {
      const wave = element.querySelector(".pulse-scan__wave");
      const center = new DOMPoint(0, 0).matrixTransform(wave.getScreenCTM());
      const mapCenter = new DOMPoint(0, 0).matrixTransform(
        element
          .querySelector('.document-cluster[data-rank="0"]')
          .getScreenCTM(),
      );
      return Math.hypot(center.x - mapCenter.x, center.y - mapCenter.y);
    });
    expect(waveCenter).toBeLessThan(1);
    await page.screenshot({
      path: `test-results/neon-fullscreen-${width}.png`,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth - innerWidth,
      ),
    ).toBeLessThanOrEqual(1);
  });
}
