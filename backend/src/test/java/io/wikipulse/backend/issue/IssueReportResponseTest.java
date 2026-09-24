package io.wikipulse.backend.issue;

import static org.assertj.core.api.Assertions.assertThat;

import io.wikipulse.backend.issue.dto.IssueReportResponse;
import java.time.Instant;
import org.junit.jupiter.api.Test;

/** 저장된 리포트 JSON → 상세 응답 report (WP-223). */
class IssueReportResponseTest {

    private static IssueReportResponse.Projection row(String json) {
        return new IssueReportResponse.Projection() {
            public String getSections() { return json; }
            public String getModel() { return "claude-sonnet-4-5 (report_v1)"; }
            public Instant getGeneratedAt() { return Instant.parse("2026-09-24T05:00:00Z"); }
        };
    }

    @Test
    void 섹션을_프론트_계약_모양으로_낸다() {
        var report = IssueReportResponse.from(row("""
                [{"id":"overview","title":"이슈 개요","body":"본문","evidenceIds":["901","902"]}]
                """), "2026-07-19T23:00:00Z").orElseThrow();

        assertThat(report.status()).isEqualTo("ready");
        assertThat(report.snapshotTs()).isEqualTo("2026-07-19T23:00:00Z");
        assertThat(report.generatedAt()).isEqualTo("2026-09-24T05:00:00Z");
        assertThat(report.sections()).singleElement().satisfies(s -> {
            assertThat(s.id()).isEqualTo("overview");
            assertThat(s.evidenceIds()).containsExactly("901", "902");
        });
    }

    @Test
    void 근거가_없는_섹션은_빈_목록이다() {
        var report = IssueReportResponse.from(row("""
                [{"id":"stocks","title":"관련 종목","body":"없음"}]
                """), "t").orElseThrow();
        assertThat(report.sections().get(0).evidenceIds()).isEmpty();
    }

    @Test
    void 깨진_JSON이나_빈_배열이면_리포트를_비운다() {
        // 상세 조회 전체를 500 으로 만들지 않는다 — 리포트만 빠진다.
        assertThat(IssueReportResponse.from(row("{not json"), "t")).isEmpty();
        assertThat(IssueReportResponse.from(row("[]"), "t")).isEmpty();
        assertThat(IssueReportResponse.from(row("[{\"body\":\"제목 없음\"}]"), "t")).isEmpty();
    }

    @Test
    void 행이_없으면_리포트도_없다() {
        assertThat(IssueReportResponse.from(null, "t")).isEmpty();
        assertThat(IssueReportResponse.from(row(null), "t")).isEmpty();
    }
}
