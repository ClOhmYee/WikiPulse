package io.wikipulse.backend.stock.dto;

import io.wikipulse.backend.stock.Stock;

/** 종목 상세 응답. 주가 그래프는 별도 엔드포인트(WP-10)라 여기 없다. */
public record StockResponse(
        String ticker,
        String name,
        String exchange,
        String sector,
        String businessSummary) {

    public static StockResponse from(Stock stock) {
        return new StockResponse(
                stock.getTicker(),
                stock.getName(),
                stock.getExchange(),
                stock.getSector(),
                stock.getBusinessSummary());
    }
}
