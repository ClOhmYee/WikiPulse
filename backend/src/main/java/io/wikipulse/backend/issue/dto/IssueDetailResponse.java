package io.wikipulse.backend.issue.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import io.wikipulse.backend.issue.IssueCluster;
import io.wikipulse.backend.stock.dto.RelatedStockResponse;
import java.util.List;

/**
 * 이슈 상세. API 명세 v0.1 §2 `GET /issues/{id}`.
 *
 * <p>relatedStocks 는 `/issues/{id}/stocks` 와 같은 객체이며 상세 진입 시 왕복을
 * 줄이려고 상위 5개만 미리 담는다. 전체는 그 endpoint 로 부른다.
 * summary 는 issue_report — 아직 없으면 null.
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record IssueDetailResponse(
        long id,
        String label,
        double pulseScore,
        String status,
        String source,
        String snapshotTs,
        String summary,
        String summaryModel,
        List<IssueMemberResponse> members,
        List<RelatedStockResponse> relatedStocks) {

    public static IssueDetailResponse of(
            IssueCluster cluster,
            String summary,
            String summaryModel,
            List<IssueMemberResponse> members,
            List<RelatedStockResponse> relatedStocks) {
        return new IssueDetailResponse(
                cluster.getId(), cluster.getLabel(), cluster.getPulseScore(),
                cluster.getStatus(), cluster.getSource(),
                cluster.getSnapshotTs().toString(),
                summary, summaryModel, members, relatedStocks);
    }
}
