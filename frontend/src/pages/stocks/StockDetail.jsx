import { ArrowLeft, ArrowRight, ChevronRight } from "lucide-react";
import { usePageData } from "../../data/hooks/PageData";
import { EmptyState } from "../../components/ui/EmptyState";
import { IssueState } from "../../components/event/IssueState";
import {
  metricLabel,
  timestampLabel,
  sourceLabel,
} from "../event/presentation.js";
import { StockMark, SaveButton, MatchEvidence } from "./StockElements";
export default function StockDetail({ symbol, savedStocks, onToggleStock }) {
  const { events, getStock, collectionLimit } = usePageData();
  const stock = getStock(symbol);
  if (!stock)
    return (
      <div className="wp-page">
        <a href="#/stocks" className="st-back">
          <ArrowLeft size={16} />
          종목 탐색
        </a>
        <EmptyState
          title="종목을 찾지 못했습니다."
          description="다른 종목명이나 티커로 찾아보세요."
          action={
            <a href="#/stocks" className="wp-button" data-variant="primary">
              종목 탐색으로 돌아가기
            </a>
          }
        />
      </div>
    );
  const relatedEvents = events.filter((event) =>
    stock.eventIds.includes(event.id),
  );
  return (
    <div className="wp-page st-page st-detail-page">
      <a href="#/stocks" className="st-back">
        <ArrowLeft size={16} aria-hidden="true" />
        종목 탐색
      </a>
      <header className="wp-page-header st-detail-header">
        <div className="st-detail-identity">
          <StockMark stock={stock} large />
          <div>
            <h1>{stock.name}</h1>
            <p className="st-detail-meta">
              <strong>{stock.symbol}</strong>
              <span>{stock.exchange}</span>
              <span>{stock.sector || "산업 미제공"}</span>
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
      <p className="st-stock-description">
        {stock.description || "기업 소개가 제공되지 않았습니다."}
      </p>
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
              <p>사건을 열어 문서와 종목의 연결 근거를 확인하세요.</p>
            </div>
          </div>
          <p className="data-scope">
            관련 이슈는 최대 {collectionLimit || 50}개까지 제공됩니다. 전체
            개수와 이슈별 연결 설명은 이 목록에 제공되지 않았습니다.
          </p>
          <div className="st-event-timeline" aria-live="polite">
            {relatedEvents.length ? (
              relatedEvents.map((event) => {
                const relation = stock.relations?.find(
                  (item) => item.eventId === event.id,
                );
                return (
                  <article className="st-timeline-event" key={event.id}>
                    <div className="st-timeline-date">
                      <span className="st-timeline-dot" aria-hidden="true" />
                      <time dateTime={event.snapshotTs || undefined}>
                        {timestampLabel(event.snapshotTs)}
                      </time>
                      <span>{sourceLabel(event.source)}</span>
                    </div>
                    <div className="st-event-body">
                      <a
                        href={`#/issues/${encodeURIComponent(event.id)}`}
                        className="st-event-title"
                      >
                        <h3>{event.title}</h3>
                        <ArrowRight size={18} aria-hidden="true" />
                      </a>
                      {event.summary && (
                        <p className="st-event-summary">{event.summary}</p>
                      )}
                      <div className="st-event-metrics">
                        <span>문서 {metricLabel(event.memberCount, 0)}개</span>
                        <span>
                          급증 점수{" "}
                          <strong>{metricLabel(event.pulseScore)}</strong>
                        </span>
                        <IssueState status={event.status} />
                      </div>
                      {relation && <MatchEvidence relation={relation} />}
                      <a
                        href={`#/issues/${encodeURIComponent(event.id)}`}
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
                title="제공된 관련 사건이 없습니다."
                description="종목 탐색에서 다른 기업의 이슈를 살펴보세요."
                action={
                  <a className="wp-button" href="#/stocks">
                    종목 탐색
                  </a>
                }
              />
            )}
          </div>
        </section>
        <aside className="st-stock-aside" aria-label="종목 참고 정보">
          <section className="wp-panel st-price-panel">
            <div className="st-price-title">
              <h2>가격 흐름</h2>
              <span className="wp-tag">미제공</span>
            </div>
            <div className="data-availability">
              <strong>가격 자료 미제공</strong>
              <p>
                주가 시계열과 등락률이 제공되지 않았습니다. 이슈 발생 시점과
                가격을 비교할 자료가 없습니다.
              </p>
            </div>
          </section>
          <section className="st-how-to-read">
            <h2>연결은 이렇게 읽어요.</h2>
            <p>
              관련 이슈의 종목 화면에서 제공된 연결 유형과 설명을 확인하세요.
              후보 탐색 경로는 AI 신뢰도나 수익률을 뜻하지 않습니다.
            </p>
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
