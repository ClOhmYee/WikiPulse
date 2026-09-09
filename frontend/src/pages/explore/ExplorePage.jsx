import { EventRow, statusLabels } from "../../components/event/EventRow";
import { useMemo, useState } from "react";
import {
  ArrowDownUp,
  ArrowRight,
  Bookmark,
  Check,
  ChevronRight,
  CircleHelp,
  List,
  LayoutGrid,
  Search,
  X,
} from "lucide-react";
import { usePageData } from "../../data/hooks/PageData";
import { CategoryTag } from "../../components/ui/CategoryTag";
import { EmptyState } from "../../components/ui/EmptyState";
import { TrendChart } from "../../components/charts/TrendChart";
import PulseMap from "./PulseMap";
import { wikipediaUrl } from "../../lib/wiki";

export default function ExplorePage({
  listView = false,
  initialQuery = "",
  savedEvents,
  onToggleEvent,
}) {
  const { categories, events, getEntity, getCategory, meta, isExample } =
    usePageData();
  const [query, setQuery] = useState(initialQuery);
  const [category, setCategory] = useState("all");
  const [period, setPeriod] = useState("24h");
  const [sort, setSort] = useState("pulse");
  const [view, setView] = useState("list");
  const [selectedId, setSelectedId] = useState(events[0]?.id);
  const [showHelp, setShowHelp] = useState(false);
  const filtered = useMemo(
    () =>
      events
        .map((event) => {
          if (listView || period === "24h") return event;
          const points = event.chart.slice(-(period === "3d" ? 3 : 7));
          const edits = points.reduce((total, point) => total + point.edits, 0);
          const baseline = points.reduce(
            (total, point) => total + point.baseline,
            0,
          );
          return {
            ...event,
            edits,
            baseline,
            pageviews: points.reduce(
              (total, point) => total + point.pageviews,
              0,
            ),
            pulse: Math.round((edits / baseline) * 10) / 10,
          };
        })
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
    [category, query, sort, period, listView, events],
  );
  const selected =
    filtered.find((event) => event.id === selectedId) || filtered[0];
  const reset = () => {
    setCategory("all");
    setQuery("");
  };
  return (
    <div className="wp-page explore-page">
      <div className="wp-page-header">
        <div>
          <h1>{listView ? "사건을 탐색하세요" : "세상의 변화가 모이는 곳"}</h1>
          <p className="wp-subtitle">
            {listView
              ? "흩어진 문서의 움직임에서, 하나의 사건을 발견하세요."
              : "문서의 작은 변화에서 시작해, 사건의 맥락까지 따라가 보세요."}
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
              onClick={() => setQuery("")}
              aria-label="검색어 지우기"
            >
              <X size={15} />
            </button>
          )}
        </label>
        {listView && (
          <div className="wp-segment" aria-label="이슈 보기 방식">
            <button onClick={() => setView("card")} aria-pressed={view === "card"}>
              <LayoutGrid size={16} />카드
            </button>
            <button onClick={() => setView("list")} aria-pressed={view === "list"}>
              <List size={16} />리스트
            </button>
          </div>
        )}
        {!listView && (
          <div className="wp-segment" aria-label="차트 기간">
            {[
              ["24h", "24시간"],
              ["3d", "3일"],
              ["7d", "7일"],
            ].map(([value, label]) => (
              <button
                key={value}
                onClick={() => setPeriod(value)}
                aria-pressed={period === value}
              >
                {label}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="explore-filter-row">
        <div className="wp-filter-chips" aria-label="사건 주제">
          <button
            className="wp-chip"
            data-active={category === "all"}
            onClick={() => setCategory("all")}
          >
            전체 <span>{events.length}</span>
          </button>
          {categories
            .filter((item) =>
              events.some((event) => event.category === item.id),
            )
            .map((item) => (
              <button
                key={item.id}
                className="wp-chip"
                data-active={category === item.id}
                onClick={() => setCategory(item.id)}
              >
                {item.label}
              </button>
            ))}
        </div>
        <button
          className="wp-text-button"
          onClick={() => setShowHelp(!showHelp)}
          aria-expanded={showHelp}
        >
          <CircleHelp size={15} />
          Pulse란?
        </button>
      </div>
      {showHelp && (
        <div className="wp-explainer">
          <strong>평소보다 얼마나 많은 편집이 일어났을까요?</strong>
          <p>
            Pulse는 평소 편집량 대비 현재 편집량의 배수입니다. 값이 높을수록
            문서에 변화가 집중되었다는 뜻이며, 사건의 중요도나 주가 방향을
            의미하지 않습니다.{" "}
            {isExample
              ? "이 화면의 값과 관계는 모두 예시입니다."
              : "값과 관계는 제공된 데이터의 출처를 함께 확인해 주세요."}
          </p>
        </div>
      )}
      {filtered.length === 0 ? (
        <EmptyState
          title="일치하는 사건이 없습니다"
          description="검색어를 짧게 입력하거나 다른 주제를 선택해 보세요."
          action={
            <button className="wp-button" onClick={reset}>
              필터 초기화
            </button>
          }
        />
      ) : (
        <>
          {!listView && (
            <div className="explore-map-layout">
              <PulseMap
                isExample={isExample}
                categories={categories}
                events={filtered}
                selectedId={selected.id}
                onSelect={setSelectedId}
                period={period}
              />
              <aside className="signal-preview" aria-label="선택한 사건">
                <div className="signal-preview__top">
                  <CategoryTag category={getCategory(selected.category)} />
                  <button
                    className="wp-icon-button"
                    onClick={() => onToggleEvent(selected.id)}
                    aria-label={
                      savedEvents.includes(selected.id)
                        ? "선택한 사건 저장 해제"
                        : "선택한 사건 저장"
                    }
                    aria-pressed={savedEvents.includes(selected.id)}
                  >
                    <Bookmark
                      size={18}
                      fill={
                        savedEvents.includes(selected.id)
                          ? "currentColor"
                          : "none"
                      }
                    />
                  </button>
                </div>
                <span className="signal-preview__status">
                  <span />
                  {statusLabels[selected.status]}
                </span>
                <h2>{selected.title}</h2>
                <p>{selected.summary}</p>
                <div className="signal-preview__numbers">
                  <div>
                    <strong>
                      {selected.pulse.toFixed(1)}
                      <small>×</small>
                    </strong>
                    <span>평소 대비 편집량</span>
                  </div>
                  <div>
                    <strong>
                      {selected.articleIds.length}
                      <small>개</small>
                    </strong>
                    <span>연결된 문서</span>
                  </div>
                </div>
                <TrendChart
                  isExample={isExample}
                  data={selected.chart.slice(
                    -(period === "24h" ? 2 : period === "3d" ? 4 : 8),
                  )}
                  label="편집 추이"
                  height={115}
                />
                <div className="signal-preview__documents">
                  {selected.articleIds
                    .slice(0, 3)
                    .map((id) => getEntity(id))
                    .filter(Boolean)
                    .map((article) => (
                      <a
                        href={wikipediaUrl(article)}
                        key={article.id}
                        target="_blank"
                        rel="noreferrer"
                        aria-label={`${article.title} 위키백과 원문 (새 탭)`}
                      >
                        {article.title}
                        <ChevronRight size={12} />
                      </a>
                    ))}
                </div>
                <a
                  className="wp-button"
                  data-variant="primary"
                  href={`#/issues/${selected.id}`}
                >
                  사건 자세히 보기
                  <ArrowRight size={16} />
                </a>
              </aside>
            </div>
          )}
          <section className="event-list-section">
            <div className="wp-section-heading">
              <div>
                <h2>
                  {listView ? "모든 사건" : "포착된 사건"}
                  <span className="wp-count">{filtered.length}</span>
                </h2>
                {!listView && <p>지도의 신호를 목록으로 살펴보세요.</p>}
              </div>
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
            <div className="event-list" data-view={listView ? view : "list"}>
              {filtered.map((event) => (
                <EventRow
                  category={getCategory(event.category)}
                  key={event.id}
                  event={event}
                  saved={savedEvents.includes(event.id)}
                  onToggle={onToggleEvent}
                />
              ))}
            </div>
          </section>
        </>
      )}
      <div className="explore-footnote">
        <Check size={14} />
        <span>
          Wikipedia 문서의 변화를 중심으로 사건을 탐색합니다.{" "}
          {isExample
            ? "화면의 모든 수치는 데모 데이터입니다."
            : "데이터의 출처와 기준 시각을 확인해 주세요."}
        </span>
      </div>
    </div>
  );
}
