import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/me", (route) =>
    route.fulfill({ status: 401, json: { error: { code: "UNAUTHORIZED" } } }),
  );
  await page.route("**/api/v1/auth/csrf", (route) =>
    route.fulfill({
      json: { data: { token: "csrf-fixture", headerName: "X-CSRF-TOKEN" } },
    }),
  );
  await page.route("**/api/v1/auth/logout", (route) =>
    route.fulfill({ status: 204 }),
  );
  await page.route("**/api/v1/me/saved-state", (route) =>
    route.fulfill({ json: { data: { issueIds: [], tickers: [] } } }),
  );
});
const member = {
  id: 7,
  displayName: "테스트 사용자",
  email: "reader@example.com",
};
const nav = (page) => page.getByRole("navigation", { name: "주 메뉴" });
const deferred = () => {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
};

for (const action of ["login", "logout"]) {
  test(`focus during ${action} cannot restore the previous account state`, async ({
    page,
  }) => {
    let restoring = 0;
    const started = deferred();
    const release = deferred();
    await page.route("**/api/v1/me", (route) => {
      restoring++;
      return route.fulfill(
        action === "logout"
          ? { json: { data: member } }
          : { status: 401, json: { error: { code: "UNAUTHORIZED" } } },
      );
    });
    await page.route(`**/api/v1/auth/${action}`, async (route) => {
      started.resolve();
      await release.promise;
      await route.fulfill(
        action === "login" ? { json: { data: { member } } } : { status: 204 },
      );
    });
    await page.goto(action === "login" ? "/#/login" : "/#/issues");
    await expect(nav(page).getByRole("link")).toHaveCount(
      action === "login" ? 3 : 5,
    );
    if (action === "login") {
      await fillLogin(page);
      await page
        .getByRole("dialog")
        .getByRole("button", { name: "로그인", exact: true })
        .click();
    } else {
      await page.getByRole("button", { name: "로그아웃" }).click();
    }
    await started.promise;
    const count = restoring;
    await page.evaluate(() => {
      window.dispatchEvent(new Event("focus"));
      document.dispatchEvent(new Event("visibilitychange"));
    });
    release.resolve();
    await expect(nav(page).getByRole("link")).toHaveCount(
      action === "login" ? 5 : 3,
    );
    expect(restoring).toBe(count);
  });
}
async function fillLogin(page) {
  await page.getByLabel("이메일", { exact: true }).fill(member.email);
  await page.getByLabel("비밀번호", { exact: true }).fill("test-password");
}

test("guest navigation, modal keyboard focus, switching and mobile layout", async ({
  page,
}) => {
  await page.goto("/#/issues");
  await expect(nav(page).getByRole("link")).toHaveCount(3);
  await expect(page.getByText(/API 데이터|데모 데이터/)).toHaveCount(0);
  const trigger = page.getByRole("button", { name: "로그인", exact: true });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "로그인", exact: true });
  await expect(dialog).toBeVisible();
  await expect(page.getByLabel("이메일", { exact: true })).toBeFocused();
  for (let i = 0; i < 7; i++) {
    await page.keyboard.press("Tab");
    expect(
      await dialog.evaluate((el) => el.contains(document.activeElement)),
    ).toBe(true);
  }
  await page.screenshot({
    path: "../.impeccable/review/auth-desktop.png",
    fullPage: true,
  });
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await trigger.click();
  await page.getByRole("button", { name: "회원가입", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("dialog", { name: "회원가입" })).toBeVisible();
  await expect(page.getByLabel("비밀번호 확인")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../.impeccable/review/auth-mobile.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "인증 창 닫기" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("server success gates menus, restores verified session and logout hides private routes", async ({
  page,
}) => {
  await page.route("**/api/v1/auth/login", (route) =>
    route.fulfill({ json: { data: { member } } }),
  );
  await page.route("**/api/v1/me", (route) =>
    route.fulfill({ json: { data: member } }),
  );
  await page.goto("/#/login");
  await fillLogin(page);
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "로그인", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(nav(page).getByRole("link")).toHaveCount(5);
  await nav(page).getByRole("link", { name: "마이페이지" }).click();
  await expect(
    page.getByRole("heading", { name: member.displayName }),
  ).toBeVisible();
  await page.reload();
  await expect(nav(page).getByRole("link", { name: "보관함" })).toBeVisible();
  await page.getByRole("button", { name: "로그아웃" }).click();
  await expect(nav(page).getByRole("link")).toHaveCount(3);
  await expect(
    page.getByRole("heading", { name: "로그인이 필요합니다" }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => sessionStorage.getItem("wikipulse.auth.token")),
  ).toBeNull();
});

test("signup validates confirmation, sends only contract fields and returns to login", async ({
  page,
}) => {
  const requests = [];
  await page.route("**/api/v1/auth/signup", (route) => {
    requests.push(route.request().postDataJSON());
    return route.fulfill({ status: 201, json: { data: member } });
  });
  await page.goto("/#/signup");
  await page.getByLabel("닉네임").fill(member.displayName);
  await fillLogin(page);
  await page.getByLabel("비밀번호 확인").fill("different-password");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "회원가입", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("일치하지 않습니다");
  expect(requests).toHaveLength(0);
  await page.getByLabel("비밀번호 확인").fill("test-password");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "회원가입", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "로그인", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("status").filter({ hasText: "회원가입이 완료" }),
  ).toBeVisible();
  expect(requests).toEqual([
    {
      email: member.email,
      password: "test-password",
      displayName: member.displayName,
    },
  ]);
  await expect(nav(page).getByRole("link")).toHaveCount(3);
});

test("unsupported and malformed auth never log in, private URLs remain gated", async ({
  page,
}) => {
  await page.route("**/api/v1/auth/login", (route) =>
    route.fulfill({ status: 404, json: {} }),
  );
  await page.goto("/#/saved");
  await expect(
    page.getByRole("heading", { name: "로그인이 필요합니다" }),
  ).toBeVisible();
  await page
    .locator(".workspace-header")
    .getByRole("button", { name: "로그인" })
    .click();
  await fillLogin(page);
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "로그인", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "항목을 찾을 수 없습니다",
  );
  await page.route("**/api/v1/auth/login", (route) =>
    route.fulfill({ json: { data: {} } }),
  );
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "로그인", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "로그인 정보를 확인하지 못했습니다",
  );
  await expect(nav(page).getByRole("link")).toHaveCount(3);
});
