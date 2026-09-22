import { useCallback, useState } from "react";
import { ArrowRight, Bookmark, Search } from "lucide-react";
import { useAsyncResource } from "../../data/hooks/useAsyncResource";
import { authRequest } from "../../features/auth/client";
import { issueView, stockView } from "../../data/resources";
import { Pagination } from "../../components/event/IssueState";
import { EmptyState } from "../../components/ui/EmptyState";
import { EventRow } from "../../components/event/EventRow";
import "./saved.css";

export default function SavedPage({
  savedEvents,
  savedStocks,
  onToggleEvent,
  onToggleStock,
  savedStatus,
  reloadSaved,
}) {
  const [tab, setTab] = useState("events");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const key = JSON.stringify({ tab, query, offset, savedEvents, savedStocks });
  const load = useCallback(
    async (signal) => {
      const { tab, query, offset } = JSON.parse(key);
      return authRequest(
        `/me/${tab === "events" ? "bookmarks" : "watchlist"}?${new URLSearchParams({ q: query, offset, limit: 20 })}`,
        { signal, envelope: true },
      );
    },
    [key],
  );
  const result = useAsyncResource(load, key);
  const selectedEvents =
    tab === "events"
      ? (result.data?.data || []).map((value) => issueView(value))
      : [];
  const selectedStocks =
    tab === "stocks"
      ? (result.data?.data || []).map((value) => stockView(value))
      : [];
  return (
    <div className="wp-page saved-page">
      <div className="wp-page-header">
        <div>
          <h1>관심의 흐름을 이어가세요</h1>
          <p className="wp-subtitle">
            저장한 사건과 종목을 한곳에서 다시 살펴보세요.
          </p>
        </div>
        <Bookmark size={27} strokeWidth={1.3} />
      </div>
      <div className="wp-tabs">
        <button
          aria-pressed={tab === "events"}
          onClick={() => {
            setTab("events");
            setQuery("");
            setOffset(0);
          }}
        >
          저장한 사건 <span>{savedStatus === "ready" ? savedEvents.length : "—"}</span>
        </button>
        <button
          aria-pressed={tab === "stocks"}
          onClick={() => {
            setTab("stocks");
            setQuery("");
            setOffset(0);
          }}
        >
          관심 종목 <span>{savedStatus === "ready" ? savedStocks.length : "—"}</span>
        </button>
      </div>
      <label className="wp-search saved-search">
        <Search size={17} />
        <input
          aria-label="보관함 검색"
          placeholder="보관함에서 검색"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOffset(0);
          }}
        />
      </label>
      {result.loading ? (
        <p role="status">보관함을 불러오고 있습니다.</p>
      ) : result.error ? (
        <div role="alert">
          {result.error.message}{" "}
          <button className="wp-button" onClick={result.reload}>
            다시 시도
          </button>
        </div>
      ) : tab === "events" ? (
        selectedEvents.length ? (
          <div className="event-list">
            {selectedEvents.map((event) => (
              <EventRow
                category={null}
                key={event.id}
                event={event}
                saved
                onToggle={() =>
                  onToggleEvent(event.savedId || event.id, [
                    event.id,
                    ...(event.aliases || []),
                  ])
                }
              />
            ))}
          </div>
        ) : (
          <EmptyState
            title={
              query
                ? "검색 결과가 없습니다"
                : "다음에 다시 보고 싶은 사건을 담아보세요"
            }
            description={
              query
                ? "다른 검색어로 보관함을 찾아보세요."
                : "사건의 북마크를 누르면 이곳에서 이어서 탐색할 수 있어요."
            }
            action={
              <a className="wp-button" data-variant="primary" href="#/issues">
                사건 탐색하기
                <ArrowRight size={16} />
              </a>
            }
          />
        )
      ) : selectedStocks.length ? (
        <div className="saved-stock-list">
          {selectedStocks.map((stock) => (
            <article key={stock.symbol}>
              <div className="stock-monogram">{stock.symbol.slice(0, 1)}</div>
              <a href={`#/stocks/${stock.symbol}`}>
                <strong>{stock.name}</strong>
                <span>
                  {stock.symbol} · {stock.sector}
                </span>
              </a>
              <span className="wp-muted">
                {Number.isInteger(stock.issueCount)
                  ? `관련 사건 ${stock.issueCount}개`
                  : "관련 사건 수 미제공"}
              </span>
              <button
                className="wp-icon-button"
                aria-label={`${stock.name} 관심 종목 해제`}
                onClick={() => onToggleStock(stock.symbol)}
              >
                <Bookmark size={18} fill="currentColor" />
              </button>
            </article>
          ))}
        </div>
      ) : (
        <EmptyState
          title={query ? "검색 결과가 없습니다" : "궁금한 종목을 저장해 보세요"}
          description="종목을 저장하고 연결된 사건의 맥락을 다시 확인하세요."
          action={
            <a className="wp-button" data-variant="primary" href="#/stocks">
              종목 탐색하기
              <ArrowRight size={16} />
            </a>
          }
        />
      )}
      <Pagination
        pagination={result.data?.meta?.pagination}
        onChange={({ offset }) => setOffset(offset)}
        loading={result.loading}
      />
      {savedStatus === "error" && (
        <button className="wp-button" onClick={reloadSaved}>
          저장 상태 다시 확인
        </button>
      )}
      <p className="saved-note">
        계정에 저장되어 다른 기기에서도 이어서 확인할 수 있습니다.
      </p>
    </div>
  );
}
