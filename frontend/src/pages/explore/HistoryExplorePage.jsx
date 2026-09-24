import { useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  CircleHelp,
  LayoutGrid,
  List,
  Search,
  X,
} from "lucide-react";
import { dataClient } from "../../data/index.js";
import { useAsyncResource } from "../../data/hooks/useAsyncResource.js";
import { IssueState, Pagination } from "../../components/event/IssueState.jsx";
import { EmptyState } from "../../components/ui/EmptyState.jsx";
import {
  ISSUE_STATUS_LABELS,
  metricLabel,
  timestampLabel,
} from "../event/presentation.js";
import IssueRankings from "./IssueRankings.jsx";
import "./explore.css";
import "./history-explore.css";

export default function HistoryExplorePage({ initialQuery = "" }) {
  const [query, setQuery] = useState(initialQuery);
  const [settledQuery, setSettledQuery] = useState(initialQuery.trim());
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [view, setView] = useState("list");
  const [showHelp, setShowHelp] = useState(false);
  useEffect(() => {
    const timer = globalThis.setTimeout(
      () => setSettledQuery(query.trim()),
      250,
    );
    return () => globalThis.clearTimeout(timer);
  }, [query]);
  const key = JSON.stringify({ settledQuery, status, offset });
  const load = useCallback(
    (signal) =>
      dataClient.listIssueHistoryGroups(
        {
          q: settledQuery || undefined,
          status: status || undefined,
          offset,
          limit: 20,
        },
        { signal },
      ),
    [settledQuery, status, offset],
  );
  const { data, loading, error, reload } = useAsyncResource(load, key);
  const groups = data?.data || [];
  const pagination = data?.meta.pagination;
  const hrefFor = (group) =>
    `#/issues/${group.defaultReportId || group.id}${settledQuery ? `?q=${encodeURIComponent(settledQuery)}` : ""}`;

  return (
    <div className="wp-page explore-page history-explore" aria-busy={loading}>
      <div className="wp-page-header">
        <div>
          <h1>이슈 탐색</h1>
          <p className="wp-subtitle">
            대표 문서를 검색하고 날짜별 기록을 확인하세요.
          </p>
        </div>
      </div>
      <div className="explore-layout">
        <div className="explore-results">
          <div className="explore-toolbar">
            <label className="wp-search">
              <Search size={17} />
              <input
                type="search"
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setOffset(0);
                }}
                maxLength={200}
                placeholder="대표 문서 제목 검색"
                aria-label="사건 검색"
                aria-describedby="issue-search-scope"
              />
              {query && (
                <button
                  className="wp-icon-button"
                  aria-label="검색어 지우기"
                  onClick={() => {
                    setQuery("");
                    setOffset(0);
                  }}
                >
                  <X size={15} />
                </button>
              )}
            </label>
            <div className="wp-segment" aria-label="이슈 보기 방식">
              <button
                onClick={() => setView("list")}
                aria-pressed={view === "list"}
              >
                <List size={16} />
                리스트
              </button>
              <button
                onClick={() => setView("card")}
                aria-pressed={view === "card"}
              >
                <LayoutGrid size={16} />
                카드
              </button>
            </div>
          </div>
          <p className="data-scope" id="issue-search-scope">
            전체 완료 기록의 대표 문서 제목을 검색합니다. 같은 대표 문서의
            날짜별 기록은 한 건으로 표시합니다.
          </p>
          <div className="data-filters">
            <label>
              분석 상태
              <select
                className="wp-select"
                aria-label="분석 상태"
                value={status}
                onChange={(event) => {
                  setStatus(event.target.value);
                  setOffset(0);
                }}
              >
                <option value="">모든 상태</option>
                {Object.entries(ISSUE_STATUS_LABELS)
                  .filter(([value]) => value !== "DISCARDED")
                  .map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
              </select>
            </label>
            <button
              className="wp-text-button"
              aria-expanded={showHelp}
              onClick={() => setShowHelp(!showHelp)}
            >
              <CircleHelp size={15} />
              급증 점수란?
            </button>
          </div>
          {showHelp && (
            <div className="wp-explainer">
              <strong>문서에서 포착한 변화의 크기를 나타냅니다.</strong>
              <p>
                급증 점수는 편집량의 배수나 AI 검증의 확률이 아닙니다. 편집과
                조회수의 신호를 반영하며, 신규 문서와 기존 문서는 계산 방식이
                다릅니다. 분석 상태는 요약이나 종목 연결의 유무를 뜻하지
                않습니다.
              </p>
            </div>
          )}
          {loading && (
            <p role="status" className="data-scope">
              대표 문서를 불러오는 중입니다.
            </p>
          )}
          {error && (
            <div role="alert" className="wp-explainer">
              <p>대표 문서를 불러오지 못했습니다.</p>
              <button className="wp-text-button" onClick={reload}>
                다시 시도
              </button>
            </div>
          )}
          {!loading && !error && !groups.length && (
            <EmptyState
              title="일치하는 대표 문서가 없습니다"
              description="검색어나 분석 상태를 바꿔 보세요."
            />
          )}
          {!!groups.length && (
            <section className="event-list-section">
              <div className="wp-section-heading">
                <h2>
                  이슈<span className="wp-count">{pagination.total}</span>
                </h2>
              </div>
              <div className="event-list" data-view={view}>
                {groups.map((group) => {
                  const href = hrefFor(group);
                  return (
                    <article
                      key={`${group.source}:${group.id}`}
                      className="event-row"
                      onDoubleClick={() => {
                        window.location.hash = href.slice(1);
                      }}
                    >
                      <div className="event-row__main">
                        <a href={href} className="event-row__title">
                          {group.label}
                          <ArrowRight size={17} />
                        </a>
                        {group.defaultReportId === group.id &&
                          group.summary && <p>{group.summary}</p>}
                        <div className="event-row__meta">
                          <span>
                            {group.occurrenceCount}개 기록 ·{" "}
                            {group.source === "replay"
                              ? "과거 재구성"
                              : "실시간"}
                          </span>
                          <time dateTime={group.snapshotTs}>
                            {timestampLabel(group.snapshotTs)}
                          </time>
                          <IssueState status={group.status} />
                        </div>
                      </div>
                      <div className="event-row__signal">
                        <strong>{metricLabel(group.pulseScore)}</strong>
                        <span>급증 점수</span>
                      </div>
                      <div className="event-row__edits">
                        <strong>{metricLabel(group.stockCount, 0)}</strong>
                        <span>관련 종목</span>
                      </div>
                    </article>
                  );
                })}
              </div>
            </section>
          )}
          <Pagination
            pagination={pagination}
            loading={loading}
            onChange={({ offset: next }) => setOffset(next)}
          />
        </div>
        <IssueRankings />
      </div>
    </div>
  );
}
