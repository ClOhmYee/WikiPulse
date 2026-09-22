import { test, expect } from "@playwright/test";
import { newsroomExamples } from "../src/data/mock/fixtures/newsroom.js";
import { mockClient } from "../src/data/mock/client.js";

for (const width of [1440, 390]) {
  test(`map and article share the full summary at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 1000 });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const map = await mockClient.getPulseMap();
    const cluster = map.data.clusters.find(
      (item) => item.issueKey === "iran-hormuz-2025",
    );
    await page.goto("/#/pulse");
    await page
      .locator(".pulse-cluster-list button")
      .filter({ hasText: cluster.label })
      .click();
    const panel = page.getByRole("complementary", { name: "선택한 사건" });
    await expect(panel.locator(".issue-summary p")).toHaveText(cluster.summary);
    await panel.scrollIntoViewIfNeeded();
    await page.screenshot({
      path: `../output/newsroom-pulse-${width}.png`,
      fullPage: true,
    });
    await panel.getByRole("link", { name: "이슈 리포트 보기" }).click();
    await expect(page.locator(".dt-report .issue-summary p")).toHaveText(
      cluster.summary,
    );
    await expect(
      page.getByRole("article", { name: "리포트 본문" }),
    ).toBeVisible();
    await expect(page.locator(".dt-report-prose > p")).toHaveCount(4);
    await expect(page.locator(".dt-report-section")).toHaveCount(0);
    await expect(page.locator(".dt-report-sources a")).toHaveCount(
      cluster.memberCount,
    );
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `../output/newsroom-report-${width}.png`,
      fullPage: true,
    });
    expect(errors).toEqual([]);
  });
}

test("six authored examples have distinct complete articles and reachable sources", async ({
  page,
}) => {
  for (const [id, example] of Object.entries(newsroomExamples)) {
    await page.goto(`/#/issues/${id}`);
    await expect(page.locator(".issue-summary p")).toHaveText(example.summary);
    await expect(page.locator(".dt-report-prose > p").first()).toHaveText(
      example.paragraphs[0],
    );
    await expect(page.locator(".dt-report-sources a").first()).toHaveAttribute(
      "href",
      /^https:\/\/en\.wikipedia\.org\/wiki\//,
    );
  }
});
