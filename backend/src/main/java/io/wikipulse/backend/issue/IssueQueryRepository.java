package io.wikipulse.backend.issue;

import io.wikipulse.backend.issue.dto.IssueCardResponse;
import io.wikipulse.backend.issue.dto.IssueHistoryGroupResponse;
import io.wikipulse.backend.issue.dto.IssueHistoryReportResponse;
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

    /** 완료·비폐기 행을 source+issue_key 별로 묶고 최신 행을 대표로 택한다. */
    @Query(value = """
            WITH ranked AS (
                SELECT c.id, c.source, c.issue_key, c.label, c.status,
                       c.pulse_score, c.snapshot_ts,
                       min(c.snapshot_ts) OVER grouped AS first_seen,
                       count(*) OVER grouped AS occurrence_count,
                       row_number() OVER (
                           PARTITION BY c.source, nullif(c.issue_key, ''),
                                        CASE WHEN nullif(c.issue_key, '') IS NULL THEN c.id END
                           ORDER BY c.snapshot_ts DESC, c.id DESC
                       ) AS row_number
                FROM issue_cluster c
                WHERE c.status <> 'DISCARDED'
                  AND (CAST(:source AS text) IS NULL OR c.source = CAST(:source AS text))
                  AND EXISTS (SELECT 1 FROM cluster_snapshot s
                              WHERE s.source = c.source AND s.snapshot_ts = c.snapshot_ts)
                WINDOW grouped AS (PARTITION BY c.source, nullif(c.issue_key, ''),
                                   CASE WHEN nullif(c.issue_key, '') IS NULL THEN c.id END)
            ), named AS (
                SELECT r.*, coalesce(nullif(r.label, ''),
                         (SELECT p.title FROM cluster_member cm
                          JOIN wiki_page p ON p.id = cm.page_id
                          WHERE cm.cluster_id = r.id
                          ORDER BY cm.is_seed DESC, cm.weight DESC, p.id ASC LIMIT 1),
                         '제목 없음') AS display_label
                FROM ranked r WHERE r.row_number = 1
            ), page AS (
                SELECT * FROM named n
                WHERE (CAST(:pattern AS text) IS NULL
                       OR n.display_label ILIKE CAST(:pattern AS text) ESCAPE '!')
                  AND (CAST(:status AS text) IS NULL OR n.status = CAST(:status AS text))
                ORDER BY n.snapshot_ts DESC, n.id ASC
                OFFSET :offset LIMIT :limit
            )
            SELECT g.id AS id, g.display_label AS label, g.source AS source,
                   g.status AS status, g.pulse_score AS pulseScore,
                   g.snapshot_ts AS snapshotTs, g.first_seen AS firstSeen,
                   g.occurrence_count AS occurrenceCount,
                   (SELECT c2.id FROM issue_cluster c2
                    JOIN issue_report r2 ON r2.cluster_id = c2.id
                    WHERE c2.source = g.source AND c2.status <> 'DISCARDED'
                      AND ((nullif(g.issue_key, '') IS NOT NULL AND c2.issue_key = g.issue_key)
                           OR (nullif(g.issue_key, '') IS NULL AND c2.id = g.id))
                      AND EXISTS (SELECT 1 FROM cluster_snapshot s2
                                  WHERE s2.source = c2.source AND s2.snapshot_ts = c2.snapshot_ts)
                    ORDER BY CASE WHEN r2.report_sections IS NOT NULL
                                       AND jsonb_array_length(r2.report_sections) > 0
                                  THEN 0 ELSE 1 END,
                             c2.snapshot_ts DESC, c2.id DESC LIMIT 1) AS defaultReportId,
                   (SELECT r3.summary FROM issue_report r3 WHERE r3.cluster_id = g.id) AS summary,
                   (SELECT count(*) FROM cluster_member cm WHERE cm.cluster_id = g.id) AS memberCount,
                   (SELECT count(*) FROM cluster_stock cs
                    WHERE cs.cluster_id = g.id AND cs.verified) AS stockCount
            FROM page g
            ORDER BY g.snapshot_ts DESC, g.id ASC
            """, nativeQuery = true)
    List<IssueHistoryGroupResponse.Projection> findHistoryGroups(
            @Param("pattern") String pattern, @Param("status") String status,
            @Param("source") String source, @Param("offset") int offset,
            @Param("limit") int limit);

    @Query(value = """
            WITH latest AS (
                SELECT DISTINCT ON (c.source, nullif(c.issue_key, ''),
                                    CASE WHEN nullif(c.issue_key, '') IS NULL THEN c.id END)
                       c.id, c.label, c.status
                FROM issue_cluster c
                WHERE c.status <> 'DISCARDED'
                  AND (CAST(:source AS text) IS NULL OR c.source = CAST(:source AS text))
                  AND EXISTS (SELECT 1 FROM cluster_snapshot s
                              WHERE s.source = c.source AND s.snapshot_ts = c.snapshot_ts)
                ORDER BY c.source, nullif(c.issue_key, ''),
                         CASE WHEN nullif(c.issue_key, '') IS NULL THEN c.id END,
                         c.snapshot_ts DESC, c.id DESC
            ), named AS (
                SELECT l.*, coalesce(nullif(l.label, ''),
                         (SELECT p.title FROM cluster_member cm
                          JOIN wiki_page p ON p.id = cm.page_id
                          WHERE cm.cluster_id = l.id
                          ORDER BY cm.is_seed DESC, cm.weight DESC, p.id ASC LIMIT 1),
                         '제목 없음') AS display_label
                FROM latest l
            )
            SELECT count(*) FROM named n
            WHERE (CAST(:pattern AS text) IS NULL
                   OR n.display_label ILIKE CAST(:pattern AS text) ESCAPE '!')
              AND (CAST(:status AS text) IS NULL OR n.status = CAST(:status AS text))
            """, nativeQuery = true)
    long countHistoryGroups(@Param("pattern") String pattern,
                            @Param("status") String status, @Param("source") String source);

    /** 날짜는 프론트에서 KST로 묶는다. 여기서는 리포트 행의 원래 시각을 보존한다. */
    @Query(value = """
            SELECT c.id AS id, c.snapshot_ts AS snapshotTs, c.status AS status,
                   c.pulse_score AS pulseScore
            FROM issue_cluster c
            JOIN issue_report r ON r.cluster_id = c.id
            WHERE c.source = :source AND c.status <> 'DISCARDED'
              AND ((CAST(:issueKey AS text) IS NOT NULL AND c.issue_key = CAST(:issueKey AS text))
                   OR (CAST(:issueKey AS text) IS NULL AND c.id = :anchorId))
              AND EXISTS (SELECT 1 FROM cluster_snapshot s
                          WHERE s.source = c.source AND s.snapshot_ts = c.snapshot_ts)
            ORDER BY c.snapshot_ts DESC, c.id DESC
            OFFSET :offset LIMIT :limit
            """, nativeQuery = true)
    List<IssueHistoryReportResponse.Projection> findHistoryReports(
            @Param("anchorId") long anchorId, @Param("issueKey") String issueKey,
            @Param("source") String source, @Param("offset") int offset,
            @Param("limit") int limit);

    @Query(value = """
            SELECT count(*) FROM issue_cluster c
            JOIN issue_report r ON r.cluster_id = c.id
            WHERE c.source = :source AND c.status <> 'DISCARDED'
              AND ((CAST(:issueKey AS text) IS NOT NULL AND c.issue_key = CAST(:issueKey AS text))
                   OR (CAST(:issueKey AS text) IS NULL AND c.id = :anchorId))
              AND EXISTS (SELECT 1 FROM cluster_snapshot s
                          WHERE s.source = c.source AND s.snapshot_ts = c.snapshot_ts)
            """, nativeQuery = true)
    long countHistoryReports(@Param("anchorId") long anchorId,
                             @Param("issueKey") String issueKey,
                             @Param("source") String source);


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
