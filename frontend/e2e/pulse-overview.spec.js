import { test, expect } from "@playwright/test";

test("cluster activation animates zoom and pan and reset cancels the flight", async ({
  page,
}) => {
  await page.goto("/#/pulse");
  const map = page.locator(".document-map");
  const target = map.locator('.document-cluster[data-rank="1"]');
  await expect(target).toBeVisible();
  await expect(map).toHaveAttribute("data-overview", "true");
  const before = await target.evaluate((element) => {
    const map = element.closest(".document-map");
    window.flightSamples = [];
    window.flightObserver = new MutationObserver(() => {
      const m = element.getScreenCTM();
      window.flightSamples.push({
        zoom: Number(map.dataset.zoom),
        x: m.e,
        y: m.f,
      });
    });
    window.flightObserver.observe(map, {
      attributes: true,
      attributeFilter: ["data-zoom"],
    });
    const zoom = Number(map.dataset.zoom);
    element
      .querySelector(':scope > [role="button"]')
      .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    return { zoom, immediate: Number(map.dataset.zoom) };
  });
  expect(before.immediate).toBe(before.zoom);
  await expect
    .poll(() => map.getAttribute("data-zoom").then(Number))
    .toBeCloseTo(1.219744, 5);
  const frames = await page.evaluate(() => {
    window.flightObserver.disconnect();
    return window.flightSamples;
  });
  expect(new Set(frames.map((frame) => frame.zoom)).size).toBeGreaterThan(5);
  expect(new Set(frames.map((frame) => frame.x)).size).toBeGreaterThan(5);
  for (let i = 1; i < frames.length; i++) {
    expect(frames[i].zoom).toBeGreaterThanOrEqual(frames[i - 1].zoom);
    expect(frames[i].zoom).toBeLessThanOrEqual(1.219744 + 0.000001);
  }
  await expect
    .poll(() =>
      target.evaluate((element) => {
        const p = new DOMPoint(0, 0).matrixTransform(element.getScreenCTM());
        const box = element.ownerSVGElement.getBoundingClientRect();
        return Math.hypot(
          p.x - box.x - box.width / 2,
          p.y - box.y - box.height / 2,
        );
      }),
    )
    .toBeLessThan(1);
  await map.getByRole("button", { name: "지도 위치 초기화" }).click();
  await target.evaluate((element) => {
    element
      .querySelector(':scope > [role="button"]')
      .dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  await expect
    .poll(() => map.getAttribute("data-zoom").then(Number))
    .toBeGreaterThan(before.zoom);
  await map.getByRole("button", { name: "지도 위치 초기화" }).click();
  await page.waitForTimeout(650);
  await expect(map).toHaveAttribute("data-zoom", String(1 / 1.2));
});

for (const mobile of [false, true]) {
  test(`cluster overview restores detail on ${mobile ? "mobile" : "desktop"}`, async ({
    page,
  }) => {
    if (mobile) await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/#/pulse");
    const map = page.locator(".document-map");
    const center = map.locator('.document-cluster[data-rank="0"]');
    await expect(center).toBeVisible();
    const nodeCount = await map.locator(".document-node").count();
    const out = page.getByRole("button", { name: "지도 축소", exact: true });
    await expect(map).toHaveAttribute("data-overview", "true");
    const zoomIn = page.getByRole("button", { name: "지도 확대", exact: true });
    for (let i = 0; i < 3; i++) await zoomIn.click();
    await out.click();
    await expect(map).toHaveAttribute("data-overview", "false");
    await out.click();
    await expect(map).toHaveAttribute("data-overview", "true");
    await expect(center.locator(".document-node").first()).toBeHidden();
    await map.screenshot({
      path: `../.impeccable/review/overview-${mobile ? "mobile" : "desktop"}.png`,
    });
    for (let i = 0; i < 8; i++) await out.click();
    await expect(map).toHaveAttribute("data-zoom", String(0.12 * 1.2 ** 4));
    await expect(out).toBeDisabled();
    const fits = await map
      .locator(".document-cluster__summary-title")
      .evaluateAll((titles) =>
        titles.every((title) => {
          const box = title.getBBox();
          const radius = Number(
            title.parentElement
              .querySelector(".document-cluster__summary-circle")
              .getAttribute("r"),
          );
          return (
            Math.hypot(
              Math.max(Math.abs(box.x), Math.abs(box.x + box.width)),
              Math.max(Math.abs(box.y), Math.abs(box.y + box.height)),
            ) < radius
          );
        }),
      );
    expect(fits).toBe(true);
    await map.screenshot({
      path: `../.impeccable/review/overview-min-${mobile ? "mobile" : "desktop"}.png`,
    });
    const target = map.locator('.document-cluster[data-rank="1"]');
    const activate = target.getByRole("button", { name: /클러스터 확대/ });
    if (mobile) await activate.click();
    else {
      await activate.focus();
      await page.keyboard.press("Enter");
    }
    await expect(map).toHaveAttribute("data-overview", "false");
    await expect(target.locator(".document-node").first()).toBeVisible();
    const offset = await target.evaluate((element) => {
      const point = new DOMPoint(0, 0).matrixTransform(element.getScreenCTM());
      const box = element.ownerSVGElement.getBoundingClientRect();
      return Math.hypot(
        point.x - box.x - box.width / 2,
        point.y - box.y - box.height / 2,
      );
    });
    expect(offset).toBeLessThan(1);
    await expect(map.locator(".document-node")).toHaveCount(nodeCount);
    await page.getByRole("button", { name: "지도 위치 초기화" }).click();
    await expect(map).toHaveAttribute("data-zoom", String(1 / 1.2));
    await expect(map).toHaveAttribute("data-overview", "true");
  });
}

for (const width of [1440, 390]) {
  test(`overview scan illuminates node-style circles at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/#/pulse");
    const map = page.locator(".document-map");
    const out = map.getByRole("button", { name: "지도 축소", exact: true });
    for (let i = 0; i < 6; i++) await out.click();
    await expect(map).toHaveAttribute("data-overview", "true");
    const svg = map.locator("svg[role=group]");
    await svg.scrollIntoViewIfNeeded();
    await svg.focus();
    await page.keyboard.press("ArrowRight");
    await expect
      .poll(
        () =>
          svg.evaluate((element) => {
            const wave = element.querySelector(".pulse-scan__wave");
            const matrix = wave.getScreenCTM();
            const origin = new DOMPoint(0, 0).matrixTransform(matrix);
            const waveRadius = Number(wave.getAttribute("r")) * matrix.a;
            return [
              ...element.querySelectorAll(
                '.document-cluster[data-rendered="true"] .document-cluster__summary',
              ),
            ].some((summary) => {
              const position = new DOMPoint(0, 0).matrixTransform(
                summary.getScreenCTM(),
              );
              const distance = Math.hypot(
                position.x - origin.x,
                position.y - origin.y,
              );
              return (
                Number(summary.style.getPropertyValue("--scan-strength")) >
                  0.65 &&
                Math.abs(distance - waveRadius) < 60 &&
                Number(
                  getComputedStyle(
                    summary.querySelector(".document-node__echo"),
                  ).opacity,
                ) > 0.65 &&
                Number(
                  getComputedStyle(
                    summary.querySelector(".document-node__halo"),
                  ).opacity,
                ) > 0.85
              );
            });
          }),
        { timeout: 6500, intervals: [16] },
      )
      .toBe(true);
    await map.screenshot({
      path: `../.impeccable/review/overview-glow-${width}.png`,
    });
    await map.getByRole("button", { name: "스캔 효과 일시정지" }).click();
    const echoes = map.locator(
      ".document-cluster__summary .document-node__echo",
    );
    await expect
      .poll(() =>
        echoes.evaluateAll((elements) =>
          elements.every((e) => getComputedStyle(e).opacity === "0"),
        ),
      )
      .toBe(true);
    await map.getByRole("button", { name: "스캔 효과 재생" }).click();
    await page.emulateMedia({ reducedMotion: "reduce" });
    await expect(svg).toHaveAttribute("data-scan-state", "reduced");
    await expect
      .poll(() =>
        echoes.evaluateAll((elements) =>
          elements.every((e) => getComputedStyle(e).opacity === "0"),
        ),
      )
      .toBe(true);
  });
}
