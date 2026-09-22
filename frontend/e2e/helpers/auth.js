// Authentication fixture only; the application never fabricates a session.
export async function authenticate(page) {
  await page.route("**/api/v1/me", (route) =>
    route.fulfill({ json: { data: { id: 7, displayName: "테스트 사용자" } } }),
  );
  await page.addInitScript(() =>
    sessionStorage.setItem("wikipulse.auth.token", "test-token"),
  );
}
