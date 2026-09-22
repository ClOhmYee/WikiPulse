import { createHttpClient } from "./http.js";
import {
  adaptResponse,
  issueCard,
  issueDetail,
  stockCard,
  stockDetail,
  stockPrice,
  relatedStock,
} from "./adapters.js";
import { validateMap, validateSnapshots } from "../pulse/contract.js";
import { validateRankings } from "../rankings.js";

/** @returns {import('../contracts.js').DataClient} */
export function createApiClient(baseURL, fetcher) {
  const request = createHttpClient(baseURL, fetcher);
  const pathId = (value) => encodeURIComponent(String(value));
  const list = async (path, params, options, validate, paginated = false) =>
    adaptResponse(await request(path, params, options), {
      list: true,
      paginated,
      validate,
    });
  return {
    dataSource: "api",
    getIssueRankings: async (params = {}, options) =>
      validateRankings(await request("/issues/rankings", params, options)),
    listIssues: (params = {}, options) =>
      list("/issues", params, options, issueCard, true),
    getIssue: async (id, options) =>
      adaptResponse(await request(`/issues/${pathId(id)}`, {}, options), {
        validate: issueDetail,
      }),
    listIssueStocks: (id, params = {}, options) =>
      list(`/issues/${pathId(id)}/stocks`, params, options, relatedStock),
    listStocks: (params = {}, options) =>
      list("/stocks", params, options, stockCard, true),
    getStock: async (ticker, options) =>
      adaptResponse(
        await request(
          `/stocks/${pathId(String(ticker).toUpperCase())}`,
          {},
          options,
        ),
        { validate: stockDetail },
      ),
    listStockIssues: (ticker, options) =>
      list(
        `/stocks/${pathId(String(ticker).toUpperCase())}/issues`,
        {},
        options,
        issueCard,
      ),
    getStockPrices: (ticker, params = {}, options) =>
      list(
        `/stocks/${pathId(String(ticker).toUpperCase())}/prices`,
        params,
        options,
        stockPrice,
      ),
    listSnapshots: async (params = {}, options) =>
      validateSnapshots(await request("/issues/snapshots", params, options)),
    getPulseMap: async (params = {}, options) =>
      validateMap(await request("/issues/map", params, options), params),
  };
}
