package io.wikipulse.backend.issue;

import io.wikipulse.backend.issue.dto.IssueCardResponse;
import io.wikipulse.backend.issue.dto.IssueMemberResponse;
import io.wikipulse.backend.stock.dto.RelatedStockResponse;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/**
 * cluster_member · cluster_stock · issue_report 를 읽는 네이티브 프로젝션 모음.
 * 이 테이블들은 API 가 읽기만 하고 파이프라인이 쓴다. 리포지토리는 아무 엔티티나
 * 가리켜야 해서 IssueCluster 를 재사용한다 — CRUD 는 쓰지 않는다.
 */
public interface IssueQueryRepository extends JpaRepository<IssueCluster, Long> {

    /**
     * 이슈 상세의 멤버 문서. weight 내림차순. editCount·views 는 최근 윈도우/조회수
     * 에서 끌어온다 — 아직 없으면 null. API 명세 §2.
     */
    @Query(value = """
            SELECT p.id AS pageId, p.wiki AS wiki, p.title AS title,
                   cm.weight AS weight, cm.is_seed AS isSeed,
                   (SELECT ew.edit_count FROM page_edit_window ew
                     WHERE ew.page_id = p.id ORDER BY ew.window_start DESC LIMIT 1) AS editCount,
                   (SELECT pv.views FROM page_view_hourly pv
                     WHERE pv.page_id = p.id ORDER BY pv.ts_hour DESC LIMIT 1) AS views
            FROM cluster_member cm
            JOIN wiki_page p ON p.id = cm.page_id
            WHERE cm.cluster_id = :clusterId
            ORDER BY cm.is_seed DESC, cm.weight DESC
            """, nativeQuery = true)
    List<IssueMemberResponse.Projection> findMembers(@Param("clusterId") Long clusterId);

    @Query(value = "SELECT summary FROM issue_report WHERE cluster_id = :clusterId",
            nativeQuery = true)
    Optional<String> findSummary(@Param("clusterId") Long clusterId);

    @Query(value = "SELECT model FROM issue_report WHERE cluster_id = :clusterId",
            nativeQuery = true)
    Optional<String> findSummaryModel(@Param("clusterId") Long clusterId);

    /**
     * 한 이슈의 검증된 관련 종목. verified=true 만.
     * 정렬: tier(BOTH→GDELT_ONLY→EMBEDDING_ONLY) → gdeltLift → similarity (명세 §6.3).
     * limit 으로 자른다(상세는 5, 전체 endpoint 는 넉넉히).
     */
    @Query(value = """
            SELECT cs.ticker AS ticker, s.name AS name, s.exchange AS exchange,
                   s.sector AS sector, cs.tier AS tier, cs.match_path AS matchPath,
                   cs.similarity AS similarity, cs.gdelt_lift AS gdeltLift,
                   cs.rationale AS rationale
            FROM cluster_stock cs
            JOIN stock s ON s.ticker = cs.ticker
            WHERE cs.cluster_id = :clusterId AND cs.verified
            ORDER BY CASE cs.tier WHEN 'BOTH' THEN 0 WHEN 'GDELT_ONLY' THEN 1 ELSE 2 END,
                     coalesce(cs.gdelt_lift, 0) DESC, coalesce(cs.similarity, 0) DESC
            LIMIT :limit
            """, nativeQuery = true)
    List<RelatedStockResponse.Projection> findVerifiedStocks(
            @Param("clusterId") Long clusterId, @Param("limit") int limit);

    /**
     * 한 종목이 걸린 이슈 카드. verified=true 이고 DISCARDED 가 아닌 이슈만.
     * memberCount·stockCount 포함 — 종목 상세 화면이 이슈 카드로 그린다.
     */
    @Query(value = """
            SELECT c.id AS id, c.label AS label, c.pulse_score AS pulseScore,
                   c.status AS status, c.source AS source, c.snapshot_ts AS snapshotTs,
                   (SELECT count(*) FROM cluster_member cm WHERE cm.cluster_id = c.id) AS memberCount,
                   (SELECT count(*) FROM cluster_stock cs2 WHERE cs2.cluster_id = c.id AND cs2.verified) AS stockCount
            FROM cluster_stock cs
            JOIN issue_cluster c ON c.id = cs.cluster_id
            WHERE cs.ticker = :ticker AND cs.verified AND c.status <> 'DISCARDED'
            ORDER BY c.snapshot_ts DESC, c.pulse_score DESC
            LIMIT :limit
            """, nativeQuery = true)
    List<IssueCardResponse.Projection> findIssuesByTicker(
            @Param("ticker") String ticker, @Param("limit") int limit);
}
