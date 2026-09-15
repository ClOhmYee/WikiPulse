import { useCallback } from "react";
import { dataClient } from "../../data/index.js";
import { useAsyncResource } from "../../data/hooks/useAsyncResource.js";

export function useGlobalSearch(query) {
  const term = query.trim();
  const load = useCallback(
    async (signal) => {
      if (!term) return [];
      signal.throwIfAborted();
      await new Promise((resolve, reject) => {
        const cancel = () => {
          window.clearTimeout(timer);
          reject(signal.reason);
        };
        const timer = window.setTimeout(() => {
          signal.removeEventListener("abort", cancel);
          resolve();
        }, 250);
        signal.addEventListener("abort", cancel, { once: true });
      });
      signal.throwIfAborted();
      return (
        await dataClient.listStocks(
          { q: term, offset: 0, limit: 7 },
          { signal },
        )
      ).data.map((stock) => ({
        kind: "stock",
        id: stock.ticker,
        title: `${stock.ticker} · ${stock.name}`,
        detail: [stock.exchange, stock.sector].filter(Boolean).join(" · "),
      }));
    },
    [term],
  );
  return useAsyncResource(load, term);
}
