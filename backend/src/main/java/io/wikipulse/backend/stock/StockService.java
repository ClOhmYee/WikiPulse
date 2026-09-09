package io.wikipulse.backend.stock;

import io.wikipulse.backend.common.ApiException;
import io.wikipulse.backend.common.ApiResponse;
import io.wikipulse.backend.common.PageMeta;
import io.wikipulse.backend.common.QueryParams;
import io.wikipulse.backend.issue.IssueQueryRepository;
import io.wikipulse.backend.issue.dto.IssueCardResponse;
import io.wikipulse.backend.stock.dto.StockCardResponse;
import io.wikipulse.backend.stock.dto.StockResponse;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class StockService {

    private static final int TICKER_ISSUE_LIMIT = 50;

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
}
