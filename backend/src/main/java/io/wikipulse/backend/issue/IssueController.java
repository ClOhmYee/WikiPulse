package io.wikipulse.backend.issue;

import io.wikipulse.backend.common.ApiResponse;
import io.wikipulse.backend.issue.dto.IssueCardResponse;
import io.wikipulse.backend.issue.dto.IssueDetailResponse;
import io.wikipulse.backend.stock.dto.RelatedStockResponse;
import java.time.Instant;
import java.util.List;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 이슈 피드·버블맵·상세. API 명세 v0.1 §2.
 *
 * <p>피드와 버블맵은 같은 데이터를 카드/버블로 다르게 그릴 뿐이라 endpoint 를
 * 공유한다. snapshotTs 를 주면 그 시점(리플레이), 안 주면 최근 스냅샷.
 */
@RestController
@RequestMapping("/api/v1/issues")
public class IssueController {

    private final IssueService service;

    public IssueController(IssueService service) {
        this.service = service;
    }

    /** GET /api/v1/issues?snapshotTs=&status=&source=&offset=&limit= */
    @GetMapping
    public ApiResponse<List<IssueCardResponse>> feed(
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) Instant snapshotTs,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String source,
            @RequestParam(required = false) Integer offset,
            @RequestParam(required = false) Integer limit) {
        return service.feed(snapshotTs, status, source, offset, limit);
    }

    /** GET /api/v1/issues/{id} */
    @GetMapping("/{id}")
    public ApiResponse<IssueDetailResponse> detail(@PathVariable Long id) {
        return service.detail(id);
    }

    /** GET /api/v1/issues/{id}/stocks — 전체 관련 종목 */
    @GetMapping("/{id}/stocks")
    public ApiResponse<List<RelatedStockResponse>> stocks(
            @PathVariable Long id,
            @RequestParam(required = false) Integer limit) {
        return service.stocks(id, limit);
    }
}
