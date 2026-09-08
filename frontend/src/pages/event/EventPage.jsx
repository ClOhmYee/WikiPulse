import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Bookmark,
  Check,
  ChevronRight,
  FileText,
  GitCompareArrows,
  Layers3,
  MessageCircle,
  Newspaper,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import { usePageData } from "../../data/hooks/PageData";
import { formatNumber } from "../../lib/format";
import { ArticleNetwork } from "../../components/entity/ArticleNetwork";
import { CategoryTag } from "../../components/ui/CategoryTag";
import { EmptyState } from "../../components/ui/EmptyState";
import { TrendChart } from "../../components/charts/TrendChart";
import { Timeline, EventNews, Evidence } from "./EventSections";
import EventDiscussion from "./EventDiscussion";
import "../../styles/details.css";
const tabs = [
  { id: "overview", label: "이벤트 개요" },
  { id: "timeline", label: "타임라인" },
  { id: "news", label: "관련 소식" },
  { id: "evidence", label: "근거 문서" },
  { id: "discussion", label: "토론" },
];
const formatDate = (value) =>
  value
    ? String(value).replace("T", " ").replace(/Z$/, "").slice(0, 16)
    : "날짜 미제공";

export default function EventPage({
  eventId,
  savedEvents = [],
  onToggleEvent,
}) {
  const { getEvent, getEntity, getStock, getCategory, isExample } =
    usePageData();
  const [tab, setTab] = useState("overview");
  const [range, setRange] = useState("all");
  const [showBaseline, setShowBaseline] = useState(true);
  const [selectedArticle, setSelectedArticle] = useState(null);
  const event = getEvent(eventId);
  useEffect(() => {
    setTab("overview");
    setRange("all");
    setSelectedArticle(null);
  }, [eventId]);
  const articles = useMemo(
    () => (event?.articleIds || []).map(getEntity).filter(Boolean),
    [event, getEntity],
  );
  const relatedStocks = useMemo(
    () => (event?.stockSymbols || []).map(getStock).filter(Boolean),
    [event, getStock],
  );
  if (!event)
    return (
      <div className="wp-page">
        <EmptyState
          title="이벤트를 찾을 수 없어요"
          description="주소를 확인하거나 이벤트 탐색에서 다른 신호를 살펴보세요."
          action={
            <a className="wp-button" data-variant="primary" href="#/explore">
              이벤트 탐색으로
            </a>
          }
        />
      </div>
    );
  const selected =
    articles.find((article) => article.id === selectedArticle) || articles[0];
  const isSaved =
    typeof savedEvents.has === "function"
      ? savedEvents.has(event.id)
      : savedEvents.includes(event.id);
  const chartData =
    range === "7" ? (event.chart || []).slice(-7) : event.chart || [];
  const timeline = event.timeline || [];

  function selectTab(nextTab) {
    setTab(nextTab);
    document.getElementById(`event-tab-${nextTab}`)?.focus();
  }

  function handleTabKey(eventKey, index) {
    const direction =
      eventKey.key === "ArrowRight" ? 1 : eventKey.key === "ArrowLeft" ? -1 : 0;
    if (!direction && eventKey.key !== "Home" && eventKey.key !== "End") return;
    eventKey.preventDefault();
    const nextIndex =
      eventKey.key === "Home"
        ? 0
        : eventKey.key === "End"
          ? tabs.length - 1
          : (index + direction + tabs.length) % tabs.length;
    setTab(tabs[nextIndex].id);
    document.getElementById(`event-tab-${tabs[nextIndex].id}`)?.focus();
  }

  return (
    <div className="wp-page dt-page">
      <a href="#/explore" className="dt-back">
        <ArrowLeft size={16} />
        이벤트 탐색
      </a>
      <header className="dt-event-header">
        <div>
          <h1>{event.title}</h1>
          <p className="dt-lede">{event.summary}</p>
          <div className="dt-meta">
            <CategoryTag category={getCategory(event.category)} />
            <time>{formatDate(event.date || event.startAt)} 기준</time>
            <span>
              {isExample
                ? "이벤트 데이터 예시"
                : "이벤트 데이터 · 출처 확인 필요"}
            </span>
          </div>
        </div>
        <button
          type="button"
          className="wp-button dt-save-button"
          data-variant={isSaved ? "primary" : "ghost"}
          aria-pressed={isSaved}
          onClick={() => onToggleEvent?.(event.id)}
        >
          {isSaved ? <Check size={17} /> : <Bookmark size={17} />}
          {isSaved ? "저장됨" : "이벤트 저장"}
        </button>
      </header>

      <div
        className="dt-report-actions"
        role="group"
        aria-label="리포트 관련 탐색"
      >
        <a className="wp-button" href={`#/events/${event.id}/stocks`}>
          <Layers3 size={16} />
          연관 주식 {relatedStocks.length}
          <ArrowRight size={14} />
        </a>
        <button
          type="button"
          className="wp-button"
          onClick={() => selectTab("discussion")}
        >
          <MessageCircle size={16} />
          토론 참여하기
        </button>
      </div>

      <div className="dt-event-metrics" aria-label="이벤트 신호 예시">
        <div>
          <span>기준일 편집량</span>
          <strong>
            {formatNumber(event.edits)}
            <small>회</small>
          </strong>
        </div>
        <div>
          <span>평소 대비</span>
          <strong className="dt-teal">
            {event.pulse}
            <small>배</small>
            <TrendingUp size={20} />
          </strong>
        </div>
        <div>
          <span>함께 움직인 문서</span>
          <strong>
            {articles.length}
            <small>개</small>
          </strong>
        </div>
        <div>
          <span>문서별 편집자 합계</span>
          <strong>
            {formatNumber(event.editors)}
            <small>명</small>
          </strong>
        </div>
      </div>

      <nav className="dt-tabs" role="tablist" aria-label="이벤트 상세 보기">
        {tabs.map((item, index) => (
          <button
            type="button"
            key={item.id}
            id={`event-tab-${item.id}`}
            role="tab"
            aria-selected={tab === item.id}
            aria-controls="event-detail-panel"
            tabIndex={tab === item.id ? 0 : -1}
            onKeyDown={(keyEvent) => handleTabKey(keyEvent, index)}
            onClick={() => setTab(item.id)}
          >
            {item.label}
            {item.id === "evidence" && <span>{articles.length}</span>}
          </button>
        ))}
      </nav>

      <div className="dt-content-layout">
        <div
          className="dt-primary"
          id="event-detail-panel"
          role="tabpanel"
          aria-labelledby={`event-tab-${tab}`}
          tabIndex={0}
        >
          {tab === "overview" && (
            <>
              <section className="dt-chart-section">
                <div className="dt-section-heading">
                  <div>
                    <h2>편집 신호의 흐름</h2>
                    <p>함께 바뀐 문서들의 편집량을 시간순으로 살펴보세요.</p>
                  </div>
                  <div
                    className="dt-segment"
                    role="group"
                    aria-label="편집 차트 기간"
                  >
                    <button
                      type="button"
                      aria-pressed={range === "7"}
                      onClick={() => setRange("7")}
                    >
                      7일
                    </button>
                    <button
                      type="button"
                      aria-pressed={range === "all"}
                      onClick={() => setRange("all")}
                    >
                      전체
                    </button>
                  </div>
                </div>
                <div className="dt-chart-frame">
                  <div className="dt-chart-legend">
                    <span>
                      <i />
                      편집량
                    </span>
                    <label>
                      <input
                        type="checkbox"
                        checked={showBaseline}
                        onChange={(e) => setShowBaseline(e.target.checked)}
                      />
                      <i className="dt-baseline-swatch" />
                      평소 편집량
                    </label>
                    <span className="dt-legend-note">
                      {isExample ? "단위: 회 · 예시" : "단위: 회"}
                    </span>
                  </div>
                  <TrendChart
                    isExample={isExample}
                    data={chartData}
                    label={
                      isExample
                        ? "이벤트 편집량 추이 예시"
                        : "이벤트 편집량 추이"
                    }
                    baseline={showBaseline}
                    height={240}
                  />
                </div>
              </section>
              <section className="dt-network-section">
                <div className="dt-section-heading">
                  <div>
                    <h2>하나의 변화, 연결된 문서</h2>
                    <p>문서를 선택해 이 이벤트와 어떤 관계인지 살펴보세요.</p>
                  </div>
                  <span className="dt-mini-label">연결 관계 예시</span>
                </div>
                <div className="dt-network-layout">
                  <ArticleNetwork
                    articles={articles}
                    selectedId={selected?.id}
                    onSelect={setSelectedArticle}
                  />
                  {selected && (
                    <div className="dt-network-detail">
                      <CategoryTag category={getCategory(selected.category)} />
                      <h3>{selected.name}</h3>
                      <p>{selected.description}</p>
                      <div className="dt-inline-stat">
                        <span>편집량</span>
                        <strong>{formatNumber(selected.edits)}회</strong>
                        <span className="dt-teal">{selected.pulse}배</span>
                      </div>
                      <a
                        className="dt-text-link"
                        href={`#/intelligence/${selected.id}`}
                      >
                        문서 변화 분석 <ArrowRight size={16} />
                      </a>
                    </div>
                  )}
                </div>
              </section>
              <section className="dt-interpretation">
                <div className="dt-section-heading">
                  <h2>
                    <Sparkles size={20} />
                    {isExample
                      ? "AI 해석 예시"
                      : "제공된 해석 · 출처 확인 필요"}
                  </h2>
                  <span className="dt-mini-label">검증 전 해석</span>
                </div>
                <p className="dt-interpretation-note">
                  편집 신호를 읽는 하나의 관점입니다. 사실 확인은 근거 문서와
                  출처에서 이어가세요.
                </p>
                <div>
                  {(event.insights || []).map((insight, index) => (
                    <article key={`${insight.title}-${index}`}>
                      <h3>{insight.title}</h3>
                      <p>{insight.body}</p>
                    </article>
                  ))}
                </div>
                <button
                  type="button"
                  className="dt-text-link"
                  onClick={() => selectTab("evidence")}
                >
                  해석의 근거 문서 보기 <ArrowRight size={16} />
                </button>
              </section>
              <section className="dt-timeline-preview">
                <div className="dt-section-heading">
                  <h2>이벤트의 주요 순간</h2>
                  <button
                    type="button"
                    className="dt-text-link"
                    onClick={() => selectTab("timeline")}
                  >
                    타임라인 전체 <ArrowRight size={16} />
                  </button>
                </div>
                <Timeline entries={timeline.slice(0, 3)} compact />
              </section>
              <EventDiscussion key={event.id} event={event} />
            </>
          )}
          {tab === "timeline" && (
            <section>
              <div className="dt-section-intro">
                <h2>변화가 이어진 순서</h2>
                <p>
                  최근 기록부터 편집 신호와 소식을 살펴보세요.{" "}
                  {isExample
                    ? "모든 시점과 설명은 데모 예시입니다."
                    : "각 기록의 기준 시각과 출처를 확인해 주세요."}
                </p>
              </div>
              <Timeline entries={timeline} />
            </section>
          )}
          {tab === "news" && (
            <EventNews isExample={isExample} items={event.news || []} />
          )}
          {tab === "evidence" && (
            <Evidence isExample={isExample} articles={articles} />
          )}
          {tab === "discussion" && (
            <EventDiscussion key={event.id} event={event} />
          )}
        </div>

        <aside className="dt-sidebar" aria-label="이벤트 참고 정보">
          <section>
            <h2>이 이벤트에서 확인할 것</h2>
            <p className="dt-sidebar-intro">
              신호에서 맥락으로, 맥락에서 근거로 이어가세요.
            </p>
            <div className="dt-reading-links">
              <button type="button" onClick={() => selectTab("evidence")}>
                <FileText size={17} />
                <span>
                  <strong>{articles.length}개의 근거 문서</strong>
                  <small>편집 내용을 살펴보는 출발점</small>
                </span>
                <ChevronRight size={17} />
              </button>
              <button type="button" onClick={() => selectTab("news")}>
                <Newspaper size={17} />
                <span>
                  <strong>{(event.news || []).length}개의 관련 소식</strong>
                  <small>문서 밖의 맥락 함께 읽기</small>
                </span>
                <ChevronRight size={17} />
              </button>
              <button type="button" onClick={() => selectTab("timeline")}>
                <GitCompareArrows size={17} />
                <span>
                  <strong>시간순으로 비교</strong>
                  <small>어떤 변화가 먼저였는지</small>
                </span>
                <ChevronRight size={17} />
              </button>
            </div>
          </section>
          <section className="dt-stock-preview">
            <div className="dt-section-heading">
              <h2>연관 주식</h2>
              <ArrowUpRight size={18} />
            </div>
            <p className="dt-sidebar-intro">
              {isExample
                ? "이벤트와 사업 영역이 연결된 종목 예시입니다."
                : "이벤트와 사업 영역이 연결된 종목 데이터입니다."}
            </p>
            {relatedStocks.length ? (
              <div className="dt-stock-links">
                {relatedStocks.slice(0, 3).map((stock) => (
                  <a key={stock.symbol} href={`#/stocks/${stock.symbol}`}>
                    <span className="dt-stock-symbol">{stock.symbol}</span>
                    <span>
                      <strong>{stock.name}</strong>
                      <small>{stock.sector}</small>
                    </span>
                    <ChevronRight size={16} />
                  </a>
                ))}
              </div>
            ) : (
              <p className="wp-muted">
                {isExample
                  ? "연결된 종목 예시가 없습니다."
                  : "연결된 종목이 없습니다."}
              </p>
            )}
            <a
              className="wp-button dt-full-width"
              href={`#/events/${event.id}/stocks`}
            >
              종목 연결 근거 보기 <ArrowRight size={16} />
            </a>
            <p className="dt-footnote">
              연결은 탐색을 위한 가설이며, 수익률 예측이나 투자 권유가 아닙니다.
            </p>
          </section>
          <section className="dt-context-note">
            <h2>신호를 읽는 방법</h2>
            <p>
              편집이 늘었다는 것은 사람들이 이 주제를 다시 기록하고 있다는
              뜻입니다. 그 이유와 의미는 문서의 변화, 출처, 서로 다른 관점을
              함께 보며 판단하세요.
            </p>
            <div className="dt-keywords">
              {(event.keywords || []).map((keyword) => (
                <a
                  key={keyword}
                  href={`#/explore?q=${encodeURIComponent(keyword)}`}
                >
                  #{keyword}
                </a>
              ))}
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}
