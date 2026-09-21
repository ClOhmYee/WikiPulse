import { test, expect } from "@playwright/test";

test("overview camera frames leave hidden detail geometry unchanged", async ({
  page,
}) => {
  await page.goto("/#/pulse");
  const map = page.locator(".document-map");
  await map.locator(".document-cluster").first().waitFor();
  await expect(map).toHaveAttribute("data-overview", "true");
  await map.evaluate((element) => {
    window.overviewWork = { mode: 0, detail: 0, font: 0 };
    window.overviewObserver = new MutationObserver((records) => {
      for (const record of records) {
        if (
          record.target === element &&
          record.attributeName === "data-overview"
        )
          window.overviewWork.mode++;
        if (
          record.target.matches(
            ".document-cluster__heading, .document-node-label__text",
          ) &&
          ["transform", "data-scan-y", "font-size"].includes(
            record.attributeName,
          )
        )
          window.overviewWork.detail++;
        if (
          record.target.matches(".document-cluster__summary-title") &&
          record.attributeName === "font-size"
        )
          window.overviewWork.font++;
      }
    });
    window.overviewObserver.observe(element, {
      attributes: true,
      subtree: true,
    });
  });
  await map.getByRole("button", { name: "지도 확대", exact: true }).click();
  await expect(map).toHaveAttribute("data-zoom", "1");
  expect(await page.evaluate(() => window.overviewWork)).toEqual({
    mode: 0,
    detail: 0,
    font: 0,
  });
  await map.getByRole("button", { name: "지도 확대", exact: true }).click();
  await expect(map).toHaveAttribute("data-zoom", "1.2");
  expect(await page.evaluate(() => window.overviewWork.mode)).toBe(1);
  await expect(
    map.locator('.document-cluster[data-rank="0"] .document-node').first(),
  ).toBeVisible();
  await page.evaluate(() => window.overviewObserver.disconnect());
});

test("zoom reuses title geometry and restores culled clusters without losing documents", async ({
  page,
}) => {
  await page.goto("/#/pulse");
  const map = page.locator(".document-map");
  await map.locator(".document-cluster").first().waitFor();
  await map.locator(".document-map__controls button").last().click();
  const svg = map.locator(":scope > svg");
  const controls = map.locator(".document-map__controls button");
  const total = await map.locator(".document-node").count();
  const culled = map
    .locator('.document-cluster[data-rendered="false"]')
    .first();
  const key = await culled.getAttribute("data-issue-key");
  expect(key).toBeTruthy();
  const restored = map.locator(`.document-cluster[data-issue-key="${key}"]`);
  await map.evaluate((element) => {
    window.geometryChanges = 0;
    window.cameraFrames = 0;
    window.mapObserver = new MutationObserver((records) => {
      for (const record of records) {
        if (record.attributeName === "data-zoom") window.cameraFrames++;
        if (
          record.target.matches(".document-cluster__heading rect") &&
          ["x", "y", "width", "height", "rx"].includes(record.attributeName)
        )
          window.geometryChanges++;
      }
    });
    window.mapObserver.observe(element, { attributes: true, subtree: true });
  });
  await controls.nth(2).click();
  await expect(map).toHaveAttribute("data-zoom", "1");
  expect(await page.evaluate(() => window.cameraFrames)).toBeGreaterThan(5);
  expect(await page.evaluate(() => window.geometryChanges)).toBe(0);
  await page.evaluate(() => window.mapObserver.disconnect());
  const before = Number(await svg.getAttribute("data-rendered-clusters"));
  const bounds = await svg.boundingBox();
  await page.mouse.move(
    bounds.x + bounds.width / 2,
    bounds.y + bounds.height / 2,
  );
  for (let i = 0; i < 5; i++) await page.mouse.wheel(0, 240);
  await expect(controls.nth(1)).toBeDisabled();
  await expect(restored).toHaveAttribute("data-rendered", "true");
  expect(
    Number(await svg.getAttribute("data-rendered-clusters")),
  ).toBeGreaterThan(before);
  await expect(map.locator(".document-node")).toHaveCount(total);
  await expect(map.locator(".document-node-label")).toHaveCount(total);
  await controls.nth(3).click();
  await expect(restored).toHaveAttribute("data-rendered", "false");
  await expect
    .poll(() =>
      map.evaluate((element) =>
        [
          ...element.querySelectorAll(
            '.document-cluster[data-rendered="false"] [data-scan-x]',
          ),
        ].every(
          (target) => !Number(target.style.getPropertyValue("--scan-strength")),
        ),
      ),
    )
    .toBe(true);
});

test("title glow follows the transformed box through zoom and clears on pause", async ({
  page,
}) => {
  await page.goto("/#/pulse");
  const map = page.locator(".document-map");
  await map.locator(".document-cluster").first().waitFor();
  await map.locator(".document-map__controls button").last().click();
  const controls = map.locator(".document-map__controls button");
  const svg = map.locator(":scope > svg");
  await controls.nth(2).click();
  await expect(map).toHaveAttribute("data-zoom", "1");
  await controls.nth(2).click();
  await expect(map).toHaveAttribute("data-zoom", "1.2");
  const heading = map.locator(
    '.document-cluster[data-rank="0"] .document-cluster__heading',
  );
  const y = await heading.getAttribute("data-scan-y");
  await controls.nth(2).click();
  await expect(map).toHaveAttribute("data-zoom", "1.44");
  expect(await heading.getAttribute("data-scan-y")).not.toBe(y);
  await svg.focus();
  await page.keyboard.press("ArrowUp");
  await expect
    .poll(
      () =>
        heading.evaluate((element) => {
          const wave =
            element.ownerSVGElement.querySelector(".pulse-scan__wave");
          const matrix = wave.getScreenCTM();
          const origin = new DOMPoint(0, 0).matrixTransform(matrix);
          const box = element.querySelector(".document-cluster__title-box");
          const rect = box.getBBox();
          const center = new DOMPoint(
            rect.x + rect.width / 2,
            rect.y + rect.height / 2,
          ).matrixTransform(box.getScreenCTM());
          const distance = Math.hypot(center.x - origin.x, center.y - origin.y);
          return (
            Number(element.style.getPropertyValue("--scan-strength")) > 0.7 &&
            Math.abs(distance - Number(wave.getAttribute("r")) * matrix.a) < 70
          );
        }),
      { timeout: 6000, intervals: [16] },
    )
    .toBe(true);
  await controls.first().click();
  await expect(heading.locator(".document-cluster__title-glow")).toHaveCSS(
    "opacity",
    "0.45",
  );
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(svg).toHaveAttribute("data-scan-state", "reduced");
});
