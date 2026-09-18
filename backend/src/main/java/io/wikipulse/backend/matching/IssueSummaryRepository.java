package io.wikipulse.backend.matching;

import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

/**
 * 이슈 요약 writer·라이프사이클 전이의 DB 접근 (WP-119). 네이티브 SQL —
 * issue_report·issue_cluster.status·cluster_stock 을 읽고 쓴다.
 *
 * <p>대표 텍스트 입력(멤버 제목·GDELT 기관명·issue_key)은 {@link VerificationRepository} 의 범용
 * 읽기를 재사용한다 — 요약과 검증이 같은 입력을 본다. 여기엔 요약 저장·상태 전이·재사용 조회만 둔다.
 *
 * <p>백엔드는 스키마를 소유하지 않는다. 이 SQL 의 실 DB 검증은 db/ pgserver 테스트 몫이다.
 */
@Repository
public class IssueSummaryRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public IssueSummaryRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /** 재사용할 이전 요약 (같은 issue_key 의 다른 스냅샷). */
    public record PriorSummary(String summary, String model) {
    }

    /** issue_cluster.status. 없으면 null. */
    public String statusOf(long clusterId) {
        List<String> rows = jdbc.queryForList(
                "SELECT status FROM issue_cluster WHERE id = :cid",
                new MapSqlParameterSource("cid", clusterId), String.class);
        return rows.isEmpty() ? null : rows.get(0);
    }

    /** issue_report 가 이미 있는지 (멱등 — 있으면 요약을 다시 만들지 않는다). */
    public boolean hasReport(long clusterId) {
        Integer n = jdbc.queryForObject(
                "SELECT count(*) FROM issue_report WHERE cluster_id = :cid",
                new MapSqlParameterSource("cid", clusterId), Integer.class);
        return n != null && n > 0;
    }

    /**
     * DETECTED → VERIFYING 전이. status='DETECTED' 일 때만 올린다(가드).
     * 🔴 이미 VERIFYING/CONFIRMED/DISCARDED 면 건드리지 않는다 — 상태를 되돌리지 않는다.
     *
     * @return 실제로 전이된 행 수(0 이면 이미 DETECTED 가 아니었다)
     */
    public int advanceToVerifying(long clusterId) {
        return jdbc.update("""
                UPDATE issue_cluster
                   SET status = 'VERIFYING'
                 WHERE id = :cid AND status = 'DETECTED'
                """, new MapSqlParameterSource("cid", clusterId));
    }

    /**
     * 이슈 요약 멱등 upsert (지라 인수 조건). cluster_id PK 충돌 시 요약·모델·생성시각을 갱신한다.
     * 🔴 model 을 기록해 나중에 품질 비교가 되게 한다(issue_report 테이블 주석).
     */
    public void upsertReport(long clusterId, String summary, String model) {
        jdbc.update("""
                INSERT INTO issue_report (cluster_id, summary, model, generated_at)
                VALUES (:cid, :summary, :model, now())
                ON CONFLICT (cluster_id) DO UPDATE
                   SET summary      = EXCLUDED.summary,
                       model        = EXCLUDED.model,
                       generated_at = EXCLUDED.generated_at
                """, new MapSqlParameterSource()
                .addValue("cid", clusterId)
                .addValue("summary", summary)
                .addValue("model", model));
    }

    /**
     * 같은 issue_key 의 다른 스냅샷에서 이미 만든 요약을 찾는다 (WP-119 요약 재사용).
     * GATEWAY 재호출을 아끼려고 복사한다 — 🔴 행을 공유하지 않고 복사한다. 각 스냅샷(cluster_id)이
     * 자기 issue_report 행을 가져 generated_at 이 그 스냅샷의 유효 시각이 되므로, 과거 조회가
     * 미래 요약을 소급 노출하지 않는다(§3.2 8번 as-of).
     *
     * <p>여러 스냅샷에 요약이 걸쳐 있으면 generated_at 최신 1행. 현재 cluster_id 자신은 제외한다.
     *
     * <p>🔴 {@code model} 이 일치하는 요약만 재사용한다 — model 문자열에 프롬프트 버전이 박혀 있어
     * (예: {@code "claude-... (summary_v1)"}), 프롬프트·모델을 올리면 이전 요약이 재사용되지 않고
     * 재생성된다. 검증 재사용이 prompt_version 컬럼으로 거는 것({@code VerificationRepository
     * .findPriorVerdict})과 같은 의도를, issue_report 에 별도 버전 컬럼 없이 model 동등성으로 이룬다.
     *
     * @return 재사용할 요약, 없으면 {@link Optional#empty()}
     */
    public Optional<PriorSummary> findPriorSummary(long clusterId, String issueKey, String model) {
        List<PriorSummary> rows = jdbc.query("""
                SELECT r.summary, r.model
                  FROM issue_report r
                  JOIN issue_cluster c ON c.id = r.cluster_id
                 WHERE c.issue_key = :issueKey
                   AND r.cluster_id <> :cid
                   AND r.model = :model
                 ORDER BY r.generated_at DESC
                 LIMIT 1
                """, new MapSqlParameterSource()
                .addValue("cid", clusterId)
                .addValue("issueKey", issueKey)
                .addValue("model", model),
                (rs, n) -> new PriorSummary(rs.getString("summary"), rs.getString("model")));
        return rows.isEmpty() ? Optional.empty() : Optional.of(rows.get(0));
    }

    /**
     * 종목 검증이 끝났는지 (CONFIRMED 게이트의 두 번째 조건).
     * 🔴 cluster_stock 행이 1개 이상이면서 check_state='PENDING' 이 0개일 때만 true.
     *
     * <p>빈 cluster_stock 은 "후보 생성(-67)이 아직 안 돎"으로 보아 false 다 — 장애·미도착을
     * 정상 0종목으로 오인해 조용히 확정하는 걸 막는다(§10 11번). PENDING 이 남아 있으면(전송 실패로
     * 재시도 대기, -50) 아직 검증 중이라 false. DONE(통과·탈락)·FAILED(파킹)만 남으면 완료다.
     */
    public boolean stockVerificationComplete(long clusterId) {
        // 🔴 한 쿼리로 total·pending 을 같은 스냅샷에서 읽는다(원자성 + 왕복 1회). autocommit 에서
        // 두 쿼리로 나누면 그 사이 삽입/삭제로 서로 다른 스냅샷을 볼 수 있다.
        return Boolean.TRUE.equals(jdbc.queryForObject("""
                SELECT count(*) > 0 AND count(*) FILTER (WHERE check_state = 'PENDING') = 0
                  FROM cluster_stock
                 WHERE cluster_id = :cid
                """, new MapSqlParameterSource("cid", clusterId), Boolean.class));
    }

    /**
     * VERIFYING → CONFIRMED 전이. status='VERIFYING' 일 때만 올린다(가드).
     * 🔴 호출자가 요약 완료 AND 종목 검증 완료를 확인한 뒤에만 부른다.
     *
     * @return 실제로 전이된 행 수
     */
    public int confirm(long clusterId) {
        return jdbc.update("""
                UPDATE issue_cluster
                   SET status = 'CONFIRMED'
                 WHERE id = :cid AND status = 'VERIFYING'
                """, new MapSqlParameterSource("cid", clusterId));
    }

    /**
     * 요약·상태 전이가 더 필요한 클러스터 id. DISCARDED·CONFIRMED 는 뺀다(이미 종착·폐기).
     * 최근 스냅샷부터. 워커 폴러가 대상 클러스터를 고를 때 쓴다.
     */
    public List<Long> clustersNeedingSummary(int limit) {
        return jdbc.queryForList("""
                SELECT id
                  FROM issue_cluster
                 WHERE status IN ('DETECTED', 'VERIFYING')
                 ORDER BY id DESC
                 LIMIT :limit
                """, new MapSqlParameterSource("limit", limit), Long.class);
    }
}
