package io.wikipulse.backend.issue;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/**
 * cluster_member · cluster_stock · issue_report 를 읽는 네이티브 프로젝션 모음.
 *
 * <p>이 세 테이블은 API 가 읽기만 하고 파이프라인이 쓴다. JPA 엔티티를 각각 두는
 * 대신 프로젝션으로 바로 필요한 형태를 뽑는다. 리포지토리는 아무 엔티티나
 * 가리켜야 해서 IssueCluster 를 재사용한다 — CRUD 는 쓰지 않는다.
 */
public interface IssueQueryRepository extends JpaRepository<IssueCluster, Long> {

    /** 클러스터에 묶인 문서명. seed 문서를 먼저, 가중치 순으로. */
    @Query(value = """
            SELECT p.title
            FROM cluster_member cm
            JOIN wiki_page p ON p.id = cm.page_id
            WHERE cm.cluster_id = :clusterId
            ORDER BY cm.is_seed DESC, cm.weight DESC
            """, nativeQuery = true)
    List<String> findMemberTitles(@Param("clusterId") Long clusterId);

    @Query(value = "SELECT summary FROM issue_report WHERE cluster_id = :clusterId",
            nativeQuery = true)
    Optional<String> findSummary(@Param("clusterId") Long clusterId);

    /** 한 이슈의 검증된 관련 종목. gdelt_lift·similarity 순. */
    @Query(value = """
            SELECT cs.ticker AS ticker,
                   s.name AS name,
                   s.exchange AS exchange,
                   cs.tier AS tier,
                   cs.match_path AS matchPath,
                   cs.similarity AS similarity,
                   cs.gdelt_lift AS gdeltLift,
                   cs.rationale AS rationale
            FROM cluster_stock cs
            JOIN stock s ON s.ticker = cs.ticker
            WHERE cs.cluster_id = :clusterId AND cs.verified
            ORDER BY coalesce(cs.gdelt_lift, 0) DESC, coalesce(cs.similarity, 0) DESC
            """, nativeQuery = true)
    List<RelatedStockProjection> findVerifiedStocks(@Param("clusterId") Long clusterId);

    /** 한 종목이 걸린 최근 확정 이슈. 종목 상세 화면용. */
    @Query(value = """
            SELECT c.id AS id,
                   c.label AS label,
                   c.pulse_score AS pulseScore,
                   c.status AS status,
                   c.snapshot_ts AS snapshotTs
            FROM cluster_stock cs
            JOIN issue_cluster c ON c.id = cs.cluster_id
            WHERE cs.ticker = :ticker AND cs.verified AND c.status = 'CONFIRMED'
            ORDER BY c.snapshot_ts DESC, c.pulse_score DESC
            LIMIT :limit
            """, nativeQuery = true)
    List<IssueCardProjection> findIssuesByTicker(
            @Param("ticker") String ticker, @Param("limit") int limit);

    interface RelatedStockProjection {
        String getTicker();
        String getName();
        String getExchange();
        String getTier();
        String getMatchPath();
        Double getSimilarity();
        Double getGdeltLift();
        String getRationale();
    }

    interface IssueCardProjection {
        Long getId();
        String getLabel();
        double getPulseScore();
        String getStatus();
        Instant getSnapshotTs();
    }
}
