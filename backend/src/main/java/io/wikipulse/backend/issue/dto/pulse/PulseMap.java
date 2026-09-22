package io.wikipulse.backend.issue.dto.pulse;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.util.List;

/**
 * 펄스맵 지도 응답 DTO. 계약: frontend/docs/pulse-openapi.json (WP-74).
 *
 * <p>한 스냅샷의 그래프를 통째로 담는다. 모든 ID 는 전송 시 불투명 문자열이다
 * — 숫자 DB 키(BIGINT)를 문자열로 직렬화해 정밀도 손실을 막는다.
 *
 * <p>노드의 수치 지표는 <b>required 이지만 nullable</b> 이다(계약). 없으면 null 을
 * 그대로 내보내야 하므로 {@code Node} 에는 NON_NULL 을 걸지 않는다 — 화면이
 * completeness 로 null 과 0 을 구분한다. Meta.dataMode 만 선택적이라 NON_NULL 로 뺀다.
 */
public final class PulseMap {

    private PulseMap() {
    }

    /** {@code data} — 단일 스냅샷의 클러스터 목록. */
    public record Data(List<Cluster> clusters) {
    }

    public record Cluster(
            String id,
            String issueKey,
            String label,
            String summary,          // nullable — LLM 요약 전이면 null
            String category,
            String firstDetectedAt,   // nullable — 최초 감지 미제공이면 null
            boolean hot,
            double pulseScore,
            String status,
            long memberCount,
            List<Node> nodes,
            List<Edge> edges) {
    }

    public record Node(
            String pageId,
            String wiki,
            String title,             // 🔴 영문 원문. 위키 링크·식별자가 이걸 쓴다 — 대체하지 않는다
            String titleKo,           // nullable — ko 대응이 없으면 null, 화면이 title 로 떨어진다
            boolean isSeed,
            Integer editCount,        // 아래 수치는 모두 required+nullable — null 을 그대로 낸다
            Integer views,
            Double editBaseline,
            Double viewBaseline,
            Double spikeScore,
            Double sizeScore,
            String completeness,      // complete / pending / unavailable
            String windowStart,
            String windowEnd) {
    }

    public record Edge(
            String id,
            String sourcePageId,
            String targetPageId,
            String kind,              // clickstream / wikidata
            boolean directed,
            double weight,
            Evidence evidence) {
    }

    /** 근거. Clickstream 은 month, Wikidata 는 observedAt — 하나만 채운다. */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record Evidence(
            String label,
            String month,             // YYYY-MM (clickstream)
            String observedAt) {      // UTC ISO (wikidata)
    }

    /** {@code meta} — 실제 스냅샷 좌표와 개수. dataMode 만 선택적. */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record Meta(
            String snapshotTs,
            String source,
            String dataMode,          // 선택 — null 이면 필드 자체를 뺀다
            String scoreVersion,
            double newWindowHours,
            long clusterCount,
            long nodeCount,
            long edgeCount,
            boolean truncated) {
    }
}
