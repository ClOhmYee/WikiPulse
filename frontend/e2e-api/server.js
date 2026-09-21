import { mockClient } from "../src/data/mock/client.js";

// HTTP stand-in only: these tests do not start Spring or PostgreSQL.
export async function serve(page, override) {
  const calls = [];
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    calls.push(url);
    if (override && (await override({ route, url, calls }))) return;
    const parts = url.pathname
      .slice("/api/v1/".length)
      .split("/")
      .map(decodeURIComponent);
    const params = Object.fromEntries(url.searchParams);
    for (const key of ["offset", "limit"])
      if (params[key] !== undefined) params[key] = Number(params[key]);
    if (params.hasIssues !== undefined)
      params.hasIssues = params.hasIssues === "true";
    try {
      let body;
      if (parts[0] === "issues" && parts.length === 1)
        body = await mockClient.listIssues(params);
      else if (parts[0] === "issues" && parts[1] === "snapshots")
        body = await mockClient.listSnapshots(params);
      else if (parts[0] === "issues" && parts[1] === "map")
        body = await mockClient.getPulseMap(params);
      else if (parts[0] === "issues" && parts[2] === "stocks")
        body = await mockClient.listIssueStocks(parts[1], params);
      else if (parts[0] === "issues" && parts.length === 2)
        body = await mockClient.getIssue(parts[1]);
      else if (parts[0] === "stocks" && parts.length === 1)
        body = await mockClient.listStocks(params);
      else if (parts[0] === "stocks" && parts[2] === "prices")
        body = { data: [] };
      else if (parts[0] === "stocks" && parts[2] === "issues")
        body = await mockClient.listStockIssues(parts[1]);
      else if (parts[0] === "stocks" && parts.length === 2)
        body = await mockClient.getStock(parts[1]);
      else
        throw Object.assign(new Error("unimplemented endpoint"), {
          status: 404,
          code: "NOT_FOUND",
        });
      await route.fulfill({ json: body });
    } catch (error) {
      await route.fulfill({
        status: error.status || 500,
        json: {
          error: { code: error.code || "INTERNAL", message: error.message },
        },
      });
    }
  });
  return calls;
}
