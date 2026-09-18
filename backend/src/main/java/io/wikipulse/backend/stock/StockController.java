package io.wikipulse.backend.stock;

import io.wikipulse.backend.common.ApiResponse;
import io.wikipulse.backend.issue.dto.IssueCardResponse;
import io.wikipulse.backend.stock.dto.StockCardResponse;
import io.wikipulse.backend.stock.dto.StockResponse;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 종목. API 명세 v0.3 §4. */
@RestController
@RequestMapping("/api/v1/stocks")
public class StockController {

    private final StockService service;

    public StockController(StockService service) {
        this.service = service;
    }

    /** GET /api/v1/stocks?q=&sector=&exchange=&hasIssues=&offset=&limit= */
    @GetMapping
    public ApiResponse<List<StockCardResponse>> search(
            @RequestParam(required = false) String q,
            @RequestParam(required = false) String sector,
            @RequestParam(required = false) String exchange,
            @RequestParam(required = false, defaultValue = "false") boolean hasIssues,
            @RequestParam(required = false) Integer offset,
            @RequestParam(required = false) Integer limit) {
        return service.search(q, sector, exchange, hasIssues, offset, limit);
    }

    /** GET /api/v1/stocks/{ticker} */
    @GetMapping("/{ticker}")
    public ApiResponse<StockResponse> get(@PathVariable String ticker) {
        return service.get(ticker);
    }

    /** GET /api/v1/stocks/{ticker}/issues */
    @GetMapping("/{ticker}/issues")
    public ApiResponse<List<IssueCardResponse>> issues(@PathVariable String ticker) {
        return service.issuesFor(ticker);
    }
}
