import { useState } from "react";
import { ArrowRight, Bookmark, Search } from "lucide-react";
import { usePageData } from "../../data/hooks/PageData";
import { EmptyState } from "../../components/ui/EmptyState";
import { EventRow } from "../../components/event/EventRow";
import "./saved.css";

export default function SavedPage({
  savedEvents,
  savedStocks,
  onToggleEvent,
  onToggleStock,
}) {
  const {
    events,
    stocks,
    getCategory,
    missingSavedEvents = [],
    missingSavedStocks = [],
  } = usePageData();
  const [tab, setTab] = useState("events");
  const [query, setQuery] = useState("");
  const matches = (value) =>
    value.toLowerCase().includes(query.trim().toLowerCase());
  const selectedEvents = events.filter(
    (event) =>
      savedEvents.includes(event.savedId || event.id) &&
      matches(`${event.title} ${event.summary}`),
  );
  const selectedStocks = stocks.filter(
    (stock) =>
      savedStocks.includes(stock.symbol) &&
      matches(`${stock.symbol} ${stock.name}`),
  );
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
          }}
        >
          저장한 사건 <span>{savedEvents.length}</span>
        </button>
        <button
          aria-pressed={tab === "stocks"}
          onClick={() => {
            setTab("stocks");
            setQuery("");
          }}
        >
          관심 종목 <span>{savedStocks.length}</span>
        </button>
      </div>
      <label className="wp-search saved-search">
        <Search size={17} />
        <input
          aria-label="보관함 검색"
          placeholder="보관함에서 검색"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </label>
      {(tab === "events" ? missingSavedEvents : missingSavedStocks).length >
        0 && (
        <section
          className="saved-unavailable"
          aria-label="조회할 수 없는 저장 항목"
        >
          <p>
            다음 저장 항목은 현재 조회할 수 없습니다. 보관함에서 직접 해제할 수
            있어요.
          </p>
          {(tab === "events" ? missingSavedEvents : missingSavedStocks).map(
            (id) => (
              <button
                key={id}
                className="wp-button"
                onClick={() =>
                  tab === "events" ? onToggleEvent(id) : onToggleStock(id)
                }
              >
                {id} 저장 해제
              </button>
            ),
          )}
        </section>
      )}
      {tab === "events" ? (
        selectedEvents.length ? (
          <div className="event-list">
            {selectedEvents.map((event) => (
              <EventRow
                category={getCategory(event.category)}
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
      <p className="saved-note">
        보관함은 이 브라우저에 저장됩니다. 예시 데이터와 서버 데이터의 보관함은
        각각 보관합니다.
      </p>
    </div>
  );
}
