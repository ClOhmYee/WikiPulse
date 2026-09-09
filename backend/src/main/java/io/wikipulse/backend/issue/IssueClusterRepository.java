package io.wikipulse.backend.issue;

import io.wikipulse.backend.issue.dto.IssueCardResponse;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface IssueClusterRepository extends JpaRepository<IssueCluster, Long> {

    /** 가장 최근 스냅샷 시각. LIVE 피드·버블맵의 기준점. 없으면 비어 있다. */
    @Query("SELECT max(c.snapshotTs) FROM IssueCluster c WHERE c.source = 'live'")
    Optional<Instant> findLatestLiveSnapshot();

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
