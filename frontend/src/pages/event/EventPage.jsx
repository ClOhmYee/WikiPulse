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
} from "lucide-react";
import { usePageData } from "../../data/hooks/PageData";
import {
  metricLabel,
  completenessDescription,
  timestampLabel as formatDate,
} from "./presentation.js";
import { IssueState } from "../../components/event/IssueState";
import { ArticleNetwork } from "../../components/entity/ArticleNetwork";
import { CategoryTag } from "../../components/ui/CategoryTag";
import { EmptyState } from "../../components/ui/EmptyState";
import { TrendChart } from "../../components/charts/TrendChart";
import { Timeline, EventNews, Evidence } from "./EventSections";
import EventDiscussion from "./EventDiscussion";
import { IssueReport } from "../../components/event/IssueReport";
import HistoryReportCalendar from "./HistoryReportCalendar.jsx";
import { issueHistoryEnabled } from "../../data/historyProduction.js";
import { dataClient } from "../../data/index.js";
import { wikipediaUrl } from "../../lib/wiki";
import "../../styles/details.css";
const exampleTabs = [
  { id: "report", label: "리포트" },
  { id: "overview", label: "탐색" },
  { id: "timeline", label: "타임라인" },
  { id: "news", label: "관련 소식" },
  { id: "evidence", label: "근거 문서" },
  { id: "discussion", label: "토론" },
];
const apiTabs = [
  { id: "report", label: "리포트" },
  { id: "overview", label: "탐색" },
  { id: "evidence", label: "근거 문서" },
];

export default function EventPage({
  eventId,
  savedEvents = [],
  onToggleEvent,
}) {
  const { getEvent, getEntity, getStock, getCategory, isExample } =
    usePageData();
  const [tab, setTab] = useState("report");
  const [range, setRange] = useState("all");
  const [showBaseline, setShowBaseline] = useState(true);
  const [selectedArticle, setSelectedArticle] = useState(null);
  const event = getEvent(eventId);
  useEffect(() => {
    setTab("report");
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
            <a className="wp-button" data-variant="primary" href="#/issues">
              이벤트 탐색으로
            </a>
          }
        />
      </div>
    );
  const selected =
    articles.find((article) => article.id === selectedArticle) || articles[0];
  const savedKey = [event.id, ...(event.aliases || [])].find((id) =>
    typeof savedEvents.has === "function"
      ? savedEvents.has(id)
      : savedEvents.includes(id),
  );
  const isSaved = Boolean(savedKey);
  const chartData =
    range === "7" ? (event.chart || []).slice(-7) : event.chart || [];
  const timeline = event.timeline || [];
  const tabs = isExample ? exampleTabs : apiTabs;
  const historyMode = issueHistoryEnabled(
    import.meta.env,
    dataClient.dataSource,
  );
  const backQuery = new URLSearchParams(
    window.location.hash.split("?")[1] || "",
  ).get("q");

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
      <a
        href={`#/issues${backQuery ? `?q=${encodeURIComponent(backQuery)}` : ""}`}
        className="dt-back"
      >
        <ArrowLeft size={16} />
        이벤트 탐색
      </a>
      <header className="dt-event-header">
        <div>
          <h1>{event.title}</h1>
          <div className="dt-meta">
            {event.category && (
              <CategoryTag category={getCategory(event.category)} />
            )}
            <time dateTime={event.snapshotTs || undefined}>
              {formatDate(event.snapshotTs)} 기준
            </time>
            <IssueState status={event.status} />
          </div>
        </div>
        <button
          type="button"
          className="wp-button dt-save-button"
          data-variant={isSaved ? "primary" : "ghost"}
          aria-pressed={isSaved}
          onClick={() => onToggleEvent?.(savedKey || event.id)}
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
        <a className="wp-button" href={`#/issues/${event.id}/stocks`}>
          <Layers3 size={16} />
          연관 주식
          <ArrowRight size={14} />
        </a>
        {isExample && (
          <button
            type="button"
            className="wp-button"
            onClick={() => selectTab("discussion")}
          >
            <MessageCircle size={16} />
            토론 참여하기
          </button>
        )}
      </div>

      <div className="dt-event-metrics" aria-label="이슈 데이터 요약">
        <div>
          <span>이슈 편집량</span>
          <strong>
            {metricLabel(event.edits)}
            {event.edits != null && <small>회</small>}
          </strong>
        </div>
        <div>
          <span>급증 점수</span>
          <strong className="dt-teal">{metricLabel(event.pulseScore)}</strong>
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
            {metricLabel(event.editors)}
            {event.editors != null && <small>명</small>}
          </strong>
        </div>
      </div>

      {historyMode && <HistoryReportCalendar key={event.id} event={event} />}

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
                    <p>
                      편집·조회수의 관측 자료와 이슈 점수는 서로 다른
                      정보입니다.
                    </p>
                  </div>
                  <div
                    className="dt-segment"
                    role="group"
                    aria-label="편집 차트 기간"
                  >
                    <button
                      type="button"
                      disabled={!chartData.length}
                      aria-pressed={range === "7"}
                      onClick={() => setRange("7")}
                    >
                      7일
                    </button>
                    <button
                      type="button"
                      disabled={!chartData.length}
                      aria-pressed={range === "all"}
                      onClick={() => setRange("all")}
                    >
                      전체
                    </button>
                  </div>
                </div>
                {chartData.length ? (
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
                ) : (
                  <div className="data-availability">
                    <strong>시계열 미제공</strong>
                    <p>
                      이 시점의 편집·조회수 추이와 기준선 자료가 제공되지
                      않았습니다.
                    </p>
                  </div>
                )}
              </section>
              <section className="dt-network-section">
                <div className="dt-section-heading">
                  <div>
                    <h2>하나의 변화, 연결된 문서</h2>
                    <p>문서를 선택해 이 이벤트와 어떤 관계인지 살펴보세요.</p>
                  </div>
                  <span className="dt-mini-label">클러스터 구성</span>
                </div>
                <div className="dt-network-layout">
                  <ArticleNetwork
                    articles={articles}
                    selectedId={selected?.id}
                    onSelect={setSelectedArticle}
                  />
                  {selected && (
                    <div className="dt-network-detail">
                      {selected.category && (
                        <CategoryTag
                          category={getCategory(selected.category)}
                        />
                      )}
                      <h3>{selected.name}</h3>
                      <p>
                        {selected.isSeed
                          ? "급증 신호로 포함된 문서"
                          : "연관 문서"}
                      </p>
                      <div className="dt-inline-stat">
                        <span>편집량</span>
                        <strong>
                          {metricLabel(selected.edits)}
                          {selected.edits != null ? "회" : ""}
                        </strong>
                        <span>조회수</span>
                        <strong>
                          {metricLabel(selected.views ?? selected.pageviews)}
                          {(selected.views ?? selected.pageviews) != null
                            ? "회"
                            : ""}
                        </strong>
                      </div>
                      <p className="wp-small">
                        {completenessDescription(selected.completeness)}
                      </p>
                      <a
                        className="dt-text-link"
                        href={wikipediaUrl(selected)}
                        target="_blank"
                        rel="noreferrer"
                      >
                        위키백과 원문 보기 <ArrowUpRight size={16} />
                        <span className="dt-sr-only"> (새 탭)</span>
                      </a>
                    </div>
                  )}
                </div>
              </section>
              {isExample && (
                <>
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
                    <Timeline
                      entries={timeline.slice(0, 3)}
                      articles={articles}
                      compact
                    />
                  </section>
                  <EventDiscussion key={event.id} event={event} />
                </>
              )}
            </>
          )}
          {tab === "report" && (
            <IssueReport
              report={event.report}
              summary={event.summary}
              articles={articles}
              stocks={relatedStocks}
              isExample={isExample}
            />
          )}
          {tab === "timeline" && (
            <section>
              <div className="dt-section-intro">
                <h2>변화가 이어진 순서</h2>
                <p>
                  최근 기록부터 편집 신호와 소식을 살펴보세요. 각 기록의 기준
                  시각과 출처를 확인해 주세요.
                </p>
              </div>
              <Timeline entries={timeline} articles={articles} />
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
              {isExample && (
                <>
                  <button type="button" onClick={() => selectTab("news")}>
                    <Newspaper size={17} />
                    <span>
                      <strong>
                        {event.news?.length
                          ? `${event.news.length}개의 관련 소식`
                          : "관련 소식 미제공"}
                      </strong>
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
                </>
              )}
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
                : "검증을 통과해 이 이벤트와 연결된 종목입니다."}
            </p>
            {relatedStocks.length ? (
              <div className="dt-stock-links">
                {relatedStocks.slice(0, 5).map((stock) => (
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
                  ? "제공된 관련 종목 예시가 없습니다."
                  : "제공된 관련 종목이 없습니다."}
              </p>
            )}
            <a
              className="wp-button dt-full-width"
              href={`#/issues/${event.id}/stocks`}
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
              이슈는 사람 편집이 발생한 뒤 조회수가 급증한 문서에서 포착됩니다.
              급증 점수는 편집 배수나 사실의 정확도를 뜻하지 않습니다.
            </p>
            <div className="dt-keywords">
              {(event.keywords || []).map((keyword) => (
                <a
                  key={keyword}
                  href={`#/issues?q=${encodeURIComponent(keyword)}`}
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
