package io.wikipulse.backend.stock.dto;

import java.math.BigDecimal;
import java.time.LocalDate;

/**
 * 종목 일봉 한 점. API 명세 v0.3 §4 `GET /stocks/{ticker}/prices`.
 *
 * <p>거래일만 있다 — 휴장일은 행이 없고 보간하지 않는다. open/high/low/volume 은
 * yfinance 결측 시 null 일 수 있고(스키마 nullable), close 는 NOT NULL 이라 항상 있다.
 * 6필드를 늘 내려보내 계약을 안정시킨다(null 이면 JSON null). 이슈 시점 표시는
 * 서버가 합쳐 내리지 않는다 — FE 가 `/stocks/{ticker}/issues` 의 snapshotTs 로 겹친다.
 */
public record StockPriceResponse(
        LocalDate tradeDate,
        BigDecimal open,
        BigDecimal high,
        BigDecimal low,
        BigDecimal close,
        Long volume) {

    public interface Projection {
        LocalDate getTradeDate();
        BigDecimal getOpen();
        BigDecimal getHigh();
        BigDecimal getLow();
        BigDecimal getClose();
        Long getVolume();
    }

    public static StockPriceResponse from(Projection p) {
        return new StockPriceResponse(
                p.getTradeDate(), p.getOpen(), p.getHigh(),
                p.getLow(), p.getClose(), p.getVolume());
    }
}
