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
     */
    public List<Long> pendingClusterIds(int limit) {
        return jdbc.queryForList("""
                SELECT c.id
                  FROM issue_cluster c
                 WHERE c.status <> 'DISCARDED'
                   AND NOT EXISTS (SELECT 1 FROM cluster_stock cs WHERE cs.cluster_id = c.id)
                 ORDER BY c.snapshot_ts DESC
                 LIMIT :limit
                """, new MapSqlParameterSource("limit", limit), Long.class);
    }

    /**
     * 대표 텍스트용 멤버 제목. 급등도(cluster_member.spike_score) 내림차순 (명세 §6.2).
     * NULL 급등도는 뒤로, 동률은 엣지 가중치로 가른다.
     */
    public List<String> memberTitlesByPulse(long clusterId) {
        return jdbc.queryForList("""
                SELECT wp.title
                  FROM cluster_member cm
                  JOIN wiki_page wp ON wp.id = cm.page_id
                 WHERE cm.cluster_id = :cid
                 ORDER BY cm.spike_score DESC NULLS LAST, cm.weight DESC
                """, new MapSqlParameterSource("cid", clusterId), String.class);
    }

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
                 ORDER BY lift DESC
                 LIMIT :k
                """, params, rs -> {
            out.put(rs.getString("ticker"), rs.getDouble("lift"));
        });
        return out;
    }

    /**
     * 후보를 cluster_stock 에 멱등 적재한다 (인수조건 4: verified=false, 재실행 갱신).
     *
     * <p>한 트랜잭션에서:
     * <ol>
     *   <li>이번 합집합에 없는 <b>미검증</b> 후보를 지운다 — 후보군이 좁아지면 낡은 행이 남지 않게.
     *       검증된 행(verified=true)은 건드리지 않는다 — LLM 검증 결과를 후보 재생성이 지우면 안 된다.
     *   <li>각 후보를 upsert 한다. 충돌 시 tier·similarity·gdelt_lift 만 갱신하고
     *       match_path·rationale·verified·verified_at 은 그대로 둔다(LLM 검증 단계 소유).
     * </ol>
     *
     * @return 적재(삽입·갱신)한 후보 수
     */
    @Transactional
    public int replaceCandidates(long clusterId, List<StockCandidate> candidates) {
        if (candidates.isEmpty()) {
            jdbc.update("""
                    DELETE FROM cluster_stock
                     WHERE cluster_id = :cid AND verified = false
                    """, new MapSqlParameterSource("cid", clusterId));
            return 0;
        }

        List<String> keep = candidates.stream().map(StockCandidate::ticker).toList();
        jdbc.update("""
                DELETE FROM cluster_stock
                 WHERE cluster_id = :cid AND verified = false AND ticker NOT IN (:keep)
                """, new MapSqlParameterSource().addValue("cid", clusterId).addValue("keep", keep));

        SqlParameterSource[] batch = candidates.stream()
                .map(c -> new MapSqlParameterSource()
                        .addValue("cid", clusterId)
                        .addValue("ticker", c.ticker())
                        .addValue("tier", c.tier().name())
                        .addValue("similarity", c.similarity())
                        .addValue("gdelt_lift", c.gdeltLift()))
                .toArray(SqlParameterSource[]::new);

        jdbc.batchUpdate("""
                INSERT INTO cluster_stock (cluster_id, ticker, tier, similarity, gdelt_lift, verified)
                VALUES (:cid, :ticker, :tier, :similarity, :gdelt_lift, false)
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
