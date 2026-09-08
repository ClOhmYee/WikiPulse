import { createHttpClient } from "./http.js";
import { adaptResponse } from "./adapters.js";

/** @returns {import('../contracts.js').DataClient} */
export function createApiClient(baseURL, fetcher) {
  const request = createHttpClient(baseURL, fetcher);
  const list =
    (path, paginated = true) =>
    async (params = {}, options) =>
      adaptResponse(await request(path, params, options), {
        list: true,
        paginated,
      });
  const detail = (path) => async (id, options) =>
    adaptResponse(
      await request(`${path}/${encodeURIComponent(id)}`, {}, options),
    );
  return {
    listCategories: async (options) =>
      adaptResponse(await request("/categories", {}, options), { list: true }),
    listEvents: list("/events"),
    getEvent: detail("/events"),
    listEntities: list("/entities"),
    getEntity: detail("/entities"),
    listStocks: list("/stocks"),
    getStock: (symbol, options) =>
      detail("/stocks")(String(symbol).toUpperCase(), options),
    searchWorkspace: list("/search", false),
  };
}
