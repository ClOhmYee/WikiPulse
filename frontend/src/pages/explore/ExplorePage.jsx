import { useMemo, useState } from "react";
import {
  ArrowDownUp,
  CircleHelp,
  LayoutGrid,
  List,
  Search,
  X,
} from "lucide-react";
import { usePageData } from "../../data/hooks/PageData";
import { EventRow } from "../../components/event/EventRow";
import { EmptyState } from "../../components/ui/EmptyState";

export default function ExplorePage({
  initialQuery = "",
  savedEvents,
  onToggleEvent,
}) {
  const { categories, events, getCategory, meta, isExample } = usePageData();
  const [query, setQuery] = useState(initialQuery);
  const [category, setCategory] = useState("all");
  const [sort, setSort] = useState("pulse");
  const [view, setView] = useState("list");
  const [showHelp, setShowHelp] = useState(false);
  const filtered = useMemo(
    () =>
      events
        .filter(
          (event) =>
            (category === "all" || event.category === category) &&
            `${event.title} ${event.summary} ${event.keywords.join(" ")}`
              .toLowerCase()
              .includes(query.trim().toLowerCase()),
        )
        .sort((a, b) =>
          sort === "recent"
            ? b.startAt.localeCompare(a.startAt)
            : sort === "documents"
              ? b.articleIds.length - a.articleIds.length
              : b.pulse - a.pulse,
        ),
    [events, category, query, sort],
  );
  return (
    <div className="wp-page explore-page">
      <div className="wp-page-header">
        <div>
          <h1>사건을 탐색하세요</h1>
          <p className="wp-subtitle">
            흩어진 문서의 움직임에서, 하나의 사건을 발견하세요.
          </p>
        </div>
        <div className="explore-date">
          <span>{isExample ? "데모 기준일" : "데이터 기준일"}</span>
          <strong>{meta.asOf?.replaceAll("-", ". ") || "기준일 미제공"}</strong>
        </div>
      </div>
      <div className="explore-toolbar">
        <label className="wp-search">
          <Search size={17} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="사건, 주제, 키워드 검색"
            aria-label="사건 검색"
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
      <div className="explore-filter-row">
        <div className="wp-filter-chips" aria-label="사건 주제">
          <button
            className="wp-chip"
            data-active={category === "all"}
            aria-pressed={category === "all"}
            onClick={() => setCategory("all")}
          >
            전체 <span>{events.length}</span>
          </button>
          {categories
            .filter((v) => events.some((event) => event.category === v.id))
            .map((v) => (
              <button
                key={v.id}
                className="wp-chip"
                data-active={category === v.id}
                aria-pressed={category === v.id}
                onClick={() => setCategory(v.id)}
              >
                {v.label}
              </button>
            ))}
        </div>
        <button
          className="wp-text-button"
          aria-expanded={showHelp}
          onClick={() => setShowHelp(!showHelp)}
        >
          <CircleHelp size={15} />
          Pulse란?
        </button>
      </div>
      {showHelp && (
        <div className="wp-explainer">
          <strong>평소보다 얼마나 많은 편집이 일어났을까요?</strong>
          <p>
            이슈 탐색의 Pulse는 평소 대비 편집량의 배수입니다. 사건의 중요도나
            주가 방향을 의미하지 않습니다. 펄스맵의 복합 급증 점수와는 다른
            지표입니다. {isExample && "이 화면의 값과 관계는 모두 예시입니다."}
          </p>
        </div>
      )}
      {!filtered.length ? (
        <EmptyState
          title="일치하는 사건이 없습니다"
          description="검색어를 짧게 입력하거나 다른 주제를 선택해 보세요."
          action={
            <button
              className="wp-button"
              onClick={() => {
                setCategory("all");
                setQuery("");
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
              모든 사건<span className="wp-count">{filtered.length}</span>
            </h2>
            <label className="sort-control">
              <ArrowDownUp size={14} />
              <select
                value={sort}
                onChange={(e) => setSort(e.target.value)}
                aria-label="사건 정렬"
              >
                <option value="pulse">Pulse 높은 순</option>
                <option value="recent">최근 시작 순</option>
                <option value="documents">문서 많은 순</option>
              </select>
            </label>
          </div>
          <div className="event-list" data-view={view}>
            {filtered.map((event) => (
              <EventRow
                key={event.id}
                category={getCategory(event.category)}
                event={event}
                saved={savedEvents.includes(event.id)}
                onToggle={onToggleEvent}
              />
            ))}
          </div>
        </section>
      )}
      <p className="explore-footnote">
        {isExample
          ? "화면의 모든 수치는 데모 데이터입니다."
          : "데이터의 출처와 기준 시각을 확인해 주세요."}
      </p>
    </div>
  );
}
