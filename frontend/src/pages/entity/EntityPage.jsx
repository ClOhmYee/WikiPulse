import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronRight,
  Clock3,
  ExternalLink,
  Eye,
  FileText,
  GitCompareArrows,
  Info,
  Users,
} from "lucide-react";
import { usePageData } from "../../data/hooks/PageData";
import { formatNumber } from "../../lib/format";
import { CategoryTag } from "../../components/ui/CategoryTag";
import { EmptyState } from "../../components/ui/EmptyState";
import { TrendChart } from "../../components/charts/TrendChart";
import "../../styles/details.css";

const formatDate = (value) =>
  value
    ? String(value).replace("T", " ").replace(/Z$/, "").slice(0, 16)
    : "날짜 미제공";
const ranges = [
  { id: "7", label: "7일" },
  { id: "14", label: "14일" },
  { id: "all", label: "전체" },
];

export default function EntityPage({ entityId }) {
  const { getEntity, getEvent, getCategory, isExample } = usePageData();
  const entity = getEntity(entityId);
  const [metric, setMetric] = useState("edits");
  const [range, setRange] = useState("all");
  const [showBaseline, setShowBaseline] = useState(true);
  const [selectedRevision, setSelectedRevision] = useState(null);
  const [revisionQuery, setRevisionQuery] = useState("");
  useEffect(() => {
    setSelectedRevision(null);
    setRevisionQuery("");
    setMetric("edits");
    setRange("all");
  }, [entityId]);
  if (!entity)
    return (
      <div className="wp-page">
        <EmptyState
          title="문서를 찾을 수 없어요"
          description="주소가 변경되었거나 아직 준비되지 않은 문서입니다. 사건 탐색에서 연결된 문서를 다시 찾아보세요."
          action={
            <a className="wp-button" data-variant="primary" href="#/explore">
              사건 탐색으로
            </a>
          }
        />
      </div>
    );
  const changes = entity.changes || [];
  const filteredChanges = changes.filter((change) =>
    `${change.section} ${change.summary}`
      .toLocaleLowerCase()
      .includes(revisionQuery.trim().toLocaleLowerCase()),
  );
  const revision =
    filteredChanges.find((change) => change.id === selectedRevision) ||
    filteredChanges[0];
  const chartData =
    range === "all"
      ? entity.chart || []
      : (entity.chart || []).slice(-Number(range));
  const relatedEntities = (entity.relatedIds || [])
    .map(getEntity)
    .filter(Boolean);
  const relatedEvents = (entity.eventIds || []).map(getEvent).filter(Boolean);
  const wikipediaUrl = `https://en.wikipedia.org/wiki/${encodeURIComponent(entity.title)}`;
  const historyUrl = `https://en.wikipedia.org/w/index.php?title=${encodeURIComponent(entity.title)}&action=history`;

  return (
    <div className="wp-page dt-page dt-entity-page">
      <a href="#/explore" className="dt-back">
        <ArrowLeft size={16} />
        사건 탐색
      </a>
      <header className="dt-event-header dt-entity-header">
        <div>
          <h1>{entity.name}</h1>
          <div className="dt-entity-original">
            <FileText size={16} />
            <span>{entity.title.replaceAll("_", " ")}</span>
            <CategoryTag category={getCategory(entity.category)} />
          </div>
          <p className="dt-lede">{entity.description}</p>
          <p className="dt-footnote">
            지표 기준일 {entity.chart?.at(-1)?.date || "미제공"} ·{" "}
            {isExample ? "데이터 예시" : "출처 확인 필요"}
          </p>
        </div>
        <a
          href={wikipediaUrl}
          target="_blank"
          rel="noreferrer"
          className="wp-button"
        >
          위키백과 원문 <ExternalLink size={16} />
          <span className="dt-sr-only"> (새 탭)</span>
        </a>
      </header>

      <div
        className="dt-event-metrics dt-entity-metrics"
        aria-label="문서 기준일 지표 예시"
      >
        <div>
          <span>
            <GitCompareArrows size={14} />
            기준일 편집량
          </span>
          <strong>
            {formatNumber(entity.edits)}
            <small>회</small>
          </strong>
        </div>
        <div>
          <span>평소 대비</span>
          <strong className="dt-teal">
            {entity.pulse}
            <small>배</small>
          </strong>
        </div>
        <div>
          <span>
            <Eye size={14} />
            기준일 조회수
          </span>
          <strong>
            {formatNumber(entity.pageviews)}
            <small>회</small>
          </strong>
        </div>
        <div>
          <span>
            <Users size={14} />
            참여 편집자
          </span>
          <strong>
            {formatNumber(entity.editors)}
            <small>명</small>
          </strong>
        </div>
      </div>

      <div className="dt-content-layout dt-entity-layout">
        <div className="dt-primary">
          <section className="dt-chart-section" aria-label="문서 활동 차트">
            <div className="dt-section-heading">
              <div>
                <h2>이 문서에 모인 관심</h2>
                <p>편집과 조회가 언제 늘었는지 비교해 보세요.</p>
              </div>
              <div
                className="dt-segment"
                role="group"
                aria-label="문서 차트 기간"
              >
                {ranges.map((item) => (
                  <button
                    type="button"
                    key={item.id}
                    aria-pressed={range === item.id}
                    onClick={() => setRange(item.id)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="dt-chart-frame">
              <div className="dt-chart-toolbar">
                <div
                  className="dt-chart-metric"
                  role="group"
                  aria-label="차트 지표"
                >
                  <button
                    type="button"
                    aria-pressed={metric === "edits"}
                    onClick={() => setMetric("edits")}
                  >
                    편집량
                  </button>
                  <button
                    type="button"
                    aria-pressed={metric === "pageviews"}
                    onClick={() => setMetric("pageviews")}
                  >
                    조회수
                  </button>
                </div>
                <span className="dt-mini-label">기간별 데이터 예시</span>
              </div>
              <div className="dt-chart-legend">
                <span>
                  <i />
                  {metric === "edits" ? "편집량" : "조회수"}
                </span>
                {metric === "edits" && (
                  <label>
                    <input
                      type="checkbox"
                      checked={showBaseline}
                      onChange={(event) =>
                        setShowBaseline(event.target.checked)
                      }
                    />
                    <i className="dt-baseline-swatch" />
                    평소 편집량
                  </label>
                )}
                <span className="dt-legend-note">단위: 회</span>
              </div>
              <TrendChart
                isExample={isExample}
                data={chartData}
                valueKey={metric}
                label={`${entity.name} ${metric === "edits" ? "편집량" : "조회수"} 추이 예시`}
                baseline={metric === "edits" && showBaseline}
                height={245}
              />
            </div>
            <p className="dt-footnote">
              <Info size={15} />
              편집량과 조회수는 관심의 변화를 보여 줍니다. 내용의 정확성이나
              사건의 영향을 나타내는 값은 아닙니다.
            </p>
          </section>

          <section className="dt-revision-section" aria-label="편집 내역 비교">
            <div className="dt-section-heading">
              <div>
                <h2>무엇이 바뀌었을까?</h2>
                <p>편집 내역을 선택하면 바뀌기 전과 후를 비교할 수 있어요.</p>
              </div>
              <span className="dt-mini-label">
                {isExample ? "편집 내역 예시" : "편집 내역"}
              </span>
            </div>
            <label className="dt-revision-search">
              <span>편집 내역 검색</span>
              <input
                type="search"
                value={revisionQuery}
                onChange={(event) => setRevisionQuery(event.target.value)}
                placeholder="섹션 또는 변경 내용"
              />
            </label>
            {filteredChanges.length ? (
              <div className="dt-revision-browser">
                <div
                  className="dt-revision-list"
                  role="group"
                  aria-label="편집 내역 선택"
                >
                  {filteredChanges.map((change) => (
                    <button
                      type="button"
                      key={change.id}
                      aria-pressed={revision?.id === change.id}
                      className="dt-revision-option"
                      onClick={() => setSelectedRevision(change.id)}
                    >
                      <span className="dt-revision-time">
                        <Clock3 size={13} />
                        <time>{formatDate(change.time)}</time>
                        {revision?.id === change.id && <Check size={14} />}
                      </span>
                      <strong>{change.summary}</strong>
                      <span className="dt-revision-option-meta">
                        {change.section}
                        <span
                          data-direction={change.delta >= 0 ? "add" : "remove"}
                        >
                          {change.delta >= 0 ? "+" : ""}
                          {change.delta}자
                        </span>
                      </span>
                    </button>
                  ))}
                </div>
                <div className="dt-revision-detail" aria-live="polite">
                  <div className="dt-revision-detail-heading">
                    <span>{revision.section}</span>
                    <h3>{revision.summary}</h3>
                    <p>
                      {isExample ? "예시 편집자" : "편집자"} {revision.editor} ·{" "}
                      {formatDate(revision.time)}
                    </p>
                  </div>
                  <div className="dt-diff-columns">
                    <div className="dt-diff dt-diff-before">
                      <h4>
                        <span aria-hidden="true">−</span>편집 전
                      </h4>
                      <p>
                        {revision.before || "이전 내용이 없는 새 섹션입니다."}
                      </p>
                    </div>
                    <div className="dt-diff dt-diff-after">
                      <h4>
                        <span aria-hidden="true">+</span>편집 후
                      </h4>
                      <p>
                        {revision.after || "이 편집에서 내용이 삭제되었습니다."}
                      </p>
                    </div>
                  </div>
                  <p className="dt-footnote">
                    {isExample
                      ? "비교 문장과 편집자 표시는 화면 예시입니다."
                      : "제공된 편집 정보의 출처를 확인해 주세요."}{" "}
                    실제 변경 이력은 위키백과에서 확인하세요.
                  </p>
                  <a
                    className="dt-text-link"
                    href={historyUrl}
                    target="_blank"
                    rel="noreferrer"
                  >
                    실제 문서 역사 보기 <ExternalLink size={14} />
                    <span className="dt-sr-only"> (새 탭)</span>
                  </a>
                </div>
              </div>
            ) : (
              <EmptyState
                title={
                  revisionQuery
                    ? "일치하는 편집 내역이 없어요"
                    : "아직 편집 내역 예시가 없어요"
                }
                description={
                  revisionQuery
                    ? "다른 검색어를 입력하거나 검색 조건을 초기화해 보세요."
                    : "위키백과 원문의 문서 역사에서 실제 내역을 확인할 수 있어요."
                }
                action={
                  revisionQuery ? (
                    <button
                      className="wp-button"
                      onClick={() => setRevisionQuery("")}
                    >
                      검색 초기화
                    </button>
                  ) : (
                    <a
                      className="wp-button"
                      href={historyUrl}
                      target="_blank"
                      rel="noreferrer"
                    >
                      실제 문서 역사 보기 <ExternalLink size={15} />
                    </a>
                  )
                }
              />
            )}
          </section>

          <section className="dt-related-events">
            <div className="dt-section-heading">
              <h2>이 문서가 연결된 이벤트</h2>
              <a className="dt-text-link" href="#/explore">
                이벤트 탐색 <ArrowRight size={16} />
              </a>
            </div>
            {relatedEvents.length ? (
              <div className="dt-event-links">
                {relatedEvents.map((event) => (
                  <a key={event.id} href={`#/events/${event.id}`}>
                    <div>
                      <div className="dt-meta">
                        <CategoryTag category={getCategory(event.category)} />
                        <time>{formatDate(event.date || event.startAt)}</time>
                      </div>
                      <h3>{event.title}</h3>
                      <p>{event.summary}</p>
                    </div>
                    <ArrowUpRight size={20} />
                  </a>
                ))}
              </div>
            ) : (
              <EmptyState
                title="연결된 이벤트가 없어요"
                description="새로운 편집 신호를 이벤트 탐색에서 살펴보세요."
              />
            )}
          </section>
        </div>

        <aside className="dt-sidebar" aria-label="문서 참고 정보">
          <section>
            <h2>함께 읽으면 좋은 문서</h2>
            <p className="dt-sidebar-intro">
              이 주제와 맞닿은 다른 문서에서 맥락을 넓혀 보세요.
            </p>
            {relatedEntities.length ? (
              <div className="dt-related-docs">
                {relatedEntities.map((article) => (
                  <a key={article.id} href={`#/intelligence/${article.id}`}>
                    <div>
                      <h3>{article.name}</h3>
                      <p>{article.description}</p>
                      <span>
                        편집 {formatNumber(article.edits)}회{" "}
                        <span className="dt-teal">
                          평소 대비 {article.pulse}배
                        </span>
                      </span>
                    </div>
                    <ChevronRight size={17} />
                  </a>
                ))}
              </div>
            ) : (
              <p className="wp-muted">연결된 문서 예시가 없습니다.</p>
            )}
          </section>
          <section className="dt-source-section">
            <h2>출처에서 더 살펴보기</h2>
            <a
              className="dt-source-link"
              href={wikipediaUrl}
              target="_blank"
              rel="noreferrer"
            >
              <FileText size={18} />
              <span>
                <strong>영문 위키백과</strong>
                <small>문서의 전체 맥락 읽기</small>
              </span>
              <ExternalLink size={16} />
              <span className="dt-sr-only"> (새 탭)</span>
            </a>
            <a
              className="dt-source-link"
              href={historyUrl}
              target="_blank"
              rel="noreferrer"
            >
              <GitCompareArrows size={18} />
              <span>
                <strong>문서 역사</strong>
                <small>실제 편집 내역 확인</small>
              </span>
              <ExternalLink size={16} />
              <span className="dt-sr-only"> (새 탭)</span>
            </a>
            <p className="dt-footnote">
              외부 링크는 현재의 위키백과로 이동합니다. 이 화면의 예시와 원문
              내용은 다를 수 있어요.
            </p>
          </section>
          <section className="dt-context-note">
            <h2>변화를 읽는 세 가지 질문</h2>
            <ul className="dt-question-list">
              <li>어느 부분이 달라졌나요?</li>
              <li>새로 추가된 출처가 있나요?</li>
              <li>다른 문서에서도 비슷한 변화가 보이나요?</li>
            </ul>
            <p>
              편집의 횟수에서 한 걸음 더 들어가, 바뀐 내용과 그 근거를 함께
              확인하세요.
            </p>
          </section>
        </aside>
      </div>
    </div>
  );
}
