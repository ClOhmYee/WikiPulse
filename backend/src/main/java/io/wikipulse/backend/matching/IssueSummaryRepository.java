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
     * 저장되지 못한 요약 시도를 원장에 남긴다 (WP-182, V11).
     *
     * <p>🔴 <b>이게 없으면 종료 조건이 없다.</b> 저장을 건너뛰면 {@link #hasReport} 가 계속
     * false 라 다음 폴에서 같은 클러스터가 또 집히고, LLM 은 매번 호출되고 결과는 매번
     * 버려진다. 2026-09-22 운영에서 51분간 5,414 크레딧이 이렇게 나갔다.
     *
     * <p>{@code model} 이 바뀌면(모델·프롬프트 버전 상향) 별개 시도로 보아 카운터를 1 로
     * 되돌린다 — 프롬프트를 고쳤는데 옛 실패 때문에 영영 안 집히면 고칠 방법이 없다.
     */
    public void recordFailedAttempt(long clusterId, String model, String state) {
        jdbc.update("""
                INSERT INTO issue_summary_attempt
                       (cluster_id, model, attempt_count, last_state, last_attempt_at)
                VALUES (:cid, :model, 1, :state, now())
                ON CONFLICT (cluster_id) DO UPDATE
                   SET attempt_count   = CASE WHEN issue_summary_attempt.model = EXCLUDED.model
                                              THEN issue_summary_attempt.attempt_count + 1
                                              ELSE 1 END,
                       model           = EXCLUDED.model,
                       last_state      = EXCLUDED.last_state,
                       last_attempt_at = EXCLUDED.last_attempt_at
                """, new MapSqlParameterSource()
                .addValue("cid", clusterId)
                .addValue("model", model)
                .addValue("state", state));
    }

    /**
     * 같은 issue_key 의 다른 스냅샷에서 이미 만든 요약을 찾는다 (WP-119 요약 재사용).
     * GATEWAY 재호출을 아끼려고 복사한다 — 🔴 행을 공유하지 않고 복사한다. 각 스냅샷(cluster_id)이
     * 자기 issue_report 행을 갖는다. 재사용 원본도 {@code source.snapshot_ts <= target.snapshot_ts}
     * 로 제한해, 과거를 나중에 재생할 때 미래 스냅샷 요약이 역복사되지 않게 한다
     * (WP-208, §3.2 8번 as-of).
     *
     * <p>허용된 원본이 여러 개면 대상 시점 이하의 가장 가까운 스냅샷을 고르고, 같은 시점 안에서는
     * {@code generated_at} 최신 1행을 쓴다. 현재 cluster_id 자신은 제외한다.
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
                  JOIN issue_cluster source_cluster ON source_cluster.id = r.cluster_id
                  JOIN issue_cluster target_cluster ON target_cluster.id = :cid
                 WHERE source_cluster.issue_key = :issueKey
                    AND r.cluster_id <> :cid
                    AND r.model = :model
                    AND source_cluster.snapshot_ts <= target_cluster.snapshot_ts
                 ORDER BY source_cluster.snapshot_ts DESC, r.generated_at DESC
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
     *
     * <p>🔴 <b>{@code topPerSnapshot} 이 실제 비용 상한이다</b> (WP-165). 옛 조건은
     * {@code status IN ('DETECTED','VERIFYING')} 뿐이라 상한이 batchSize 하나였는데, 폴마다
     * 대상을 새로 고르므로 반복하면 미처리 클러스터 전체를 훑는다. 운영 4,474건 전수 처리가
     * 약 277,000 크레딧이므로 실행 범위를 제한한다.
     *
     * <p>순위는 <b>그 스냅샷의 전체 클러스터</b> 위에서 매긴다. DETECTED·VERIFYING 만으로
     * 매기면 상위가 CONFIRMED 로 빠질 때마다 하위가 올라와 상한이 조용히 새어 나간다.
     *
     * <p>⚠️ <b>재사용 가능한 클러스터는 상한에서 면제한다.</b> 같은 issue_key·같은 model 의
     * 요약이 이미 있으면 {@link #findPriorSummary} 가 복사하므로 LLM 호출이 0 이다. 면제하면
     * 과거 스냅샷도 요약을 갖게 되어 시점 슬라이더에서 빈 요약이 사라진다 — 비용 증가 없이
     * 시점 정합성이 좋아진다.
     *
     * <p>{@code source} 는 대상을 한 출처로 좁힌다(WP-168). 정렬이 {@code id DESC} 라
     * 폴러는 <b>최근 생성분부터</b> 집는다 — LIVE 가 쌓이는 동안에는 과거 replay 구간에
     * 영원히 닿지 못한다. 특정 구간을 먼저 채우려면 이 값으로 좁힌다. 순위는 좁힌 출처
     * 안에서 매긴다({@link CandidateRepository#pendingClusterIds} 와 같은 이유 — 화면도
     * {@code source} 로 거른다).
     *
     * <p>🔴 <b>후보 생성 쪽과 같은 값이어야 한다.</b> 한쪽만 좁히면 같은 화면에서 요약은
     * 있는데 종목이 없거나 그 반대가 생긴다 — {@code topPerSnapshot} 과 같은 제약이다.
     *
     * @param topPerSnapshot 스냅샷당 {@code pulse_score} 상위 몇 개까지. 0 이하면 무제한
     * @param model {@code issue_report.model} 동등성으로 재사용 가능 여부를 본다
     * @param source {@code issue_cluster.source} 한정. {@code null}·빈 문자열이면 전체
     * @param maxAttempts 같은 model 로 이 횟수만큼 실패한 클러스터는 뺀다 (WP-182).
     *     🔴 이 제외가 없으면 저장 못 하는 클러스터를 매 폴 다시 집어 크레딧만 나간다 —
     *     {@code topPerSnapshot} 은 "몇 개를 고르나"라 이걸 못 막는다
     */
    public List<Long> clustersNeedingSummary(int limit, int topPerSnapshot, String model,
                                             String source, int maxAttempts) {
        return jdbc.queryForList("""
                WITH ranked AS (
                    SELECT id, status, issue_key, snapshot_ts,
                           row_number() OVER (PARTITION BY snapshot_ts
                                              ORDER BY pulse_score DESC, id ASC) AS rnk
                      FROM issue_cluster
                     WHERE CAST(:source AS text) IS NULL
                        OR source = CAST(:source AS text)
                )
                SELECT id
                  FROM ranked
                 WHERE status IN ('DETECTED', 'VERIFYING')
                   -- 🔴 시도 상한에 닿은 클러스터는 뺀다 (WP-182). 같은 model 일
                   --    때만 막는다 — 모델·프롬프트를 올리면 다시 집혀야 고칠 수 있다.
                   -- 🔴 :maxAttempts <= 0 이 "무제한"이다. 이 가드가 없으면
                   --    attempt_count >= 0 이 항상 참이라 시도 기록이 있는 클러스터가
                   --    **전부** 빠진다 — 의미가 정반대가 되는데 에러는 안 난다.
                   AND (:maxAttempts <= 0
                        OR NOT EXISTS (SELECT 1
                                         FROM issue_summary_attempt a
                                        WHERE a.cluster_id = ranked.id
                                          AND a.model = :model
                                          AND a.attempt_count >= :maxAttempts))
                   AND (:top <= 0
                        OR rnk <= :top
                        OR EXISTS (SELECT 1
                                     FROM issue_report r
                                     JOIN issue_cluster c2 ON c2.id = r.cluster_id
                                    WHERE c2.issue_key IS NOT NULL
                                      AND c2.issue_key = ranked.issue_key
                                      AND c2.snapshot_ts <= ranked.snapshot_ts
                                      AND r.model = :model))
                 ORDER BY id DESC
                 LIMIT :limit
                """, new MapSqlParameterSource()
                .addValue("limit", limit)
                .addValue("top", topPerSnapshot)
                .addValue("model", model)
                .addValue("maxAttempts", maxAttempts)
                .addValue("source", source == null || source.isBlank() ? null : source),
                Long.class);
    }
}
