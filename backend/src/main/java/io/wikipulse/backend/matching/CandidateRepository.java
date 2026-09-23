package io.wikipulse.backend.matching;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

/**
 * 후보 생성 워커의 DB 접근 (WP-67). 네이티브 SQL 이라 JdbcTemplate 을 쓴다 —
 * pgvector 연산자({@code <=>})와 upsert 는 JPA 로 표현하기 어색하다.
 *
 * <p>백엔드는 스키마를 소유하지 않는다(application.yml). 여기 SQL 은 db/migrations 의
 * cluster_stock·cluster_org_mention·cluster_member·issue_cluster·stock 을 그대로 읽고 쓴다.
 * 백엔드 테스트는 DB 없이 도는 웹 레이어 테스트뿐이라(다른 테스트 관습) 이 SQL 의 실 DB
 * 검증은 db/ pgserver 테스트 몫이다.
 */
@Repository
public class CandidateRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public CandidateRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /**
     * 후보가 아직 없는, 버려지지 않은 클러스터 id. 최근 스냅샷부터.
     * 재생성(갱신)은 {@code generateFor} 를 직접 불러서 한다 — 폴러는 신규만 집는다.
     *
     * <p>🔴 <b>{@code topPerSnapshot} 이 실제 비용 상한이다</b> (WP-176). 옛 조건은
     * {@code NOT EXISTS cluster_stock} 뿐이라 상한이 {@code batchSize} 하나였는데, 폴마다 대상을
     * 새로 고르므로 반복하면 미처리 클러스터 전체를 훑는다. 운영 4,474개를 다 돌면 후보마다
     * 검증이 따라붙어 310k~620k 크레딧이다. ⚠️ 후보 생성 자체는 임베딩이라 싸다 —
     * 이 상한이 묶는 것은 그 뒤의 <b>LLM 검증</b>이다.
     *
     * <p>순위는 <b>그 스냅샷의 전체 클러스터</b> 위에서 매긴다. 처리된 것을 뺀 나머지로 매기면
     * 처리할수록 하위가 올라와 상한이 조용히 아래로 번진다({@link IssueSummaryRepository
     * #clustersNeedingSummary} 와 같은 이유).
     *
     * <p>⚠️ 같은 {@code issue_key} 에 이미 {@code check_state='DONE'} 판정이 있으면 상한에서
     * <b>면제</b>한다 — 검증이 {@code (issue_key, ticker, prompt_version)} 으로 재사용하므로
     * LLM 호출이 0 이다. 면제하면 과거 스냅샷에도 종목이 붙어 시점 슬라이더가 완전해진다.
     *
     * <p>🔴 <b>요약 상한과 같은 축·같은 값을 쓴다.</b> 다르면 같은 화면에서 요약은 있는데
     * 종목이 없거나 그 반대가 생긴다.
     *
     * <p>{@code source} 는 대상을 한 출처로 좁힌다(WP-168). 정렬이
     * {@code snapshot_ts DESC} 라 폴러는 <b>가장 최근 스냅샷부터</b> 집는다 — LIVE 가 쌓이는
     * 동안에는 과거 replay 구간에 영원히 닿지 못한다. 특정 구간을 먼저 채우려면 이 값으로
     * 좁힌다. ⚠️ 비용 상한이 아니라 <b>대상 선택</b>이다. {@code topPerSnapshot} 과 함께 쓴다.
     *
     * <p>순위는 좁힌 출처 <b>안에서</b> 매긴다. 화면도 {@code source} 로 걸러 보여주므로
     * (`/api/v1/issues?source=`) 축을 맞춰야 "보여주는 상위 N" 과 대상이 일치한다. 밖에서
     * 매기면 다른 출처가 순위 자리를 먹어 상한보다 적게 뽑힌다.
     *
     * @param topPerSnapshot 스냅샷당 {@code pulse_score} 상위 몇 개까지. 0 이하면 무제한
     * <p>{@code snapshotDays} 는 대상을 그 UTC 날짜의 스냅샷으로 좁힌다(WP-215) —
     * 시연일만 채울 때. 날짜는 스냅샷 전체를 고르므로 스냅샷 안의 순위에는 영향이 없다.
     *
     * @param source {@code issue_cluster.source} 한정. {@code null}·빈 문자열이면 전체
     * @param snapshotDays 쉼표 구분 UTC 날짜. {@code null}·빈 문자열이면 전체
     */
    public List<Long> pendingClusterIds(int limit, int topPerSnapshot, String source,
                                        String snapshotDays) {
        return jdbc.queryForList("""
                WITH ranked AS (
                    SELECT id, status, issue_key, snapshot_ts,
                           row_number() OVER (PARTITION BY snapshot_ts
                                              ORDER BY pulse_score DESC, id ASC) AS rnk
                      FROM issue_cluster
                     WHERE (CAST(:source AS text) IS NULL
                            OR source = CAST(:source AS text))
                       AND (CAST(:days AS date[]) IS NULL
                            OR CAST(snapshot_ts AT TIME ZONE 'UTC' AS date)
                               = ANY (CAST(:days AS date[])))
                )
                SELECT r.id
                  FROM ranked r
                 WHERE r.status <> 'DISCARDED'
                   AND NOT EXISTS (SELECT 1 FROM cluster_stock cs WHERE cs.cluster_id = r.id)
                   AND (:top <= 0
                        OR r.rnk <= :top
                        OR EXISTS (SELECT 1
                                     FROM cluster_stock cs2
                                     JOIN issue_cluster c2 ON c2.id = cs2.cluster_id
                                    WHERE cs2.issue_key IS NOT NULL
                                      AND cs2.issue_key = r.issue_key
                                      AND cs2.check_state = 'DONE'
                                      AND c2.snapshot_ts <= r.snapshot_ts))
                 ORDER BY r.snapshot_ts DESC
                 LIMIT :limit
                """, new MapSqlParameterSource()
                .addValue("limit", limit)
                .addValue("top", topPerSnapshot)
                .addValue("source", blankToNull(source))
                .addValue("days", SnapshotDays.toSqlArray(snapshotDays)), Long.class);
    }

    /** 설정에서 온 빈 문자열을 "한정 없음"(NULL)으로 읽는다 — 미설정 환경변수가 빈 값이라서다. */
    private static String blankToNull(String source) {
        return source == null || source.isBlank() ? null : source;
    }

    // 멤버 제목 조회(memberTitlesByPulse)는 ClusterIntroRepository.context 로 옮겼다
    // (WP-129). 대표 텍스트를 만들려면 제목만으로는 부족하다 — 어느 시점의 도입부를
    // 쓸지가 클러스터의 source·snapshot_ts 에 달렸고, page_id 도 있어야 고정본을 찾는다.

    /**
     * 이슈 임베딩 ↔ 종목 임베딩 코사인 Top-K (명세 §6.3 a). 티커 → 코사인 유사도(1 - 거리).
     * 삽입 순서 = 유사도 내림차순을 유지한다. 임베딩이 없는 종목은 뺀다.
     */
    public Map<String, Double> embeddingTopK(float[] issueVector, int k) {
        var params = new MapSqlParameterSource()
                .addValue("vec", toVectorLiteral(issueVector))
                .addValue("k", k);
        Map<String, Double> out = new LinkedHashMap<>();
        jdbc.query("""
                SELECT s.ticker AS ticker,
                       1 - (s.embedding <=> CAST(:vec AS vector)) AS similarity
                  FROM stock s
                 WHERE s.embedding IS NOT NULL
                 ORDER BY s.embedding <=> CAST(:vec AS vector)
                 LIMIT :k
                """, params, rs -> {
            out.put(rs.getString("ticker"), rs.getDouble("similarity"));
        });
        return out;
    }

    /**
     * GDELT 동시 출현 lift 상위 Top-K (명세 §6.3 b). 티커 → lift.
     * 종목 마스터에 매칭된 것만(ticker NOT NULL). 별칭 여러 기관명이 한 티커면 최대 lift 로 접는다.
     */
    public Map<String, Double> gdeltTopK(long clusterId, int k) {
        var params = new MapSqlParameterSource()
                .addValue("cid", clusterId)
                .addValue("k", k);
        Map<String, Double> out = new LinkedHashMap<>();
        jdbc.query("""
                SELECT ticker, MAX(lift) AS lift
                  FROM cluster_org_mention
                 WHERE cluster_id = :cid AND ticker IS NOT NULL
                 GROUP BY ticker
                 ORDER BY MAX(lift) DESC
                 LIMIT :k
                """, params, rs -> {
            out.put(rs.getString("ticker"), rs.getDouble("lift"));
        });
        return out;
    }

    /**
     * 이 클러스터의 issue_key. 재사용 조회(WP-49)의 키다. 없으면(V1 이전 데이터) null —
     * 그 클러스터는 재사용 대상에서 자연히 빠진다(과거 판정을 찾을 수 없으므로 새로 검증).
     */
    private String issueKeyOf(long clusterId) {
        List<String> rows = jdbc.queryForList(
                "SELECT issue_key FROM issue_cluster WHERE id = :cid",
                new MapSqlParameterSource("cid", clusterId), String.class);
        return rows.isEmpty() ? null : rows.get(0);
    }

    /**
     * 후보를 cluster_stock 에 멱등 적재한다 (인수조건 4: verified=false, 재실행 갱신).
     *
     * <p>한 트랜잭션에서:
     * <ol>
     *   <li>이번 합집합에 없고 <b>아직 판정이 끝나지 않은(check_state &lt;&gt; DONE)</b> 후보를
     *       지운다 — 후보군이 좁아지면 낡은 행이 남지 않게. DONE 행(통과·탈락 둘 다)은 건드리지
     *       않는다 — LLM 검증 결과를 후보 재생성이 지우면 안 되고, 재사용 조회(-49)의 이력이기도
     *       하다.
     *   <li>각 후보를 upsert 한다. 충돌 시(같은 cluster_id 재실행) tier·similarity·gdelt_lift 만
     *       갱신하고 match_path·rationale·verified·verified_at·check_state 는 그대로 둔다
     *       (LLM 검증 단계 소유).
     *   <li>신규 행(이 cluster_id 에서 처음 보는 ticker)은 같은 issue_key 의 과거 스냅샷에
     *       DONE 판정이 있으면 그대로 들고 온다(WP-49) — {@code cluster_id} 는 스냅샷마다
     *       새로 생겨서(cluster/snapshot.py) 이 복사가 없으면 진행 중인 이슈가 재감지될 때마다
     *       LLM 을 다시 부른다. prompt_version 일치 여부는 검증 단계(WP-68)가 판단한다 —
     *       여기서는 대상 이하의 가장 가까운 스냅샷에 있는 DONE 을 들고 오고, 프롬프트가 올라
     *       재검증이 필요하면 검증 단계가 check_state 를 다시 PENDING 으로 돌린다. 미래 판정을
     *       과거 replay 로 역복사하지 않는다(WP-208).
     * </ol>
     *
     * @return 적재(삽입·갱신)한 후보 수
     */
    @Transactional
    public int replaceCandidates(long clusterId, List<StockCandidate> candidates) {
        if (candidates.isEmpty()) {
            jdbc.update("""
                    DELETE FROM cluster_stock
                     WHERE cluster_id = :cid AND check_state <> 'DONE'
                    """, new MapSqlParameterSource("cid", clusterId));
            return 0;
        }

        List<String> keep = candidates.stream().map(StockCandidate::ticker).toList();
        jdbc.update("""
                DELETE FROM cluster_stock
                 WHERE cluster_id = :cid AND check_state <> 'DONE' AND ticker NOT IN (:keep)
                """, new MapSqlParameterSource().addValue("cid", clusterId).addValue("keep", keep));

        String issueKey = issueKeyOf(clusterId);
        SqlParameterSource[] batch = candidates.stream()
                .map(c -> new MapSqlParameterSource()
                        .addValue("cid", clusterId)
                        .addValue("ticker", c.ticker())
                        .addValue("tier", c.tier().name())
                        .addValue("similarity", c.similarity())
                        .addValue("gdelt_lift", c.gdeltLift())
                        .addValue("issueKey", issueKey))
                .toArray(SqlParameterSource[]::new);

        // 신규 행만 prior(같은 issue_key·ticker 의 가장 최근 DONE 행)를 들고 온다. 이미 있는
        // 행(ON CONFLICT)은 재실행이라 prior 조회 결과를 무시하고 기존 검증 상태를 지킨다.
        jdbc.batchUpdate("""
                INSERT INTO cluster_stock
                    (cluster_id, ticker, tier, similarity, gdelt_lift, verified,
                     issue_key, prompt_version, check_state, attempt_count,
                     match_path, confidence, rationale, verified_at)
                SELECT :cid, :ticker, :tier, :similarity, :gdelt_lift,
                       COALESCE(prior.verified, false),
                       :issueKey,
                       prior.prompt_version,
                       COALESCE(prior.check_state, 'PENDING'),
                       COALESCE(prior.attempt_count, 0),
                       prior.match_path, prior.confidence, prior.rationale, prior.verified_at
                  FROM (SELECT 1) AS dual
                  LEFT JOIN (
                       SELECT cs.verified, cs.prompt_version, cs.check_state, cs.attempt_count,
                              cs.match_path, cs.confidence, cs.rationale, cs.verified_at
                         FROM cluster_stock cs
                         JOIN issue_cluster source_cluster ON source_cluster.id = cs.cluster_id
                         JOIN issue_cluster target_cluster ON target_cluster.id = :cid
                        WHERE cs.issue_key = CAST(:issueKey AS text)
                          AND cs.ticker = :ticker
                          AND cs.check_state = 'DONE'
                          AND cs.cluster_id <> :cid
                          AND source_cluster.snapshot_ts <= target_cluster.snapshot_ts
                        ORDER BY source_cluster.snapshot_ts DESC,
                                 cs.verified_at DESC NULLS LAST
                        LIMIT 1
                  ) AS prior ON true
                ON CONFLICT (cluster_id, ticker) DO UPDATE
                   SET tier = EXCLUDED.tier,
                       similarity = EXCLUDED.similarity,
                       gdelt_lift = EXCLUDED.gdelt_lift
                """, batch);
        return candidates.size();
    }

    /** float[] → pgvector 입력 리터럴 {@code [v1,v2,...]}. */
    static String toVectorLiteral(float[] vector) {
        StringBuilder sb = new StringBuilder(vector.length * 8 + 2);
        sb.append('[');
        for (int i = 0; i < vector.length; i++) {
            if (i > 0) {
                sb.append(',');
            }
            sb.append(vector[i]);
        }
        return sb.append(']').toString();
    }
}
