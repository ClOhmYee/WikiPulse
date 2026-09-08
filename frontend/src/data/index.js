import { readDataConfig } from "./config.js";

let clientPromise;
function getClient() {
  if (!clientPromise) {
    clientPromise = Promise.resolve().then(async () => {
      const { source, baseURL } = readDataConfig(import.meta.env);
      if (source === "mock")
        return (await import("./mock/client.js")).mockClient;
      return (await import("./api/client.js")).createApiClient(baseURL);
    });
  }
  return clientPromise;
}

/** @type {import('./contracts.js').DataClient} */
export const dataClient = Object.fromEntries(
  [
    "listCategories",
    "listEvents",
    "getEvent",
    "listEntities",
    "getEntity",
    "listStocks",
    "getStock",
    "searchWorkspace",
  ].map((method) => [
    method,
    async (...args) => (await getClient())[method](...args),
  ]),
);
