package io.wikipulse.backend.issue;

import io.wikipulse.backend.issue.dto.IssueCardResponse;
import io.wikipulse.backend.issue.dto.IssueDetailResponse;
import java.time.Instant;
import java.util.List;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 이슈 피드·버블맵·상세.
 *
 * <p>피드와 버블맵은 같은 데이터를 카드/버블로 다르게 그릴 뿐이라 한 엔드포인트를
 * 공유한다. snapshotTs 를 주면 그 시점을 재생(리플레이), 안 주면 최근 LIVE.
 */
@RestController
@RequestMapping("/api/issues")
public class IssueController {

    private final IssueService service;

    public IssueController(IssueService service) {
        this.service = service;
    }

    /** GET /api/issues?snapshotTs=&status=&limit= */
    @GetMapping
    public List<IssueCardResponse> feed(
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) Instant snapshotTs,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) Integer limit) {
        return service.feed(snapshotTs, status, limit);
    }

    /** GET /api/issues/{id} */
    @GetMapping("/{id}")
    public IssueDetailResponse detail(@PathVariable Long id) {
        return service.detail(id);
    }
}
