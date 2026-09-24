import { useMemo, useState } from "react";
import {
  ArrowRight,
  CircleHelp,
  LayoutGrid,
  List,
  Search,
  X,
} from "lucide-react";
import { IssueState, Pagination } from "../../components/event/IssueState.jsx";
import { EmptyState } from "../../components/ui/EmptyState.jsx";
import { searchIssueGroups } from "../../data/historyPreview.js";
import {
  ISSUE_STATUS_LABELS,
  metricLabel,
  timestampLabel,
} from "../event/presentation.js";

const PAGE_SIZE = 20;

function LocalRankings({ groups }) {
  const [period, setPeriod] = useState("monthly");
  const latest = groups[0]?.lastSeen;
  const cutoff =
    latest &&
    new Date(Date.parse(latest) - (period === "monthly" ? 30 : 365) * 86400000);
  const entries = groups
    .filter(
      (group) => !cutoff || Date.parse(group.lastSeen) >= cutoff.getTime(),
    )
    .sort((a, b) => b.latestScore - a.latestScore)
    .slice(0, 10);
  return (
    <aside className="explore-rankings" aria-label="기간별 이슈 Top 10">
      <section className="explore-ranking">
        <div className="explore-ranking-heading">
          <h2>TOP 10</h2>
          <div className="wp-segment" role="group" aria-label="순위 기간">
            {[
              ["monthly", "30일"],
              ["yearly", "1년"],
            ].map(([key, label]) => (
              <button
                key={key}
                aria-pressed={period === key}
                onClick={() => setPeriod(key)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <p className="data-scope">로컬 추출본의 최신 시점·급증 점수 기준</p>
        <ol className="explore-ranking-list">
          {entries.map((group) => (
            <li key={group.key}>
              <a href={`#/issue-history-preview/${group.latestId}`}>
                <span>{group.label}</span>
                <strong>{metricLabel(group.latestScore)}</strong>
              </a>
            </li>
          ))}
        </ol>
      </section>
    </aside>
  );
}

export default function HistoryPreviewExplore({ groups, data }) {
  const initialQuery =
    new URLSearchParams(window.location.hash.split("?")[1] || "").get("q") ||
    "";
  const [query, setQuery] = useState(initialQuery);
  const [view, setView] = useState("list");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [showHelp, setShowHelp] = useState(false);
  const detailById = useMemo(
    () => new Map(data.details.map((detail) => [detail.id, detail])),
    [data],
  );
  const reportById = useMemo(
    () => new Map(data.reports.map((report) => [report.id, report])),
    [data],
  );
  const result = useMemo(
    () =>
      searchIssueGroups(
        status
          ? groups.filter((group) => group.latestStatus === status)
          : groups,
        query,
        offset,
        PAGE_SIZE,
      ),
    [groups, query, offset, status],
  );
  const pagination = {
    offset,
    limit: PAGE_SIZE,
    total: result.total,
    hasMore: offset + PAGE_SIZE < result.total,
  };
  const hrefFor = (group) =>
    `#/issue-history-preview/${group.latestId}${query ? `?q=${encodeURIComponent(query)}` : ""}`;
  return (
    <div className="wp-page explore-page history-preview-explore">
      <div className="wp-page-header">
        <div>
          <h1>이슈 탐색</h1>
          <p className="wp-subtitle">
            대표 문서를 검색하고 날짜별 기록을 확인하세요.
          </p>
        </div>
        <span className="hp-local-label">로컬 검증 전용</span>
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
            전체 로컬 추출본에서 대표 문서 제목을 검색합니다. 날짜별 기록은 대표
            문서 한 건으로 묶어 표시합니다.
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
                {Object.entries(ISSUE_STATUS_LABELS).map(([value, label]) => (
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
                급증 점수는 편집량의 배수나 AI 검증의 확률이 아닙니다. 이 목록의
                점수와 상태는 해당 대표 문서의 최신 기록 값입니다.
              </p>
            </div>
          )}
          {!result.items.length ? (
            <EmptyState
              title={
                query
                  ? "일치하는 대표 문서가 없습니다"
                  : "이 조건에 해당하는 사건이 없습니다"
              }
              description="검색어나 분석 상태를 바꿔 보세요."
              action={
                <button
                  className="wp-button"
                  onClick={() => {
                    setQuery("");
                    setStatus("");
                    setOffset(0);
                  }}
                >
                  필터 초기화
                </button>
              }
            />
          ) : (
            <section className="event-list-section">
              <div className="wp-section-heading">
                <h2>
                  이슈<span className="wp-count">{result.total}</span>
                </h2>
              </div>
              <div className="event-list" data-view={view}>
                {result.items.map((group) => {
                  const detail = detailById.get(group.latestId);
                  const report = reportById.get(group.latestId);
                  const href = hrefFor(group);
                  return (
                    <article
                      key={group.key}
                      className="event-row hp-openable-row"
                      onDoubleClick={() => {
                        window.location.hash = href.slice(1);
                      }}
                    >
                      <div className="event-row__main">
                        <a href={href} className="event-row__title">
                          {group.label}
                          <ArrowRight size={17} />
                        </a>
                        {report?.summary && <p>{report.summary}</p>}
                        <div className="event-row__meta">
                          <span>
                            {group.count}개 기록 ·{" "}
                            {group.source === "replay"
                              ? "과거 재구성"
                              : "실시간"}
                          </span>
                          <time dateTime={group.lastSeen}>
                            {timestampLabel(group.lastSeen)}
                          </time>
                          <IssueState status={group.latestStatus} />
                        </div>
                      </div>
                      <div className="event-row__signal">
                        <strong>{metricLabel(group.latestScore)}</strong>
                        <span>급증 점수</span>
                      </div>
                      <div className="event-row__edits">
                        <strong>{detail ? detail.stocks.length : "—"}</strong>
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
            onChange={({ offset: next }) => setOffset(next)}
          />
        </div>
        <LocalRankings groups={groups} />
      </div>
    </div>
  );
}
