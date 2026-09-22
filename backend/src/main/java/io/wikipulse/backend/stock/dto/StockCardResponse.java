package io.wikipulse.backend.stock.dto;

import java.math.BigDecimal;

/**
 * 종목 목록 카드. API 명세 v0.3 §4 `GET /stocks`.
 *
 * <p>businessSummary 는 목록에 넣지 않는다 — 종목당 수천 자라 5,100건이면
 * 수 MB가 된다. issueCount 는 걸린 이슈 수(배지용).
 *
 * <p>lastClose 는 최신 거래일 종가다(가격 컬럼용, WP-189). 일봉이 없는
 * 종목은 null — FE 는 "미제공"으로 표시한다. stock_price.close 가 NUMERIC(14,4)라
 * 부동소수 대신 {@link BigDecimal} 로 받는다.
 */
public record StockCardResponse(
        String ticker,
        String name,
        String exchange,
        String sector,
        long issueCount,
        BigDecimal lastClose) {

    public interface Projection {
        String getTicker();
        String getName();
        String getExchange();
        String getSector();
        long getIssueCount();
        BigDecimal getLastClose();
    }

    public static StockCardResponse from(Projection p) {
        return new StockCardResponse(
                p.getTicker(), p.getName(), p.getExchange(),
                p.getSector(), p.getIssueCount(), p.getLastClose());
    }
}
