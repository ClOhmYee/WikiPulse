package io.wikipulse.backend.issue.dto;

import io.wikipulse.backend.issue.IssueCluster;
import java.time.Instant;

/**
 * 이슈 피드 카드 / 버블맵 버블 하나의 응답 형태.
 *
 * <p>FE 와의 계약이다. 엔티티를 그대로 내보내지 않는다 — 컬럼이 바뀌어도
 * 응답 형태를 여기서 지킨다. label 이 아직 없으면(확정 전) FE 가 대표 문서명을
 * 쓸 수 있게 null 을 그대로 보낸다.
 */
public record IssueCardResponse(
        Long id,
        String label,
        double pulseScore,
        String status,
        Instant snapshotTs) {

    public static IssueCardResponse from(IssueCluster cluster) {
        return new IssueCardResponse(
                cluster.getId(),
                cluster.getLabel(),
                cluster.getPulseScore(),
                cluster.getStatus(),
                cluster.getSnapshotTs());
    }
}
