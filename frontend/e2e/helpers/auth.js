// Intercepted session fixture; real cookies and PostgreSQL are tested by test:accounts.
export async function authenticate(page) {
  await page.route("**/api/v1/me", (route) =>
    route.fulfill({ json: { data: { id: 7, displayName: "테스트 사용자" } } }),
  );
  await page.route("**/api/v1/me/saved-state", (route) =>
    route.fulfill({ json: { data: { issueIds: [], tickers: [] } } }),
  );
  for (const path of ["bookmarks", "watchlist"]) {
    await page.route(`**/api/v1/me/${path}?*`, (route) =>
      route.fulfill({
        json: {
          data: [],
          meta: {
            pagination: { offset: 0, limit: 20, total: 0, hasMore: false },
          },
        },
      }),
    );
  }
}
