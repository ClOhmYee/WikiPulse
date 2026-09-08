package io.wikipulse.backend.stock;

import io.wikipulse.backend.common.NotFoundException;
import io.wikipulse.backend.issue.IssueQueryRepository;
import io.wikipulse.backend.issue.dto.IssueCardResponse;
import io.wikipulse.backend.stock.dto.StockResponse;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class StockService {

    private static final int DEFAULT_ISSUE_LIMIT = 20;

    private final StockRepository stockRepository;
    private final IssueQueryRepository issueQueryRepository;

    public StockService(StockRepository stockRepository,
                        IssueQueryRepository issueQueryRepository) {
        this.stockRepository = stockRepository;
        this.issueQueryRepository = issueQueryRepository;
    }

    public StockResponse get(String ticker) {
        return stockRepository.findById(ticker.toUpperCase())
                .map(StockResponse::from)
                .orElseThrow(() -> new NotFoundException("종목 %s 없음".formatted(ticker)));
    }

    /** 이 종목이 걸린 최근 확정 이슈. 종목 상세 화면 아래에 붙는다. */
    public List<IssueCardResponse> issuesFor(String ticker) {
        String normalized = ticker.toUpperCase();
        // 종목이 없으면 404. 있는데 이슈가 없으면 빈 리스트.
        if (!stockRepository.existsById(normalized)) {
            throw new NotFoundException("종목 %s 없음".formatted(ticker));
        }
        return issueQueryRepository.findIssuesByTicker(normalized, DEFAULT_ISSUE_LIMIT).stream()
                .map(p -> new IssueCardResponse(
                        p.getId(), p.getLabel(), p.getPulseScore(),
                        p.getStatus(), p.getSnapshotTs()))
                .toList();
    }
}
