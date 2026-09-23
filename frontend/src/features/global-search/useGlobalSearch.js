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
      const [issues, stocks] = await Promise.all([
        dataClient.listIssues({ offset: 0, limit: 100 }, { signal }),
        dataClient.listStocks({ q: term, offset: 0, limit: 7 }, { signal }),
      ]);
      const normalized = term.toLowerCase();
      return [
        ...issues.data
          .filter((issue) => issue.label.toLowerCase().includes(normalized))
          .slice(0, 7)
          .map((issue) => ({
            kind: "issue",
            id: issue.id,
            title: issue.label,
            detail: `${issue.memberCount}개 문서`,
          })),
        ...stocks.data.map((stock) => ({
          kind: "stock",
          id: stock.ticker,
          title: `${stock.ticker} · ${stock.name}`,
          detail: [stock.exchange, stock.sector].filter(Boolean).join(" · "),
        })),
      ];
    },
    [term],
  );
  return useAsyncResource(load, term);
}
