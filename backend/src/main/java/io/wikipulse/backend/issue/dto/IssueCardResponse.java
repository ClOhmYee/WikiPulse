package io.wikipulse.backend.issue.dto;

/**
 * 이슈 피드 카드 / 버블맵 버블. API 명세 v0.1 §2 `GET /issues`.
 *
 * <p>memberCount·stockCount 는 버블 크기·배지용 집계다 — 목록에서 상세를 N번
 * 부르지 않게 하려고 넣었다. label 은 LLM 이 붙기 전 null (FE 가 대표 문서명 사용).
 */
public record IssueCardResponse(
        long id,
        String label,
        double pulseScore,
        String status,
        String source,
        String snapshotTs,
        long memberCount,
        long stockCount) {

    /** 프로젝션에서 조립. snapshotTs 는 Instant 를 ISO 8601 UTC 문자열로. */
    public interface Projection {
        long getId();
        String getLabel();
        double getPulseScore();
        String getStatus();
        String getSource();
        java.time.Instant getSnapshotTs();
        long getMemberCount();
        long getStockCount();
    }

    public static IssueCardResponse from(Projection p) {
        return new IssueCardResponse(
                p.getId(), p.getLabel(), p.getPulseScore(), p.getStatus(),
                p.getSource(), p.getSnapshotTs().toString(),
                p.getMemberCount(), p.getStockCount());
    }
}
