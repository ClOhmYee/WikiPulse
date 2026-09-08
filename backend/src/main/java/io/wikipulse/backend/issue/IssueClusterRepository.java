package io.wikipulse.backend.issue;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Limit;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface IssueClusterRepository extends JpaRepository<IssueCluster, Long> {

    /**
     * 가장 최근 스냅샷 시각. LIVE 피드·버블맵의 기준점이다.
     * 아직 클러스터가 하나도 없으면 비어 있다.
     */
    @Query("SELECT max(c.snapshotTs) FROM IssueCluster c WHERE c.source = 'live'")
    Optional<Instant> findLatestLiveSnapshot();

    /**
     * 한 스냅샷의 클러스터를 급등도 순으로. status 로 거를 수 있다(null 이면 전부).
     * 피드와 버블맵이 같은 질의를 쓴다 — 피드는 카드, 버블맵은 버블로 그릴 뿐이다.
     */
    @Query("""
            SELECT c FROM IssueCluster c
            WHERE c.snapshotTs = :snapshotTs
              AND (:status IS NULL OR c.status = :status)
            ORDER BY c.pulseScore DESC
            """)
    List<IssueCluster> findBySnapshot(
            @Param("snapshotTs") Instant snapshotTs,
            @Param("status") String status,
            Limit limit);
}
