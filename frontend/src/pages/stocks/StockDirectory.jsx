import { useMemo, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Bookmark,
  ChevronRight,
  Search,
  X,
} from "lucide-react";
import { usePageData } from "../../data/hooks/PageData";
import { EmptyState } from "../../components/ui/EmptyState";
import { Pagination } from "../../components/event/IssueState";
import { metricLabel } from "../event/presentation.js";
import {
  RELATION_LABELS,
  isSaved,
  priceLabel,
  StockMark,
  SaveButton,
  MatchEvidence,
} from "./StockElements";
export default function StockDirectory({
  eventId,
  savedStocks,
  onToggleStock,
}) {
  const {
    stocks,
    getEvent,
    listParams,
    setListParams,
    pagination,
    collectionLimit,
    loading,
  } = usePageData();
  const [query, setQuery] = useState(listParams.q || "");
  const [sector, setSector] = useState(listParams.sector || "");
  const [exchange, setExchange] = useState(listParams.exchange || "");
  const [hasIssues, setHasIssues] = useState(Boolean(listParams.hasIssues));
  const [relationType, setRelationType] = useState("all");
  const [savedOnly, setSavedOnly] = useState(false);
  const [applied, setApplied] = useState({ q: "", sector: "" });
  const activeEvent = eventId ? getEvent(eventId) : null;
  const filteredStocks = useMemo(
    () =>
      stocks.filter((stock) => {
        const relation =
          stock.relations?.find((item) => item.eventId === activeEvent?.id) ||
          stock;
        return (
          (!savedOnly || isSaved(savedStocks, stock.symbol)) &&
          (!eventId ||
            ((!applied.q ||
              `${stock.symbol} ${stock.name}`
                .toLocaleLowerCase()
                .includes(applied.q.toLocaleLowerCase())) &&
              (!applied.sector || stock.sector === applied.sector) &&
              (relationType === "all" || relation.matchPath === relationType)))
        );
      }),
    [
      stocks,
      eventId,
      activeEvent,
      applied,
      relationType,
      savedOnly,
      savedStocks,
    ],
  );
  function submit(event) {
    event.preventDefault();
    if (eventId) setApplied({ q: query.trim(), sector: sector.trim() });
    else
      setListParams({
        q: query.trim() || undefined,
        sector: sector.trim() || undefined,
        exchange: exchange.trim() || undefined,
        hasIssues,
      });
  }
  function resetFilters() {
    setQuery("");
    setSector("");
    setExchange("");
    setHasIssues(false);
    setRelationType("all");
    setSavedOnly(false);
    setApplied({ q: "", sector: "" });
    if (!eventId)
      setListParams({
        q: undefined,
        sector: undefined,
        exchange: undefined,
        hasIssues: false,
        offset: 0,
      });
  }
  if (eventId && !activeEvent)
    return (
      <div className="wp-page">
        <EmptyState
          title="연결할 사건을 찾지 못했습니다."
          description="사건 탐색에서 다른 사건을 선택해 주세요."
          action={
            <a href="#/issues" className="wp-button" data-variant="primary">
              사건 탐색
            </a>
          }
        />
      </div>
    );
  return (
    <div className="wp-page st-page" aria-busy={loading}>
      {activeEvent && (
        <a
          href={`#/issues/${encodeURIComponent(activeEvent.id)}`}
          className="st-back"
        >
          <ArrowLeft size={16} />
          사건으로 돌아가기
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
          {eventId ? stocks.length : (pagination?.total ?? stocks.length)}
          <span>{eventId ? "개 수신" : "개 종목"}</span>
        </span>
      </header>
      {activeEvent && (
        <div className="st-event-context">
          <p>
            연결 설명과 후보 탐색 경로를 함께 확인하세요. 후보 탐색 경로는
            신뢰도 등급이 아닙니다.
          </p>
          <a href={`#/issues/${encodeURIComponent(activeEvent.id)}`}>
            사건 요약
            <ArrowRight size={14} />
          </a>
        </div>
      )}
      <section className="st-stock-browser" aria-label="종목 탐색">
        {loading && (
          <p role="status" className="data-scope">
            종목 목록을 갱신하는 중입니다.
          </p>
        )}
        <form onSubmit={submit} className="data-filters">
          <label className="wp-search st-search">
            <Search size={18} />
            <input
              aria-label="종목 검색"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              maxLength={200}
              placeholder="종목명, 티커 검색"
            />
          </label>
          <label>
            산업
            <input
              className="wp-select"
              aria-label="산업 필터"
              value={sector}
              onChange={(e) => setSector(e.target.value)}
              maxLength={100}
              placeholder="예: Technology"
              list="stock-sectors"
            />
          </label>
          <datalist id="stock-sectors">
            {[
              ...new Set(stocks.map((stock) => stock.sector).filter(Boolean)),
            ].map((value) => (
              <option key={value} value={value} />
            ))}
          </datalist>
          {!eventId && (
            <>
              <label>
                거래소
                <input
                  className="wp-select"
                  aria-label="거래소 필터"
                  value={exchange}
                  onChange={(e) => setExchange(e.target.value)}
                  maxLength={50}
                  placeholder="예: NASDAQ"
                />
              </label>
              <label className="data-filter-checkbox">
                <input
                  type="checkbox"
                  checked={hasIssues}
                  onChange={(e) => setHasIssues(e.target.checked)}
                />
                관련 이슈가 있는 종목만
              </label>
            </>
          )}
          <button
            type="submit"
            className="wp-button"
            data-variant="primary"
            disabled={loading}
          >
            검색 적용
          </button>
        </form>
        <div className="st-filters">
          {activeEvent && (
            <select
              className="wp-select"
              aria-label="연결 유형 필터"
              value={relationType}
              onChange={(e) => setRelationType(e.target.value)}
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
            aria-pressed={savedOnly}
            data-active={savedOnly}
            onClick={() => setSavedOnly(!savedOnly)}
          >
            <Bookmark size={15} fill={savedOnly ? "currentColor" : "none"} />
            관심 종목
          </button>
          <button
            type="button"
            className="wp-text-button"
            onClick={resetFilters}
          >
            필터 초기화
            <X size={13} />
          </button>
        </div>
        <p className="data-scope">
          {eventId
            ? `검색과 필터는 수신한 관련 종목 최대 ${collectionLimit || 100}개 안에서 적용됩니다. 전체 개수는 제공되지 않았습니다.`
            : "검색은 전체 종목에 적용됩니다. 관심 종목 필터는 현재 페이지에서 찾습니다."}{" "}
          <a href="#/saved">보관함 보기</a>
        </p>
        <div className="st-results-bar">
          <span aria-live="polite">
            <strong>{filteredStocks.length}</strong>개 표시
          </span>
        </div>
        {filteredStocks.length ? (
          <div className="st-directory-list">
            <div className="st-list-head" aria-hidden="true">
              <span>종목</span>
              <span>{activeEvent ? "사건과의 연결" : "산업"}</span>
              <span>관련 사건</span>
              <span>가격</span>
              <span>저장</span>
            </div>
            <ul>
              {filteredStocks.map((stock) => {
                const relation =
                  stock.relations?.find(
                    (item) => item.eventId === activeEvent?.id,
                  ) || (stock.matchPath || stock.rationale ? stock : null);
                return (
                  <li className="st-stock-row" key={stock.symbol}>
                    <a
                      className="st-stock-identity"
                      href={`#/stocks/${encodeURIComponent(stock.symbol)}`}
                    >
                      <StockMark stock={stock} />
                      <span>
                        <span className="st-symbol-line">
                          <strong>{stock.symbol}</strong>
                          <small>{stock.exchange}</small>
                        </span>
                        <span className="st-company-name">{stock.name}</span>
                        <span className="st-sector-mobile">
                          {stock.sector || "산업 미제공"}
                        </span>
                      </span>
                    </a>
                    <div className="st-row-context">
                      <span className="st-sector">
                        {stock.sector || "산업 미제공"}
                      </span>
                      {activeEvent && <MatchEvidence relation={relation} />}
                    </div>
                    <a
                      href={`#/stocks/${encodeURIComponent(stock.symbol)}`}
                      className="st-event-count"
                    >
                      <strong>{metricLabel(stock.issueCount, 0)}</strong>
                      <span>
                        {stock.issueCount != null ? "개 사건" : "사건 수"}
                      </span>
                      <ChevronRight size={14} />
                    </a>
                    <div className="st-row-price">
                      <span className="st-mobile-price-label">가격</span>
                      <strong>{priceLabel(stock)}</strong>
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
            title="조건에 맞는 종목이 없습니다."
            description={
              savedOnly
                ? "현재 목록에 저장한 종목이 없습니다. 모든 저장 항목은 보관함에서 확인하세요."
                : "검색어나 산업, 거래소 조건을 바꿔 보세요."
            }
            action={
              <button
                type="button"
                className="wp-button"
                onClick={resetFilters}
              >
                필터 초기화
              </button>
            }
          />
        )}
        {!eventId && (
          <Pagination
            pagination={pagination}
            onChange={setListParams}
            loading={loading}
          />
        )}
      </section>
      <p className="st-data-note">
        가격과 등락률은 제공되지 않았습니다. 종목의 연결 설명은 관련 이슈에서
        확인하세요.
      </p>
    </div>
  );
}
