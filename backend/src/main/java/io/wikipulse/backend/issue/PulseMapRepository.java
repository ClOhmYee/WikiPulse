package io.wikipulse.backend.issue;

import io.wikipulse.backend.issue.dto.pulse.SnapshotView;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/**
 * 펄스맵 스냅샷·그래프 조회 (WP-74). 네이티브 프로젝션 모음.
 *
 * <p>한 스냅샷을 통째로 그리므로 클러스터·노드·간선을 각각 한 번씩만 벌크로 읽고
 * 서비스가 cluster_id 로 묶는다 — 문서별 N+1 요청을 만들지 않는다(계약).
 * DISCARDED 클러스터는 어떤 조회에도 나오지 않는다.
 *
 * <p>지표는 cluster_member 에 <b>고정 저장된 값</b>을 그대로 읽는다(WP-75).
 * 리플레이가 현재 spike/page_view 를 다시 읽으면 과거·현재가 섞이므로 하지 않는다.
 */
public interface PulseMapRepository extends JpaRepository<IssueCluster, Long> {

    // ---- 스냅샷 목록 -------------------------------------------------------

    /** 완료된 스냅샷. 0개 스냅샷 포함. from/to/source 는 선택. 최신 우선. */
    @Query(value = """
            SELECT snapshot_ts AS snapshotTs, source AS source, cluster_count AS clusterCount
            FROM cluster_snapshot
            WHERE (CAST(:from AS timestamptz) IS NULL OR snapshot_ts >= CAST(:from AS timestamptz))
              AND (CAST(:to   AS timestamptz) IS NULL OR snapshot_ts <= CAST(:to   AS timestamptz))
              AND (CAST(:source AS text) IS NULL OR source = CAST(:source AS text))
            ORDER BY snapshot_ts DESC, source
            """, nativeQuery = true)
    List<SnapshotView.Projection> findSnapshots(
            @Param("from") Instant from,
            @Param("to") Instant to,
            @Param("source") String source);

    // ---- 스냅샷 해결(존재 확인 + 메타) ------------------------------------

    /** (source, snapshotTs) 로 완료 스냅샷을 찾는다. 없으면 비어 있다 → 404. */
    @Query(value = """
            SELECT snapshot_ts AS snapshotTs, source AS source,
                   score_version AS scoreVersion, new_window_hours AS newWindowHours
            FROM cluster_snapshot
            WHERE snapshot_ts = :snapshotTs AND source = :source
            """, nativeQuery = true)
    Optional<SnapshotMeta> findSnapshot(
            @Param("snapshotTs") Instant snapshotTs, @Param("source") String source);

    /**
     * 시각 미지정 시 기준 스냅샷. source 가 null 이면 최신 LIVE, 없으면 최신 replay.
     * source 가 지정되면 그 출처의 최신.
     */
    @Query(value = """
            SELECT snapshot_ts AS snapshotTs, source AS source,
                   score_version AS scoreVersion, new_window_hours AS newWindowHours
            FROM cluster_snapshot
            WHERE (CAST(:source AS text) IS NULL OR source = CAST(:source AS text))
            ORDER BY CASE WHEN source = 'live' THEN 0 ELSE 1 END, snapshot_ts DESC
            LIMIT 1
            """, nativeQuery = true)
    Optional<SnapshotMeta> findLatestSnapshot(@Param("source") String source);

    // ---- 그래프 벌크 조회 --------------------------------------------------

    /** 한 스냅샷의 클러스터. DISCARDED 제외. pulseScore desc, id asc. */
    @Query(value = """
            SELECT c.id AS id, c.issue_key AS issueKey, c.label AS label,
                   r.summary AS summary, c.category AS category,
                   c.first_detected_at AS firstDetectedAt, c.hot AS hot,
                   c.pulse_score AS pulseScore, c.status AS status,
                   (SELECT count(*) FROM cluster_member cm WHERE cm.cluster_id = c.id) AS memberCount
            FROM issue_cluster c
            LEFT JOIN issue_report r ON r.cluster_id = c.id
            WHERE c.snapshot_ts = :snapshotTs AND c.source = :source
              AND c.status <> 'DISCARDED'
            ORDER BY c.pulse_score DESC, c.id ASC
            """, nativeQuery = true)
    List<ClusterRow> findClusters(
            @Param("snapshotTs") Instant snapshotTs, @Param("source") String source);

    /** 한 스냅샷의 모든 노드(멤버). 고정 지표 그대로. DISCARDED 제외. */
    @Query(value = """
            SELECT c.id AS clusterId, p.id AS pageId, p.wiki AS wiki, p.title AS title,
                   p.title_ko AS titleKo, p.title_ko_fallback AS titleKoFallback,
                   cm.is_seed AS isSeed, cm.edit_count AS editCount, cm.views AS views,
                   cm.edit_baseline AS editBaseline, cm.view_baseline AS viewBaseline,
                   cm.spike_score AS spikeScore, cm.size_score AS sizeScore,
                   cm.completeness AS completeness,
                   cm.window_start AS windowStart, cm.window_end AS windowEnd
            FROM cluster_member cm
            JOIN issue_cluster c ON c.id = cm.cluster_id
            JOIN wiki_page p ON p.id = cm.page_id
            WHERE c.snapshot_ts = :snapshotTs AND c.source = :source
              AND c.status <> 'DISCARDED'
            ORDER BY c.id ASC, cm.is_seed DESC, cm.weight DESC
            """, nativeQuery = true)
    List<NodeRow> findNodes(
            @Param("snapshotTs") Instant snapshotTs, @Param("source") String source);

    /** 한 스냅샷의 모든 간선. DISCARDED 제외. */
    @Query(value = """
            SELECT e.id AS id, e.cluster_id AS clusterId,
                   e.source_page_id AS sourcePageId, e.target_page_id AS targetPageId,
                   e.kind AS kind, e.directed AS directed, e.weight AS weight,
                   e.evidence_label AS evidenceLabel, e.evidence_month AS evidenceMonth,
                   e.evidence_observed_at AS evidenceObservedAt
            FROM cluster_edge e
            JOIN issue_cluster c ON c.id = e.cluster_id
            WHERE c.snapshot_ts = :snapshotTs AND c.source = :source
              AND c.status <> 'DISCARDED'
            ORDER BY e.cluster_id ASC, e.id ASC
            """, nativeQuery = true)
    List<EdgeRow> findEdges(
            @Param("snapshotTs") Instant snapshotTs, @Param("source") String source);

    // ---- 프로젝션 ---------------------------------------------------------

    interface SnapshotMeta {
        Instant getSnapshotTs();
        String getSource();
        String getScoreVersion();
        double getNewWindowHours();
    }

    interface ClusterRow {
        Long getId();
        String getIssueKey();
        String getLabel();
        String getSummary();
        String getCategory();
        Instant getFirstDetectedAt();
        boolean getHot();
        double getPulseScore();
        String getStatus();
        long getMemberCount();
    }

    interface NodeRow {
        Long getClusterId();
        Long getPageId();
        String getWiki();
        String getTitle();
        String getTitleKo();
        String getTitleKoFallback();
        boolean getIsSeed();
        Integer getEditCount();
        Integer getViews();
        Double getEditBaseline();
        Double getViewBaseline();
        Double getSpikeScore();
        Double getSizeScore();
        String getCompleteness();
        Instant getWindowStart();
        Instant getWindowEnd();
    }

    interface EdgeRow {
        Long getId();
        Long getClusterId();
        Long getSourcePageId();
        Long getTargetPageId();
        String getKind();
        boolean getDirected();
        double getWeight();
        String getEvidenceLabel();
        String getEvidenceMonth();
        Instant getEvidenceObservedAt();
    }
}
