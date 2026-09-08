package io.wikipulse.backend.stock;

import io.wikipulse.backend.issue.dto.IssueCardResponse;
import io.wikipulse.backend.stock.dto.StockResponse;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/stocks")
public class StockController {

    private final StockService service;

    public StockController(StockService service) {
        this.service = service;
    }

    /** GET /api/stocks/{ticker} */
    @GetMapping("/{ticker}")
    public StockResponse get(@PathVariable String ticker) {
        return service.get(ticker);
    }

    /** GET /api/stocks/{ticker}/issues — 이 종목이 걸린 이슈들 */
    @GetMapping("/{ticker}/issues")
    public List<IssueCardResponse> issues(@PathVariable String ticker) {
        return service.issuesFor(ticker);
    }
}
