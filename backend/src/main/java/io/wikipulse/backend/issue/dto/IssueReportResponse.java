package io.wikipulse.backend.issue.dto;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * 이슈 상세의 섹션형 리포트 (WP-223). 프론트 `report` 계약과 같은 모양이다
 * (frontend/src/data/api/adapters.js `report`·`reportSection`).
 *
 * <p>저장된 행이 있을 때만 만든다 — 없으면 상세 응답에서 {@code report} 자체가 빠지고
 * 프론트는 기존처럼 "근거가 충분하지 않습니다" 상태를 보인다.
 */
public record IssueReportResponse(
        String status,
        String model,
        String generatedAt,
        String snapshotTs,
        List<Section> sections) {

    /** evidenceIds 는 이 클러스터 멤버의 pageId(문자열). 프론트 근거 칩이 멤버로 찾는다. */
    public record Section(String id, String title, String body, List<String> evidenceIds) {}

    /** issue_report 에서 읽는 리포트 컬럼. */
    public interface Projection {
        String getSections();
        String getModel();
        Instant getGeneratedAt();
    }

    private static final Logger log = LoggerFactory.getLogger(IssueReportResponse.class);

    private static final ObjectMapper MAPPER = new ObjectMapper()
            .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);

    private static final TypeReference<List<Section>> SECTIONS = new TypeReference<>() {};

    /**
     * 저장된 JSON 을 응답으로 바꾼다. 깨진 JSON·빈 배열이면 비운다 — 상세 조회 전체를
     * 500 으로 만들지 않는다. 대신 로그를 남긴다(조용히 사라지면 원인을 못 찾는다).
     */
    public static Optional<IssueReportResponse> from(Projection row, String snapshotTs) {
        if (row == null || row.getSections() == null) {
            return Optional.empty();
        }
        try {
            List<Section> sections = MAPPER.readValue(row.getSections(), SECTIONS).stream()
                    .filter(s -> s.id() != null && !s.id().isBlank()
                            && s.title() != null && !s.title().isBlank())
                    .map(s -> new Section(s.id(), s.title(), s.body(),
                            s.evidenceIds() == null ? List.of() : s.evidenceIds()))
                    .toList();
            if (sections.isEmpty()) {
                return Optional.empty();
            }
            return Optional.of(new IssueReportResponse("ready", row.getModel(),
                    row.getGeneratedAt() == null ? null : row.getGeneratedAt().toString(),
                    snapshotTs, sections));
        } catch (Exception e) {
            log.warn("issue_report.report_sections 를 읽지 못했다 — report 를 비운다: {}", e.toString());
            return Optional.empty();
        }
    }
}
