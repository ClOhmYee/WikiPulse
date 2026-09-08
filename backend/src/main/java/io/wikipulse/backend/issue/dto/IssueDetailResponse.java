package io.wikipulse.backend.issue.dto;

import io.wikipulse.backend.issue.IssueCluster;
import io.wikipulse.backend.stock.dto.RelatedStockResponse;
import java.time.Instant;
import java.util.List;

/**
 * 이슈 상세 응답. 카드 정보 + 묶인 문서 + 관련 종목.
 *
 * <p>members 와 relatedStocks 는 아직 파이프라인이 안 채워서 지금은 빈 리스트로
 * 나갈 수 있다. FE 는 빈 배열을 "없음"으로 처리하면 된다.
 */
public record IssueDetailResponse(
        Long id,
        String label,
        double pulseScore,
        String status,
        String source,
        Instant snapshotTs,
        List<String> memberTitles,
        String summary,
        List<RelatedStockResponse> relatedStocks) {

    public static IssueDetailResponse of(
            IssueCluster cluster,
            List<String> memberTitles,
            String summary,
            List<RelatedStockResponse> relatedStocks) {
        return new IssueDetailResponse(
                cluster.getId(),
                cluster.getLabel(),
                cluster.getPulseScore(),
                cluster.getStatus(),
                cluster.getSource(),
                cluster.getSnapshotTs(),
                memberTitles,
                summary,
                relatedStocks);
    }
}
