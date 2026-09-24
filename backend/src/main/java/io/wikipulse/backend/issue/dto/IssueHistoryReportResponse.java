package io.wikipulse.backend.issue.dto;

import java.time.Instant;

/** 날짜 선택에 필요한 리포트 보유 시점의 최소 정보. */
public record IssueHistoryReportResponse(long id, String snapshotTs, String status,
                                         double pulseScore) {
    public interface Projection {
        long getId();
        Instant getSnapshotTs();
        String getStatus();
        double getPulseScore();
    }

    public static IssueHistoryReportResponse from(Projection p) {
        return new IssueHistoryReportResponse(p.getId(), p.getSnapshotTs().toString(),
                p.getStatus(), p.getPulseScore());
    }
}
