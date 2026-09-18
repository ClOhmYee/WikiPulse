package io.wikipulse.backend.stock.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import io.wikipulse.backend.stock.Stock;

/**
 * 종목 상세. API 명세 v0.3 §4 `GET /stocks/{ticker}`.
 * embedding 은 내보내지 않는다(1,536차원, 화면이 쓸 일 없음). 주가는 별도 endpoint.
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record StockResponse(
        String ticker,
        String name,
        String exchange,
        String cik,
        String sector,
        String businessSummary) {

    public static StockResponse from(Stock stock) {
        return new StockResponse(
                stock.getTicker(),
                stock.getName(),
                stock.getExchange(),
                stock.getCik(),
                stock.getSector(),
                stock.getBusinessSummary());
    }
}
