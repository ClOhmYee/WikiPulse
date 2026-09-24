package io.wikipulse.backend.issue;

import io.wikipulse.backend.issue.dto.IssueCardResponse;
import io.wikipulse.backend.issue.dto.IssueRankingsResponse;
import io.wikipulse.backend.issue.dto.IssueMemberResponse;
import io.wikipulse.backend.issue.dto.IssueReportResponse;
import io.wikipulse.backend.stock.dto.RelatedStockResponse;
import java.time.Instant;
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

    /** Peak per stable issue in the rolling window, linking to that exact snapshot. */
    @Query(value = """
            WITH ranked AS (
                SELECT c.id, c.label, c.pulse_score, c.snapshot_ts,
                       row_number() OVER (
                           PARTITION BY COALESCE(NULLIF(c.issue_key, ''), 'id:' || c.id)
                           ORDER BY c.pulse_score DESC, c.snapshot_ts DESC, c.id ASC
                       ) AS occurrence
                FROM issue_cluster c
                WHERE c.snapshot_ts >= :from AND c.snapshot_ts <= :asOf
                  AND c.status IN ('DETECTED', 'VERIFYING', 'CONFIRMED')
                  AND EXISTS (
                      SELECT 1 FROM cluster_snapshot s
                      WHERE s.source = c.source AND s.snapshot_ts = c.snapshot_ts
                  )
            )
            SELECT id, label, pulse_score AS pulseScore
            FROM ranked WHERE occurrence = 1
            ORDER BY pulse_score DESC, snapshot_ts DESC, id ASC
            LIMIT 10
            """, nativeQuery = true)
    List<IssueRankingsResponse.Projection> findRankings(
            @Param("from") Instant from,
            @Param("asOf") Instant asOf);

    /**
     * 이슈 상세의 멤버 문서. weight 내림차순. API 명세 §2.
     *
     * <p>🔴 <b>수치는 `cluster_member` 에 복사된 판정 당시 값이다</b> (WP-129 5번).
     * ~~최신 `page_edit_window`·`page_view_hourly` 한 행을 끌어온다~~ → 그러면 과거 스냅샷을
     * 열었을 때 <b>그 뒤에 들어온 수치</b>가 표시된다. 2025-06-12 09시 이슈에 오늘 조회수가
     * 붙는 식이다 — 값이 그럴듯해서 화면만 봐서는 틀린 줄 모른다.
     * 펄스맵({@link PulseMapRepository})은 이미 고정값을 읽고 있었다. 상세만 남아 있었다.
     *
     * <p>아직 안 채워졌으면 {@code null} 이다. ⚠️ 최신 원시 행으로 메우지 않는다 —
     * {@code completeness} 가 "판정 완료(complete) / 입력 대기(pending) / 원본 없음
     * (unavailable)" 를 구분한다(명세 §5.2).
     */
    @Query(value = """
            SELECT p.id AS pageId, p.wiki AS wiki, p.title AS title,
                   p.title_ko AS titleKo, p.title_ko_fallback AS titleKoFallback,
                   cm.weight AS weight, cm.is_seed AS isSeed,
                   cm.edit_count AS editCount, cm.views AS views,
                   cm.completeness AS completeness
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

    /** 섹션형 리포트 (V21, WP-223). 리포트가 없으면 빈 결과. */
    @Query(value = """
            SELECT report_sections::text AS sections, report_model AS model,
                   report_generated_at AS generatedAt
            FROM issue_report
            WHERE cluster_id = :clusterId AND report_sections IS NOT NULL
            """, nativeQuery = true)
    Optional<IssueReportResponse.Projection> findReport(@Param("clusterId") Long clusterId);

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
