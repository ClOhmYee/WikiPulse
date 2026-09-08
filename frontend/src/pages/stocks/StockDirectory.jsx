import { useMemo, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Bookmark,
  ChevronRight,
  GitBranch,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { usePageData } from "../../data/hooks/PageData";
import { EmptyState } from "../../components/ui/EmptyState";
import {
  RELATION_LABELS,
  isSaved,
  priceLabel,
  StockMark,
  SaveButton,
  PriceChange,
} from "./StockElements";
export default function StockDirectory({
  eventId,
  savedStocks,
  onToggleStock,
}) {
  const { stocks, getEvent, isExample } = usePageData();
  const [query, setQuery] = useState("");
  const [sector, setSector] = useState("all");
  const [relationType, setRelationType] = useState("all");
  const [savedOnly, setSavedOnly] = useState(false);
  const [sort, setSort] = useState("events");
  const activeEvent = eventId ? getEvent(eventId) : null;
  const universe = useMemo(
    () =>
      eventId
        ? stocks.filter(
            (stock) =>
              stock.eventIds.includes(eventId) ||
              activeEvent?.stockSymbols?.includes(stock.symbol),
          )
        : stocks,
    [eventId, activeEvent, stocks],
  );
  const sectors = [...new Set(universe.map((stock) => stock.sector))];
  const filteredStocks = useMemo(() => {
    const term = query.trim().toLocaleLowerCase();
    return universe
      .filter((stock) => {
        const matchesQuery =
          !term ||
          `${stock.symbol} ${stock.name} ${stock.sector} ${stock.description}`
            .toLocaleLowerCase()
            .includes(term);
        const matchesSector = sector === "all" || stock.sector === sector;
        const matchesSaved = !savedOnly || isSaved(savedStocks, stock.symbol);
        const matchesRelation =
          relationType === "all" ||
          stock.relations?.some(
            (relation) =>
              (!eventId || relation.eventId === eventId) &&
              relation.type === relationType,
          );
        return matchesQuery && matchesSector && matchesSaved && matchesRelation;
      })
      .sort((a, b) =>
        sort === "name"
          ? a.symbol.localeCompare(b.symbol)
          : b.eventIds.length - a.eventIds.length ||
            a.symbol.localeCompare(b.symbol),
      );
  }, [
    universe,
    query,
    sector,
    savedOnly,
    savedStocks,
    relationType,
    eventId,
    sort,
  ]);
  const hasFilters = Boolean(
    query || sector !== "all" || relationType !== "all" || savedOnly,
  );

  function resetFilters() {
    setQuery("");
    setSector("all");
    setRelationType("all");
    setSavedOnly(false);
  }

  if (eventId && !activeEvent) {
    return (
      <div className="wp-page">
        <EmptyState
          title="연결할 사건을 찾지 못했습니다."
          description="사건 탐색에서 다른 사건을 선택해 주세요."
          action={
            <a href="#/explore" className="wp-button" data-variant="primary">
              사건 탐색
            </a>
          }
        />
      </div>
    );
  }

  return (
    <div className="wp-page st-page">
      {activeEvent && (
        <a href={`#/events/${activeEvent.id}`} className="st-back">
          <ArrowLeft size={16} aria-hidden="true" /> 사건으로 돌아가기
        </a>
      )}
      <header className="wp-page-header st-directory-header">
        <div>
          <h1>
            {activeEvent
              ? "이 사건과 연결된 종목"
              : "종목에서 사건의 맥락을 찾으세요."}
          </h1>
          <p className="wp-subtitle">
            {activeEvent
              ? activeEvent.title
              : "기업 이름 너머, 산업과 공급망을 따라 연결된 사건을 살펴보세요."}
          </p>
        </div>
        <span className="st-directory-total">
          {universe.length}
          <span>개 종목</span>
        </span>
      </header>

      {activeEvent && (
        <div className="st-event-context">
          <GitBranch size={18} aria-hidden="true" />
          <p>
            종목마다 <strong>어떤 경로로 연결되는지</strong>를 확인할 수
            있습니다.
          </p>
          <a href={`#/events/${activeEvent.id}`}>
            사건 요약
            <ArrowRight size={14} aria-hidden="true" />
          </a>
        </div>
      )}

      <section className="st-stock-browser" aria-label="종목 탐색">
        <div className="st-filters">
          <label className="wp-search st-search">
            <Search size={18} aria-hidden="true" />
            <input
              aria-label="종목 검색"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="종목명, 티커, 산업 검색"
            />
            {query && (
              <button
                type="button"
                className="st-clear"
                aria-label="종목 검색어 지우기"
                onClick={() => setQuery("")}
              >
                <X size={16} />
              </button>
            )}
          </label>
          <label className="st-filter-select">
            <SlidersHorizontal size={16} aria-hidden="true" />
            <select
              className="wp-select"
              aria-label="산업 필터"
              value={sector}
              onChange={(event) => setSector(event.target.value)}
            >
              <option value="all">모든 산업</option>
              {sectors.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          {activeEvent && (
            <select
              className="wp-select st-relation-select"
              aria-label="연결 유형 필터"
              value={relationType}
              onChange={(event) => setRelationType(event.target.value)}
            >
              <option value="all">모든 연결 유형</option>
              {Object.entries(RELATION_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          )}
          <button
            type="button"
            className="wp-chip st-saved-filter"
            data-active={savedOnly}
            aria-pressed={savedOnly}
            onClick={() => setSavedOnly((value) => !value)}
          >
            <Bookmark
              size={15}
              fill={savedOnly ? "currentColor" : "none"}
              aria-hidden="true"
            />{" "}
            관심 종목
          </button>
        </div>
        <div className="st-results-bar">
          <div>
            <span aria-live="polite">
              <strong>{filteredStocks.length}</strong>개 종목
            </span>
            {hasFilters && (
              <button type="button" onClick={resetFilters}>
                필터 초기화
                <X size={13} aria-hidden="true" />
              </button>
            )}
          </div>
          <select
            className="st-sort"
            aria-label="종목 정렬"
            value={sort}
            onChange={(event) => setSort(event.target.value)}
          >
            <option value="events">관련 사건 많은 순</option>
            <option value="name">티커 이름순</option>
          </select>
        </div>

        {filteredStocks.length ? (
          <div className="st-directory-list">
            <div className="st-list-head" aria-hidden="true">
              <span>종목</span>
              <span>{activeEvent ? "사건과의 연결" : "주요 연결 맥락"}</span>
              <span>관련 사건</span>
              <span>{isExample ? "예시 가격" : "가격"}</span>
              <span>저장</span>
            </div>
            <ul>
              {filteredStocks.map((stock) => {
                const relation = stock.relations?.find(
                  (item) => !eventId || item.eventId === eventId,
                );
                const leadEvent = relation
                  ? getEvent(relation.eventId)
                  : getEvent(stock.eventIds[0]);
                return (
                  <li className="st-stock-row" key={stock.symbol}>
                    <a
                      className="st-stock-identity"
                      href={`#/stocks/${stock.symbol}`}
                    >
                      <StockMark stock={stock} />
                      <span>
                        <span className="st-symbol-line">
                          <strong>{stock.symbol}</strong>
                          <small>{stock.market}</small>
                        </span>
                        <span className="st-company-name">{stock.name}</span>
                        <span className="st-sector-mobile">{stock.sector}</span>
                      </span>
                    </a>
                    <div className="st-row-context">
                      <div>
                        <span className="st-sector">{stock.sector}</span>
                        {relation && (
                          <span className="st-relation-label">
                            {RELATION_LABELS[relation.type] || relation.type}
                          </span>
                        )}
                      </div>
                      <p>
                        {activeEvent && relation
                          ? relation.explanation
                          : leadEvent?.title || stock.description}
                      </p>
                    </div>
                    <a
                      href={`#/stocks/${stock.symbol}`}
                      className="st-event-count"
                    >
                      <strong>{stock.eventIds.length}</strong>
                      <span>개 사건</span>
                      <ChevronRight size={14} aria-hidden="true" />
                    </a>
                    <div className="st-row-price">
                      <span className="st-mobile-price-label">
                        {isExample ? "예시 가격" : "가격"}
                      </span>
                      <strong>{priceLabel(stock)}</strong>
                      <PriceChange value={stock.change} />
                    </div>
                    <SaveButton
                      stock={stock}
                      savedStocks={savedStocks}
                      onToggleStock={onToggleStock}
                    />
                  </li>
                );
              })}
            </ul>
          </div>
        ) : (
          <EmptyState
            title={
              savedOnly && !query && sector === "all"
                ? "아직 관심 종목이 없습니다."
                : "조건에 맞는 종목이 없습니다."
            }
            description={
              savedOnly && !query && sector === "all"
                ? "종목 옆의 저장 버튼을 누르면 이곳에서 다시 볼 수 있어요."
                : "검색어나 산업, 연결 유형을 바꿔 보세요."
            }
            action={
              <button
                type="button"
                className="wp-button"
                onClick={resetFilters}
              >
                전체 종목 보기
              </button>
            }
          />
        )}
      </section>
      <p className="st-data-note">
        {isExample
          ? "가격과 사건 연결은 화면 탐색을 위한 예시 데이터입니다."
          : "가격과 사건 연결의 출처 및 기준 시각을 확인해 주세요."}
      </p>
    </div>
  );
}
