import { useMemo, useState } from "react";
import { CircleHelp, LayoutGrid, List, Search, X } from "lucide-react";
import { usePageData } from "../../data/hooks/PageData";
import { EventRow } from "../../components/event/EventRow";
import { Pagination } from "../../components/event/IssueState";
import { EmptyState } from "../../components/ui/EmptyState";
import { ISSUE_STATUS_LABELS } from "../event/presentation.js";
export default function ExplorePage({
  initialQuery = "",
  savedEvents,
  onToggleEvent,
}) {
  const {
    events,
    getCategory,
    listParams,
    setListParams,
    pagination,
    loading,
  } = usePageData();
  const [query, setQuery] = useState(initialQuery);
  const [view, setView] = useState("list");
  const [showHelp, setShowHelp] = useState(false);
  const filtered = useMemo(
    () =>
      events.filter((event) =>
        event.title
          .toLocaleLowerCase()
          .includes(query.trim().toLocaleLowerCase()),
      ),
    [events, query],
  );
  return (
    <div className="wp-page explore-page" aria-busy={loading}>
      <div className="wp-page-header">
        <div>
          <h1>사건을 탐색하세요</h1>
          <p className="wp-subtitle">
            흩어진 문서의 움직임에서, 하나의 사건을 발견하세요.
          </p>
        </div>
      </div>
      <div className="explore-toolbar">
        <label className="wp-search">
          <Search size={17} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            maxLength={200}
            placeholder="현재 페이지의 이슈 제목 검색"
            aria-label="사건 검색"
            aria-describedby="issue-search-scope"
          />
          {query && (
            <button
              className="wp-icon-button"
              aria-label="검색어 지우기"
              onClick={() => setQuery("")}
            >
              <X size={15} />
            </button>
          )}
        </label>
        <div className="wp-segment" aria-label="이슈 보기 방식">
          <button
            onClick={() => setView("card")}
            aria-pressed={view === "card"}
          >
            <LayoutGrid size={16} />
            카드
          </button>
          <button
            onClick={() => setView("list")}
            aria-pressed={view === "list"}
          >
            <List size={16} />
            리스트
          </button>
        </div>
      </div>
      <p className="data-scope" id="issue-search-scope">
        제목 검색은 현재 페이지에 표시된 이슈에서 찾습니다. 이슈는 기준 시각이
        최신인 순서로 표시됩니다.
      </p>
      {loading && (
        <p role="status" className="data-scope">
          이슈 목록을 갱신하는 중입니다.
        </p>
      )}
      <div className="data-filters">
        <label>
          분석 상태
          <select
            className="wp-select"
            aria-label="분석 상태"
            value={listParams.status || ""}
            onChange={(e) =>
              setListParams({ status: e.target.value || undefined })
            }
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
            급증 점수는 편집량의 배수나 AI 검증의 확률이 아닙니다. 편집과
            조회수의 신호를 반영하며, 신규 문서와 기존 문서는 계산 방식이
            다릅니다. 분석 상태는 요약이나 종목 연결의 유무를 뜻하지 않습니다.
          </p>
        </div>
      )}
      {!filtered.length ? (
        <EmptyState
          title={
            query
              ? "현재 페이지에서 일치하는 사건이 없습니다"
              : "이 조건에 해당하는 사건이 없습니다"
          }
          description={
            query
              ? "검색어를 바꾸거나 다른 페이지에서 찾아보세요."
              : "분석 상태를 바꿔 보세요."
          }
          action={
            <button
              className="wp-button"
              onClick={() => {
                setQuery("");
                setListParams({
                  status: undefined,
                  offset: 0,
                });
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
              이슈<span className="wp-count">{filtered.length}</span>
            </h2>
          </div>
          <div className="event-list" data-view={view}>
            {filtered.map((event) => (
              <EventRow
                key={event.id}
                category={getCategory(event.category)}
                event={event}
                saved={[event.id, ...(event.aliases || [])].some((id) =>
                  savedEvents.includes(id),
                )}
                onToggle={() =>
                  onToggleEvent(
                    [event.id, ...(event.aliases || [])].find((id) =>
                      savedEvents.includes(id),
                    ) || event.id,
                  )
                }
              />
            ))}
          </div>
        </section>
      )}
      <Pagination
        pagination={pagination}
        onChange={setListParams}
        loading={loading}
      />
    </div>
  );
}
