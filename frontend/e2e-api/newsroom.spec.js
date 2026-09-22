import { test, expect } from "@playwright/test";
import { mockClient } from "../src/data/mock/client.js";
import { serve } from "./server.js";

const issue = (await mockClient.getIssue("iran-hormuz-2025")).data;

test("legacy sections read as one article with unique source links", async ({
  page,
}) => {
  await serve(page, async ({ route, url }) => {
    if (url.pathname !== `/api/v1/issues/${issue.id}`) return false;
    await route.fulfill({
      json: {
        data: {
          ...issue,
          report: {
            status: "ready",
            sections: [
              {
                id: "conclusion",
                title: "결론",
                body: "첫 번째 문단입니다.\n\n두 번째 문단입니다.",
                evidenceIds: [issue.members[0].pageId],
              },
              {
                id: "context",
                title: "맥락",
                body: "이어지는 세 번째 문단입니다.",
                evidenceIds: [issue.members[0].pageId],
              },
            ],
          },
        },
      },
    });
    return true;
  });
  await page.goto(`/#/issues/${issue.id}`);
  await expect(page.locator(".dt-report-prose > p")).toHaveText([
    "첫 번째 문단입니다.",
    "두 번째 문단입니다.",
    "이어지는 세 번째 문단입니다.",
  ]);
  await expect(
    page.getByRole("heading", { name: /^(결론|맥락)$/ }),
  ).toHaveCount(0);
  await expect(page.locator(".dt-report-sources a")).toHaveCount(1);
});

for (const [status, title] of [
  ["generating", "리포트를 생성하고 있습니다"],
  ["failed", "리포트를 불러오지 못했습니다"],
  ["insufficient_evidence", "리포트를 만들 근거가 충분하지 않습니다"],
  ["ready", "리포트를 만들 근거가 충분하지 않습니다"],
]) {
  test(`${status} without article content preserves the summary and evidence navigation`, async ({
    page,
  }) => {
    await serve(page, async ({ route, url }) => {
      if (url.pathname !== `/api/v1/issues/${issue.id}`) return false;
      await route.fulfill({
        json: {
          data: { ...issue, summary: " ", report: { status, sections: [] } },
        },
      });
      return true;
    });
    await page.goto(`/#/issues/${issue.id}`);
    await expect(
      page.getByRole("heading", { name: title, exact: true }),
    ).toBeVisible();
    await expect(page.locator(".issue-summary p")).toHaveText(
      "이 시점의 요약이 제공되지 않았습니다.",
    );
    await expect(page.locator(".dt-report-prose")).toHaveCount(0);
    await page.getByRole("tab", { name: /^근거 문서/ }).click();
    await expect(page.locator(".dt-evidence-row").first()).toBeVisible();
  });
}
