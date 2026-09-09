import { useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronRight,
  GitBranch,
} from "lucide-react";
import { usePageData } from "../../data/hooks/PageData";
import { formatNumber } from "../../lib/format";
import { TrendChart } from "../../components/charts/TrendChart";
import { EmptyState } from "../../components/ui/EmptyState";
import { CategoryTag } from "../../components/ui/CategoryTag";
import {
  RELATION_LABELS,
  priceLabel,
  dateLabel,
  StockMark,
  SaveButton,
  PriceChange,
  RelationPath,
} from "./StockElements";
export default function StockDetail({ symbol, savedStocks, onToggleStock }) {
  const { events, getStock, getCategory, isExample } = usePageData();
  const stock = getStock(symbol);
  const [relationFilter, setRelationFilter] = useState("all");
  const [chartRange, setChartRange] = useState("all");

  if (!stock)
    return (
      <div className="wp-page">
        <a href="#/stocks" className="st-back">
          <ArrowLeft size={16} aria-hidden="true" /> 종목 탐색
        </a>
        <EmptyState
          title="종목을 찾지 못했습니다."
          description="등록된 예시 종목을 검색해 주세요."
          action={
            <a href="#/stocks" className="wp-button" data-variant="primary">
              종목 탐색으로 돌아가기
            </a>
          }
        />
      </div>
    );

  const relatedEvents = events
    .filter((event) => stock.eventIds.includes(event.id))
    .sort((a, b) => String(b.date).localeCompare(String(a.date)));
  const relationTypes = [
    ...new Set((stock.relations || []).map((relation) => relation.type)),
  ];
  const filteredEvents = relatedEvents.filter(
    (event) =>
      relationFilter === "all" ||
      stock.relations?.some(
        (relation) =>
          relation.eventId === event.id && relation.type === relationFilter,
      ),
  );
  const chartData =
    chartRange === "all"
      ? stock.chart || []
      : (stock.chart || []).slice(-Number(chartRange));

  return (
    <div className="wp-page st-page st-detail-page">
      <a href="#/stocks" className="st-back">
        <ArrowLeft size={16} aria-hidden="true" /> 종목 탐색
      </a>
      <header className="wp-page-header st-detail-header">
        <div className="st-detail-identity">
          <StockMark stock={stock} large />
          <div>
            <h1>{stock.name}</h1>
            <p className="st-detail-meta">
              <strong>{stock.symbol}</strong>
              <span>{stock.market}</span>
              <span>{stock.sector}</span>
            </p>
          </div>
        </div>
        <SaveButton
          stock={stock}
          savedStocks={savedStocks}
          onToggleStock={onToggleStock}
          full
        />
      </header>
      <p className="st-stock-description">{stock.description}</p>

      <div className="st-detail-layout">
        <section
          className="st-event-section"
          aria-labelledby="stock-events-title"
        >
          <div className="wp-section-heading st-events-heading">
            <div>
              <h2 id="stock-events-title">
                이 기업과 연결된 사건 <span>{relatedEvents.length}</span>
              </h2>
              <p>사건을 열어 문서 변화와 연결 근거를 함께 확인하세요.</p>
            </div>
          </div>
          <div
            className="st-relation-filters"
            role="group"
            aria-label="사건 연결 유형"
          >
            <button
              className="wp-chip"
              type="button"
              data-active={relationFilter === "all"}
              aria-pressed={relationFilter === "all"}
              onClick={() => setRelationFilter("all")}
            >
              전체
            </button>
            {relationTypes.map((type) => (
              <button
                className="wp-chip"
                type="button"
                key={type}
                data-active={relationFilter === type}
                aria-pressed={relationFilter === type}
                onClick={() => setRelationFilter(type)}
              >
                {RELATION_LABELS[type] || type}
              </button>
            ))}
          </div>

          <div className="st-event-timeline" aria-live="polite">
            {filteredEvents.length ? (
              filteredEvents.map((event) => {
                const relation = stock.relations?.find(
                  (item) => item.eventId === event.id,
                );
                return (
                  <article className="st-timeline-event" key={event.id}>
                    <div className="st-timeline-date">
                      <span className="st-timeline-dot" aria-hidden="true" />
                      <time dateTime={event.date}>{dateLabel(event.date)}</time>
                      <CategoryTag category={getCategory(event.category)} />
                    </div>
                    <div className="st-event-body">
                      <a
                        href={`#/issues/${event.id}`}
                        className="st-event-title"
                      >
                        <h3>{event.title}</h3>
                        <ArrowRight size={18} aria-hidden="true" />
                      </a>
                      <p className="st-event-summary">{event.summary}</p>
                      <div className="st-event-metrics">
                        <span>문서 {event.articleIds?.length || 0}개</span>
                        <span>편집 {formatNumber(event.edits)}회</span>
                        <span>
                          평소 대비 <strong>{event.pulse}배</strong>
                        </span>
                      </div>
                      {relation && (
                        <div className="st-relationship">
                          <div className="st-relationship-heading">
                            <span>
                              <GitBranch size={15} aria-hidden="true" />
                              {RELATION_LABELS[relation.type] || relation.type}
                            </span>
                            <span className="st-strength">
                              연결 근거{" "}
                              {relation.strength === "high" ? "높음" : "보통"} ·
                              예시
                            </span>
                          </div>
                          <RelationPath path={relation.path} />
                          <p>{relation.explanation}</p>
                        </div>
                      )}
                      <a
                        href={`#/issues/${event.id}`}
                        className="st-read-event"
                      >
                        사건과 근거 살펴보기
                        <ChevronRight size={15} aria-hidden="true" />
                      </a>
                    </div>
                  </article>
                );
              })
            ) : (
              <EmptyState
                title="이 유형으로 연결된 사건이 없습니다."
                description="다른 연결 유형을 선택해 보세요."
                action={
                  <button
                    type="button"
                    className="wp-button"
                    onClick={() => setRelationFilter("all")}
                  >
                    전체 사건 보기
                  </button>
                }
              />
            )}
          </div>
        </section>

        <aside className="st-stock-aside" aria-label="종목 참고 정보">
          <section className="wp-panel st-price-panel">
            <div className="st-price-title">
              <h2>가격 흐름</h2>
              <span className="wp-tag">{isExample ? "예시 가격" : "가격"}</span>
            </div>
            <div className="st-detail-price">
              <strong>{priceLabel(stock)}</strong>
              <PriceChange value={stock.change} />
            </div>
            <div
              className="st-chart-ranges"
              role="group"
              aria-label="예시 가격 차트 기간"
            >
              {[
                ["7", "7일"],
                ["14", "14일"],
                ["all", "전체"],
              ].map(([range, label]) => (
                <button
                  type="button"
                  key={range}
                  aria-pressed={chartRange === range}
                  data-active={chartRange === range}
                  onClick={() => setChartRange(range)}
                >
                  {label}
                </button>
              ))}
            </div>
            {chartData.length ? (
              <TrendChart
                isExample={isExample}
                data={chartData}
                valueKey="price"
                label={`${stock.symbol} ${isExample ? "예시 가격" : "가격"}`}
                color="#dbb057"
                height={160}
              />
            ) : (
              <p className="st-no-chart">
                {isExample
                  ? "이 종목의 예시 가격 추이가 없습니다."
                  : "이 종목의 가격 추이가 없습니다."}
              </p>
            )}
            <p className="st-chart-note">
              {isExample
                ? "사건 연결과 별도로 표시한 예시 가격입니다."
                : "사건 연결과 별도로 표시한 가격입니다. 기준 시각을 확인해 주세요."}
            </p>
          </section>
          <section className="st-how-to-read">
            <h2>연결은 이렇게 읽어요.</h2>
            <p>
              기업이 직접 등장하지 않아도 같은 산업, 공급망, 지역을 통해 사건과
              연결될 수 있습니다.
            </p>
            <ul>
              <li>
                <Check size={15} aria-hidden="true" />
                <span>경로를 따라 기업과 사건의 접점을 확인하세요.</span>
              </li>
              <li>
                <Check size={15} aria-hidden="true" />
                <span>사건 상세에서 문서와 뉴스의 근거를 더 살펴보세요.</span>
              </li>
            </ul>
          </section>
          <a href="#/stocks" className="st-discover-more">
            <span>
              다른 종목도 살펴보세요.<small>기업에서 시작하는 사건 탐색</small>
            </span>
            <ArrowRight size={18} aria-hidden="true" />
          </a>
        </aside>
      </div>
    </div>
  );
}
