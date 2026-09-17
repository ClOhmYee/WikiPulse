package io.wikipulse.backend.stock.dto;

/**
 * 종목 목록 카드. API 명세 v0.2 §4 `GET /stocks`.
 *
 * <p>businessSummary 는 목록에 넣지 않는다 — 종목당 수천 자라 5,100건이면
 * 수 MB가 된다. issueCount 는 걸린 이슈 수(배지용).
 */
public record StockCardResponse(
        String ticker,
        String name,
        String exchange,
        String sector,
        long issueCount) {

    public interface Projection {
        String getTicker();
        String getName();
        String getExchange();
        String getSector();
        long getIssueCount();
    }

    public static StockCardResponse from(Projection p) {
        return new StockCardResponse(
                p.getTicker(), p.getName(), p.getExchange(),
                p.getSector(), p.getIssueCount());
    }
}
