package io.wikipulse.backend.issue.dto;

import java.time.Instant;

/** 완료된 시점 전체에서 같은 대표 문서 키를 한 건으로 표시한다. */
public record IssueHistoryGroupResponse(
        long id, String label, String source, String status, double pulseScore,
        String snapshotTs, String firstSeen, long occurrenceCount,
        Long defaultReportId, String summary, long memberCount, long stockCount) {

    public interface Projection {
        long getId();
        String getLabel();
        String getSource();
        String getStatus();
        double getPulseScore();
        Instant getSnapshotTs();
        Instant getFirstSeen();
        long getOccurrenceCount();
        Long getDefaultReportId();
        String getSummary();
        long getMemberCount();
        long getStockCount();
    }

    public static IssueHistoryGroupResponse from(Projection p) {
        return new IssueHistoryGroupResponse(p.getId(), p.getLabel(), p.getSource(),
                p.getStatus(), p.getPulseScore(), p.getSnapshotTs().toString(),
                p.getFirstSeen().toString(), p.getOccurrenceCount(),
                p.getDefaultReportId(), p.getSummary(), p.getMemberCount(), p.getStockCount());
    }
}
