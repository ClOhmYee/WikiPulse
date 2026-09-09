import test from "node:test";
import assert from "node:assert/strict";
import { normalizeRoute } from "../src/app/router.js";

test("page paths normalize tickers and trailing slashes without changing query bytes or issue IDs", () => {
  assert.equal(normalizeRoute("/stocks/nvda/?q=a%2Fb&range=7"), "/stocks/NVDA?q=a%2Fb&range=7");
  assert.equal(normalizeRoute("/issues/Case-Sensitive/stocks/"), "/issues/Case-Sensitive/stocks");
  assert.equal(normalizeRoute("/issues/?q=%ED%95%B4%ED%98%91"), "/issues?q=%ED%95%B4%ED%98%91");
  assert.equal(normalizeRoute("/stocks/BRK.B"), "/stocks/BRK.B");
  assert.equal(normalizeRoute("/"), "/");
  assert.equal(normalizeRoute("/%E0%A4%A"), "/not-found");
});
