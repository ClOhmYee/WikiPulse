import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { dataClient } from "../index.js";
import { loadPageData } from "../resources.js";
import { nextListParams } from "../pagination.js";
import { useAsyncResource } from "./useAsyncResource.js";
import { EmptyState } from "../../components/ui/EmptyState";

const Context = createContext(null);
// 종목 탐색은 "관련 이슈가 있는 종목만"을 기본 ON 으로 둔다(WP-189) — 알파벳순
// 기본이면 A·AA… 만 보여 매칭·가격 있는 종목(BA·DAL 등)이 첫 페이지에 안 뜬다.
const defaultParams = (resource) => ({
  offset: 0,
  limit: 20,
  ...(resource === "stocks" ? { hasIssues: true } : {}),
});
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
  const routeIdentity = JSON.stringify({ resource, id });
  const [queryState, setQueryState] = useState({
    routeIdentity,
    params: defaultParams(resource),
  });
  const listParams = useMemo(
    () =>
      queryState.routeIdentity === routeIdentity
        ? queryState.params
        : defaultParams(resource),
    [queryState, routeIdentity, resource],
  );
  const key = JSON.stringify({
    resource,
    id,
    ...(["explore", "stocks"].includes(resource) ? { listParams } : {}),
    ...(resource === "saved" ? { savedEvents, savedStocks } : {}),
  });
  const load = useCallback(
    async (signal) => {
      const { resource: kind, ...params } = JSON.parse(key);
      return {
        ...(await loadPageData(dataClient, kind, params, { signal })),
        routeIdentity,
      };
    },
    [key, routeIdentity],
  );
  const result = useAsyncResource(load, key);
  const { loading, error, reload } = result;
  // Removing a bookmark must not remount the saved page and reset its active tab.
  const data =
    result.data ||
    (["saved", "explore", "stocks"].includes(resource) &&
    loading &&
    result.previousData?.routeIdentity === routeIdentity
      ? result.previousData
      : null);
  const snapshotTs = resource === "explore" ? data?.meta.snapshotTs : undefined;
  const sourceSnapshots =
    resource === "explore" ? data?.meta.sourceSnapshots : undefined;
  const setListParams = useCallback(
    (update) => {
      setQueryState((current) => {
        const previous =
          current.routeIdentity === routeIdentity
            ? current.params
            : defaultParams(resource);
        const partial =
          typeof update === "function" ? update(previous) : update;
        return {
          routeIdentity,
          params: nextListParams(
            previous,
            partial,
            snapshotTs,
            sourceSnapshots,
          ),
        };
      });
    },
    [routeIdentity, snapshotTs, sourceSnapshots, resource],
  );
  const value = useMemo(
    () =>
      data && {
        ...data,
        loading,
        listParams,
        setListParams,
        isExample: data.meta?.dataMode === "mock",
        getEvent: (id) =>
          data.events.find(
            (item) =>
              item.id === String(id) || item.aliases.includes(String(id)),
          ),
        getEntity: (id) => data.entities.find((item) => item.id === String(id)),
        getStock: (symbol) =>
          data.stocks.find(
            (item) => item.symbol === String(symbol ?? "").toUpperCase(),
          ),
        getCategory: (id) => data.categories.find((item) => item.id === id),
      },
    [data, loading, listParams, setListParams],
  );
  useEffect(() => {
    onSource?.(data?.meta || null);
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
