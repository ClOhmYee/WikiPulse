import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
} from "react";
import { dataClient } from "../index.js";
import { loadPageData } from "../resources.js";
import { useAsyncResource } from "./useAsyncResource.js";
import { EmptyState } from "../../components/ui/EmptyState";

const Context = createContext(null);
export function usePageData() {
  const data = useContext(Context);
  if (!data)
    throw new Error("PageDataBoundary 안에서 데이터를 사용해야 합니다.");
  return data;
}
export function PageDataBoundary({
  resource,
  id,
  savedEvents,
  savedStocks,
  onSource,
  children,
}) {
  const key = JSON.stringify({
    resource,
    id,
    ...(resource === "saved" ? { savedEvents, savedStocks } : {}),
  });
  const load = useCallback(
    (signal) => {
      const { resource: kind, ...params } = JSON.parse(key);
      return loadPageData(dataClient, kind, params, { signal });
    },
    [key],
  );
  const result = useAsyncResource(load, key);
  const { loading, error, reload } = result;
  // Removing a bookmark must not remount the saved page and reset its active tab.
  const data =
    result.data ||
    (resource === "saved" && loading ? result.previousData : null);
  const value = useMemo(
    () =>
      data && {
        ...data,
        isExample: data.meta?.dataMode === "mock",
        getEvent: (id) => data.events.find((item) => item.id === id),
        getEntity: (id) => data.entities.find((item) => item.id === id),
        getStock: (symbol) =>
          data.stocks.find(
            (item) => item.symbol === String(symbol ?? "").toUpperCase(),
          ),
        getCategory: (id) => data.categories.find((item) => item.id === id),
      },
    [data],
  );
  useEffect(() => {
    onSource(data?.meta || null);
  }, [data, onSource]);
  if (loading && !data)
    return (
      <div
        className="wp-page wp-loading"
        role="status"
        aria-label="데이터 불러오는 중"
      >
        <span className="wp-skeleton wp-skeleton--heading" />
        <span className="wp-skeleton wp-skeleton--panel" />
        <span className="sr-only">데이터 불러오는 중</span>
      </div>
    );
  if (error)
    return (
      <div className="wp-page">
        <EmptyState
          title="데이터를 불러오지 못했습니다"
          description={error.message}
          action={
            <button className="wp-button" onClick={reload}>
              다시 시도
            </button>
          }
        />
      </div>
    );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
