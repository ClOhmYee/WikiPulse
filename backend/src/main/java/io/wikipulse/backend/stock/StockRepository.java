package io.wikipulse.backend.stock;

import io.wikipulse.backend.stock.dto.StockCardResponse;
import io.wikipulse.backend.stock.dto.StockPriceResponse;
import java.time.LocalDate;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface StockRepository extends JpaRepository<Stock, String> {

    /**
     * 종목 일봉. API 명세 v0.3 §4 `GET /stocks/{ticker}/prices`.
     * [from, to] 구간의 거래일만 오름차순으로. 휴장일은 행이 없다(보간 안 함).
     * 티커 존재 검증은 서비스가 먼저 한다 — 여기서 0행은 "그 구간 데이터 없음"이다.
     */
    @Query(value = """
            SELECT trade_date AS tradeDate, open AS open, high AS high,
                   low AS low, close AS close, volume AS volume
            FROM stock_price
            WHERE ticker = :ticker
              AND trade_date >= :from
              AND trade_date <= :to
            ORDER BY trade_date ASC
            """, nativeQuery = true)
    List<StockPriceResponse.Projection> findPrices(
            @Param("ticker") String ticker,
            @Param("from") LocalDate from,
            @Param("to") LocalDate to);

    /**
     * 종목 목록. API 명세 v0.3 §4 `GET /stocks`.
     * q(회사명·티커 부분 일치, 대소문자 무시)·sector·exchange·hasIssues 필터.
     * businessSummary 는 목록에서 뺀다(수천 자 × 5,100건).
     * issueCount 는 verified·비DISCARDED 이슈만 센다.
     */
    @Query(value = """
            SELECT s.ticker AS ticker, s.name AS name, s.exchange AS exchange,
                   s.sector AS sector,
                   (SELECT count(DISTINCT cs.cluster_id) FROM cluster_stock cs
                     JOIN issue_cluster c ON c.id = cs.cluster_id
                    WHERE cs.ticker = s.ticker AND cs.verified AND c.status <> 'DISCARDED') AS issueCount
            FROM stock s
            WHERE (:q IS NULL OR lower(s.name) LIKE :q OR lower(s.ticker) LIKE :q)
              AND (:sector IS NULL OR s.sector = :sector)
              AND (:exchange IS NULL OR s.exchange = :exchange)
              AND (:hasIssues = false OR EXISTS (
                     SELECT 1 FROM cluster_stock cs2 JOIN issue_cluster c2 ON c2.id = cs2.cluster_id
                      WHERE cs2.ticker = s.ticker AND cs2.verified AND c2.status <> 'DISCARDED'))
            ORDER BY s.ticker
            OFFSET :offset LIMIT :limit
            """, nativeQuery = true)
    List<StockCardResponse.Projection> findCards(
            @Param("q") String q, @Param("sector") String sector,
            @Param("exchange") String exchange, @Param("hasIssues") boolean hasIssues,
            @Param("offset") int offset, @Param("limit") int limit);

    @Query(value = """
            SELECT count(*) FROM stock s
            WHERE (:q IS NULL OR lower(s.name) LIKE :q OR lower(s.ticker) LIKE :q)
              AND (:sector IS NULL OR s.sector = :sector)
              AND (:exchange IS NULL OR s.exchange = :exchange)
              AND (:hasIssues = false OR EXISTS (
                     SELECT 1 FROM cluster_stock cs2 JOIN issue_cluster c2 ON c2.id = cs2.cluster_id
                      WHERE cs2.ticker = s.ticker AND cs2.verified AND c2.status <> 'DISCARDED'))
            """, nativeQuery = true)
    long countCards(
            @Param("q") String q, @Param("sector") String sector,
            @Param("exchange") String exchange, @Param("hasIssues") boolean hasIssues);
}
