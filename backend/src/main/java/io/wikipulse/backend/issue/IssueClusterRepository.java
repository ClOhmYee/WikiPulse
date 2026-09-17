package io.wikipulse.backend.issue;

import io.wikipulse.backend.issue.dto.IssueCardResponse;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface IssueClusterRepository extends JpaRepository<IssueCluster, Long> {

    /**
     * 시각 미지정 시 피드가 볼 기준 스냅샷. source 가 null 이면 최신 LIVE, LIVE 가
     * 없으면 최신 replay. source 가 주어지면 그 출처의 최신. 없으면 비어 있다.
     *
     * <p>🔴 규칙과 SQL 을 {@link PulseMapRepository#findLatestSnapshot} 와 똑같이 둔다 —
     * 피드(`/issues`)와 버블맵(`/issues/map`)은 같은 데이터를 카드/버블로만 다르게
     * 그리므로, 시각 미지정일 때 서로 다른 시점을 고르면 두 화면이 조용히 어긋난다.
     * ~~LIVE 전용 질의~~ → 최신 LIVE, 없으면 최신 replay (2026-09-17, WP-106).
     * 옛 질의는 replay 만 적재된 DB 에서 **에러 없이 빈 피드**를 냈다.
     *
     * <p>버블맵과 같이 `cluster_snapshot`(완료 스냅샷)을 본다. `issue_cluster` 의
     * max 를 보면 클러스터 0개인 완료 스냅샷이 후보에서 빠져, 두 endpoint 가 고르는
     * 시점이 다시 갈린다.
     */
    @Query(value = """
            SELECT snapshot_ts FROM cluster_snapshot
            WHERE (CAST(:source AS text) IS NULL OR source = CAST(:source AS text))
            ORDER BY CASE WHEN source = 'live' THEN 0 ELSE 1 END, snapshot_ts DESC
            LIMIT 1
            """, nativeQuery = true)
    Optional<Instant> findLatestSnapshot(@Param("source") String source);

    /**
     * 한 스냅샷의 이슈 카드. 정렬은 pulseScore desc, 동률 id asc (API 명세 §2).
     * status 는 쉼표 목록을 IN 으로. DISCARDED 는 호출자가 기본 목록에서 뺀다.
     * memberCount·stockCount 는 서브쿼리 집계 — 목록에서 상세 N번 호출 방지.
     * stockCount 는 verified=true 만 센다(§1.4 규칙).
     */
    @Query(value = """
            SELECT c.id AS id, c.label AS label, c.pulse_score AS pulseScore,
                   c.status AS status, c.source AS source, c.snapshot_ts AS snapshotTs,
                   (SELECT count(*) FROM cluster_member cm WHERE cm.cluster_id = c.id) AS memberCount,
                   (SELECT count(*) FROM cluster_stock cs WHERE cs.cluster_id = c.id AND cs.verified) AS stockCount
            FROM issue_cluster c
            WHERE c.snapshot_ts = :snapshotTs
              AND c.status IN (:statuses)
              AND (:source IS NULL OR c.source = :source)
            ORDER BY c.pulse_score DESC, c.id ASC
            OFFSET :offset LIMIT :limit
            """, nativeQuery = true)
    List<IssueCardResponse.Projection> findCards(
            @Param("snapshotTs") Instant snapshotTs,
            @Param("statuses") List<String> statuses,
            @Param("source") String source,
            @Param("offset") int offset,
            @Param("limit") int limit);

    /** 페이지네이션 total — 자르기 이전 조건 일치 개수. */
    @Query(value = """
            SELECT count(*) FROM issue_cluster c
            WHERE c.snapshot_ts = :snapshotTs
              AND c.status IN (:statuses)
              AND (:source IS NULL OR c.source = :source)
            """, nativeQuery = true)
    long countCards(
            @Param("snapshotTs") Instant snapshotTs,
            @Param("statuses") List<String> statuses,
            @Param("source") String source);
}
