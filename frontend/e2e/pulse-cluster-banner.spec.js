import { test, expect } from "@playwright/test";

for (const fullscreen of [false, true]) {
  for (const input of ["click", "keyboard"]) {
    test(`${fullscreen ? "fullscreen" : "inline"} cluster ${input} opens and switches the banner while zooming`, async ({
      page,
    }) => {
      await page.goto("/#/pulse");
      if (fullscreen)
        await page
          .getByRole("button", { name: "펄스맵 전체화면", exact: true })
          .click();
      const map = page.locator(".document-map");
      const banner = page.getByRole("complementary", { name: "선택한 사건" });
      let previousTitle;
      for (const rank of [0, 1]) {
        if (rank)
          await map.getByRole("button", { name: "지도 위치 초기화" }).click();
        await expect(map).toHaveAttribute("data-overview", "true");
        const beforeZoom = Number(await map.getAttribute("data-zoom"));
        const cluster = map.locator(`.document-cluster[data-rank="${rank}"]`);
        const button = cluster.getByRole("button", { name: /클러스터 확대/ });
        const title = (await button.getAttribute("aria-label")).replace(
          /, \d+개 문서, 클러스터 확대$/,
          "",
        );
        if (previousTitle) expect(title).not.toBe(previousTitle);
        if (input === "click") await button.click();
        else {
          await button.focus();
          await page.keyboard.press(rank ? "Space" : "Enter");
        }
        await expect(banner).toBeVisible();
        await expect(banner.getByRole("heading", { level: 2 })).toHaveText(
          title,
        );
        await expect(cluster).toHaveAttribute("data-selected", "true");
        await expect
          .poll(async () => Number(await map.getAttribute("data-zoom")))
          .toBeGreaterThan(beforeZoom);
        await expect(map).toHaveAttribute("data-overview", "false");
        previousTitle = title;
      }
    });
  }
}
