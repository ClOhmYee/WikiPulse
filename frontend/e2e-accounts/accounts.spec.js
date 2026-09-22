import { test, expect } from "@playwright/test";
const password = "browser-test-only-123!";
const cluster = process.env.ACCOUNT_E2E_CLUSTER;
const nav = (page) => page.getByRole("navigation", { name: "주 메뉴" });
async function submitLogin(page, email) {
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("이메일", { exact: true }).fill(email);
  await dialog.getByLabel("비밀번호", { exact: true }).fill(password);
  await dialog.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(dialog).toHaveCount(0);
}
async function signup(page, email) {
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "회원가입", exact: true }).click();
  await dialog.getByLabel("닉네임").fill("브라우저 사용자");
  await dialog.getByLabel("이메일", { exact: true }).fill(email);
  await dialog.getByLabel("비밀번호", { exact: true }).fill(password);
  await dialog.getByLabel("비밀번호 확인").fill(password);
  await dialog.getByRole("button", { name: "회원가입", exact: true }).click();
  await expect(
    dialog.getByRole("heading", { name: "로그인", exact: true }),
  ).toBeVisible();
  await expect(dialog.getByLabel("이메일", { exact: true })).toHaveValue(email);
}

test("real signup, guest intent, cancellation, reload, browser restart, account isolation and removal", async ({
  page,
  browser,
  baseURL,
}) => {
  const email = `browser-${Date.now()}@example.com`;
  await page.goto(`/#/issues/${cluster}`);
  await expect(nav(page).getByRole("link", { name: "보관함" })).toHaveCount(0);
  await page.getByRole("button", { name: "이벤트 저장", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "이벤트 저장", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "이벤트 저장", exact: true }).click();
  await signup(page, email);
  await submitLogin(page, email);
  await expect(
    page.getByRole("button", { name: "저장됨", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => sessionStorage.getItem("wikipulse.auth.token")),
  ).toBeNull();
  await page.goto("/#/stocks/T211");
  await page
    .getByRole("button", {
      name: "Account E2E Stock 관심 종목에 추가",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("button", {
      name: "Account E2E Stock 관심 종목에서 해제",
      exact: true,
    }),
  ).toBeVisible();
  await nav(page).getByRole("link", { name: "보관함" }).click();
  await expect(
    page.getByRole("link", { name: "Account E2E Issue", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("link", { name: "Account E2E Issue", exact: true }),
  ).toBeVisible();
  const state = await page.context().storageState();
  const cookie = state.cookies.find((c) => c.name === "WIKIPULSE_SESSION");
  expect(cookie.httpOnly).toBe(true);
  expect(cookie.sameSite).toBe("Lax");
  expect(cookie.expires).toBeGreaterThan(Date.now() / 1000 + 86000);
  // New browser process, restored persistent cookies, no JS credential storage.
  const restartedBrowser = await browser.browserType().launch();
  const restored = await restartedBrowser.newContext({
    storageState: state,
    baseURL,
  });
  const restoredPage = await restored.newPage();
  await restoredPage.goto("/#/saved");
  await expect(
    restoredPage.getByRole("link", { name: "Account E2E Issue", exact: true }),
  ).toBeVisible();
  await restartedBrowser.close();
  await page.getByRole("button", { name: "로그아웃", exact: true }).click();
  await expect(nav(page).getByRole("link", { name: "보관함" })).toHaveCount(0);
  await page
    .locator(".workspace-header")
    .getByRole("button", { name: "로그인", exact: true })
    .click();
  const second = `second-${Date.now()}@example.com`;
  await signup(page, second);
  await submitLogin(page, second);
  await expect(
    page.getByRole("link", { name: "Account E2E Issue", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("heading", {
      name: "다음에 다시 보고 싶은 사건을 담아보세요",
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "로그아웃", exact: true }).click();
  await page
    .locator(".workspace-header")
    .getByRole("button", { name: "로그인", exact: true })
    .click();
  await submitLogin(page, email);
  await page
    .getByRole("button", { name: "Account E2E Issue 저장 해제", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: "Account E2E Issue", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: /관심 종목/ }).click();
  await page
    .getByRole("button", {
      name: "Account E2E Stock 관심 종목 해제",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("heading", { name: "궁금한 종목을 저장해 보세요" }),
  ).toBeVisible();
});

test("cancelled guest save does not run after a later explicit login", async ({
  page,
}) => {
  const email = `cancel-${Date.now()}@example.com`;
  await page.goto(`/#/issues/${cluster}`);
  await page.getByRole("button", { name: "이벤트 저장", exact: true }).click();
  await page.getByRole("button", { name: "인증 창 닫기" }).click();
  await page
    .locator(".workspace-header")
    .getByRole("button", { name: "로그인", exact: true })
    .click();
  await signup(page, email);
  await submitLogin(page, email);
  await expect(
    page.getByRole("button", { name: "이벤트 저장", exact: true }),
  ).toBeVisible();
  const response = await page.request.get("/api/v1/me/saved-state");
  expect((await response.json()).data.issueIds).toEqual([]);
});

test("failed writes preserve state and account changes clear other tabs", async ({
  page,
  context,
}) => {
  const email = `failure-${Date.now()}@example.com`;
  await page.goto(`/#/issues/${cluster}`);
  await page
    .locator(".workspace-header")
    .getByRole("button", { name: "로그인", exact: true })
    .click();
  await signup(page, email);
  await submitLogin(page, email);
  await expect(nav(page).getByRole("link", { name: "보관함" })).toBeVisible();
  // Failure injection only; account/session/read requests still use the real backend.
  await page.route(`**/api/v1/me/bookmarks/${cluster}`, (route) =>
    route.fulfill({ status: 500, json: { error: { code: "INTERNAL" } } }),
  );
  await page.getByRole("button", { name: "이벤트 저장", exact: true }).click();
  await expect(
    page.getByText("서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요."),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "이벤트 저장", exact: true }),
  ).toBeVisible();
  await page.unroute(`**/api/v1/me/bookmarks/${cluster}`);
  await page.getByRole("button", { name: "이벤트 저장", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "저장됨", exact: true }),
  ).toBeVisible();
  const other = await context.newPage();
  await other.goto("/#/saved");
  await expect(
    other.getByRole("link", { name: "Account E2E Issue", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "로그아웃", exact: true }).click();
  await expect(
    other.getByRole("heading", { name: "로그인이 필요합니다" }),
  ).toBeVisible();
  await expect(
    other.getByRole("link", { name: "Account E2E Issue", exact: true }),
  ).toHaveCount(0);
});
