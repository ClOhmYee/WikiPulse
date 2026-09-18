package io.wikipulse.backend.stock;

import io.wikipulse.backend.common.ApiException;
import io.wikipulse.backend.common.ApiResponse;
import io.wikipulse.backend.common.PageMeta;
import io.wikipulse.backend.common.QueryParams;
import io.wikipulse.backend.issue.IssueQueryRepository;
import io.wikipulse.backend.issue.dto.IssueCardResponse;
import io.wikipulse.backend.stock.dto.StockCardResponse;
import io.wikipulse.backend.stock.dto.StockPriceResponse;
import io.wikipulse.backend.stock.dto.StockResponse;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class StockService {

    private static final int TICKER_ISSUE_LIMIT = 50;
    // 기본 조회 구간: 최근 1년 (명세 §4).
    private static final int DEFAULT_RANGE_YEARS = 1;

    private final StockRepository stockRepository;
    private final IssueQueryRepository issueQueryRepository;

    public StockService(StockRepository stockRepository,
                        IssueQueryRepository issueQueryRepository) {
        this.stockRepository = stockRepository;
        this.issueQueryRepository = issueQueryRepository;
    }

    /** 종목 목록 검색. 봉투 + pagination meta. */
    public ApiResponse<List<StockCardResponse>> search(
            String q, String sector, String exchange, boolean hasIssues,
            Integer offset, Integer limit) {
        int off = QueryParams.offset(offset);
        int lim = QueryParams.limit(limit);
        String pattern = QueryParams.likePattern(q);

        long total = stockRepository.countCards(pattern, sector, exchange, hasIssues);
        List<StockCardResponse> cards = stockRepository
                .findCards(pattern, sector, exchange, hasIssues, off, lim)
                .stream().map(StockCardResponse::from).toList();

        return ApiResponse.of(cards,
                PageMeta.of(PageMeta.Pagination.of(off, lim, total, cards.size())));
    }

    public ApiResponse<StockResponse> get(String ticker) {
        return stockRepository.findById(ticker.toUpperCase())
                .map(s -> ApiResponse.of(StockResponse.from(s)))
                .orElseThrow(() -> ApiException.notFound("stock %s not found".formatted(ticker)));
    }

    /** 이 종목이 걸린 이슈. verified·비DISCARDED만. */
    public ApiResponse<List<IssueCardResponse>> issuesFor(String ticker) {
        String normalized = ticker.toUpperCase();
        if (!stockRepository.existsById(normalized)) {
            throw ApiException.notFound("stock %s not found".formatted(ticker));
        }
        List<IssueCardResponse> issues = issueQueryRepository
                .findIssuesByTicker(normalized, TICKER_ISSUE_LIMIT)
                .stream().map(IssueCardResponse::from).toList();
        return ApiResponse.of(issues);
    }

    /**
     * 종목 일봉. 쿼리 from·to(YYYY-MM-DD), 기본 최근 1년.
     *
     * <p>🔴 없는 티커(404)와 티커는 있으나 구간에 데이터가 0건(200 + 빈 data)을 구분한다.
     * 전자는 마스터에 없는 것, 후자는 정상 응답이다. 거래일만 오름차순으로 내린다.
     */
    public ApiResponse<List<StockPriceResponse>> prices(String ticker, String from, String to) {
        String normalized = ticker.toUpperCase();
        if (!stockRepository.existsById(normalized)) {
            throw ApiException.notFound("stock %s not found".formatted(ticker));
        }
        LocalDate toDate = parseDate("to", to, LocalDate.now());
        LocalDate fromDate = parseDate("from", from, toDate.minusYears(DEFAULT_RANGE_YEARS));
        if (fromDate.isAfter(toDate)) {
            throw ApiException.invalidQuery("from must be on or before to");
        }
        List<StockPriceResponse> prices = stockRepository
                .findPrices(normalized, fromDate, toDate)
                .stream().map(StockPriceResponse::from).toList();
        return ApiResponse.of(prices);
    }

    /** YYYY-MM-DD 를 엄격히 파싱한다. 비었으면 기본값, 형식이 틀리면 INVALID_QUERY. */
    private static LocalDate parseDate(String field, String value, LocalDate fallback) {
        if (value == null || value.isBlank()) {
            return fallback;
        }
        try {
            return LocalDate.parse(value);
        } catch (DateTimeParseException e) {
            throw ApiException.invalidQuery("%s must be YYYY-MM-DD".formatted(field));
        }
    }
}
