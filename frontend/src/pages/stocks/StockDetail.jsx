import { useCallback, useMemo } from "react";
import { ArrowLeft, ArrowRight, ChevronRight } from "lucide-react";
import { usePageData } from "../../data/hooks/PageData";
import { EmptyState } from "../../components/ui/EmptyState";
import { IssueState } from "../../components/event/IssueState";
import { TrendChart } from "../../components/charts/TrendChart";
import { dataClient } from "../../data/index.js";
import { useAsyncResource } from "../../data/hooks/useAsyncResource.js";
import {
  metricLabel,
  timestampLabel,
  sourceLabel,
} from "../event/presentation.js";
import { StockMark, SaveButton, MatchEvidence } from "./StockElements";
export default function StockDetail({ symbol, savedStocks, onToggleStock }) {
  const { events, getStock, collectionLimit, isExample } = usePageData();
  const stock = getStock(symbol);
  // 훅은 조기 반환 전에 무조건 호출한다(rules-of-hooks). stock 이 없으면 빈 값.
  const relatedEvents = useMemo(
    () =>
      stock ? events.filter((event) => stock.eventIds.includes(event.id)) : [],
    [events, stock],
  );
  // 차트 위에 겹칠 이슈 발생 시점 마커. 마커에서 이슈 상세로 이동한다.
  const markers = useMemo(
    () =>
      relatedEvents
        .filter((event) => event.snapshotTs)
        .map((event) => ({
          key: event.id,
          date: String(event.snapshotTs).slice(0, 10),
          label: event.title,
          href: `#/issues/${encodeURIComponent(event.id)}`,
        })),
    [relatedEvents],
  );
  // 가격 창은 "최근 1년"과 "모든 연관 이슈 시점"을 모두 포함해야 한다. 마커가
  // 있으면 from 을 명시해(둘 중 더 이른 시점 − 14일) 보낸다 — from 을 생략하면
  // 서버가 자기 TZ 로 today−1년을 잡아 경계 근처 마커가 하루 차이로 조용히 잘린다.
  const from = useMemo(() => {
    const stamps = markers
      .map((marker) => Date.parse(marker.date))
      .filter(Number.isFinite);
    if (!stamps.length) return undefined;
    const oneYearAgo = new Date();
    oneYearAgo.setFullYear(oneYearAgo.getFullYear() - 1);
    const earliest = new Date(Math.min(...stamps));
    earliest.setDate(earliest.getDate() - 14); // 왼쪽 여유
    const start = Math.min(oneYearAgo.getTime(), earliest.getTime());
    return new Date(start).toISOString().slice(0, 10);
  }, [markers]);
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
          <StockPriceSection
            symbol={stock.symbol}
            from={from}
            markers={markers}
            isExample={isExample}
          />
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

/**
 * 종목 상세 가격 흐름. /stocks/{ticker}/prices 에 독립적으로 연결한다 —
 * 가격 로딩 실패가 페이지 전체를 깨지 않게 자체 상태를 가진다.
 * 🔴 API 실패 시 mock 폴백 금지(UI_GUIDE) — loading·error·unavailable·empty 를 구분한다.
 */
function StockPriceSection({ symbol, from, markers, isExample }) {
  const params = useMemo(() => (from ? { from } : {}), [from]);
  const key = JSON.stringify({ symbol, from: from ?? null, isExample });
  const load = useCallback(
    // 데모 데이터에는 주가가 없다 — 불필요한 호출을 생략하고 바로 unavailable 로.
    (signal) =>
      isExample
        ? Promise.resolve({ data: [] })
        : dataClient.getStockPrices(symbol, params, { signal }),
    [symbol, params, isExample],
  );
  const { data, error, loading, reload } = useAsyncResource(load, key);
  const points = useMemo(
    () =>
      (data?.data ?? []).map((row) => ({
        date: row.tradeDate,
        price: row.close,
        open: row.open,
        high: row.high,
        low: row.low,
        volume: row.volume,
      })),
    [data],
  );
  const heading = (tag) => (
    <div className="st-price-title">
      <h2>가격 흐름</h2>
      {tag}
    </div>
  );
  // 데모 데이터에는 주가가 없다(unavailable). 실데이터 empty 와 다른 상태로 구분한다.
  if (isExample)
    return (
      <section className="wp-panel st-price-panel">
        {heading(null)}
        <div className="data-availability">
          <strong>주가 정보가 제공되지 않았습니다</strong>
          <p>현재 이 종목의 일봉 정보를 확인할 수 없습니다.</p>
        </div>
      </section>
    );
  if (loading && !data)
    return (
      <section className="wp-panel st-price-panel">
        {heading(<span className="wp-tag">불러오는 중</span>)}
        <div
          className="data-availability"
          role="status"
          aria-label="가격 불러오는 중"
        >
          <span className="wp-skeleton wp-skeleton--panel" />
        </div>
      </section>
    );
  if (error)
    return (
      <section className="wp-panel st-price-panel">
        {heading(<span className="wp-tag">불러오기 실패</span>)}
        <div className="data-availability">
          <strong>가격을 불러오지 못했습니다</strong>
          <p>{error.message}</p>
          <button className="wp-button" data-variant="ghost" onClick={reload}>
            다시 시도
          </button>
        </div>
      </section>
    );
  if (!points.length)
    return (
      <section className="wp-panel st-price-panel">
        {heading(<span className="wp-tag">데이터 미준비</span>)}
        <div className="data-availability">
          <strong>가격 데이터가 아직 준비되지 않았습니다</strong>
          <p>이 종목의 일봉이 적재되면 이슈 발생 시점과 함께 표시됩니다.</p>
        </div>
      </section>
    );
  return (
    <section
      className="wp-panel st-price-panel"
      aria-labelledby="stock-price-title"
    >
      <div className="st-price-title">
        <h2 id="stock-price-title">가격 흐름</h2>
        <span className="wp-muted">{points.length}거래일 · 종가(USD)</span>
      </div>
      <TrendChart
        data={points}
        valueKey="price"
        label="종가"
        color="#86c9c4"
        height={220}
        markers={markers}
        isExample={false}
      />
      <p className="data-scope">
        조정 전 원시 종가입니다. 분할·배당일에 값이 튈 수 있으며 정밀 수익률이
        아니라 참고용입니다. 마커는 이 종목과 연결된 이슈 발생 시점입니다.
      </p>
    </section>
  );
}
