package io.wikipulse.backend.matching;

import java.util.List;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

/**
 * LLM 검증 워커의 DB 접근 (WP-68). 후보 생성(-67, {@link CandidateRepository})과 분리해
 * 검증 단계의 읽기/쓰기만 담는다. 네이티브 SQL — cluster_stock(V6)·cluster_org_mention·
 * issue_cluster·stock 을 그대로 읽고 쓴다.
 *
 * <p>백엔드는 스키마를 소유하지 않는다. 이 SQL 의 실 DB 검증은 db/ pgserver 테스트 몫이다
 * ({@link CandidateRepository} 와 같은 관습).
 */
@Repository
public class VerificationRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public VerificationRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /** 검증할 후보 한 건. tier 는 오케스트레이션 순서·3등급 게이트에 쓴다. */
    public record PendingCandidate(String ticker, CandidateTier tier) {
    }

    /** 후보 종목의 프롬프트 입력. business_summary 가 NULL 이면 빈 문자열. */
    public record CandidateInfo(String name, String summary) {
    }

    /**
     * 아직 검증 안 된(check_state='PENDING') 후보. tier 우선순위(BOTH→GDELT_ONLY→EMBEDDING_ONLY)
     * → tier 안 강한 신호순. FAILED·DONE 은 뺀다 — 다시 시도하지 않는다.
     */
    public List<PendingCandidate> pendingCandidates(long clusterId) {
        return jdbc.query("""
                SELECT ticker, tier
                  FROM cluster_stock
                 WHERE cluster_id = :cid AND check_state = 'PENDING'
                 ORDER BY CASE tier WHEN 'BOTH' THEN 0 WHEN 'GDELT_ONLY' THEN 1 ELSE 2 END,
                          coalesce(gdelt_lift, 0) DESC, coalesce(similarity, 0) DESC
                """, new MapSqlParameterSource("cid", clusterId),
                (rs, n) -> new PendingCandidate(
                        rs.getString("ticker"), CandidateTier.valueOf(rs.getString("tier"))));
    }

    /** 클러스터의 멤버 문서 제목. 급등도 내림차순 (명세 §6.2 순서, {@link CandidateRepository} 와 동일 조회). */
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
     * GDELT 동시 출현 상위 기관명 (lift 내림차순). LLM 검증 컨텍스트로 넘긴다 (명세 §11).
     * ⚠️ cluster_org_mention 에는 '테마' 컬럼이 없어 org_name 만 쓴다. ticker 매칭 여부와 무관하게
     * 상위 기관명을 준다 — 언론사·정부기관도 사건 맥락 신호다.
     */
    public List<String> topOrgMentions(long clusterId, int limit) {
        return jdbc.queryForList("""
                SELECT org_name
                  FROM cluster_org_mention
                 WHERE cluster_id = :cid
                 ORDER BY lift DESC
                 LIMIT :limit
                """, new MapSqlParameterSource().addValue("cid", clusterId).addValue("limit", limit),
                String.class);
    }

    /** 재사용 키로 쓸 issue_key (issue_cluster.issue_key, V2). NULL 가능. */
    public String issueKeyOf(long clusterId) {
        List<String> keys = jdbc.queryForList(
                "SELECT issue_key FROM issue_cluster WHERE id = :cid",
                new MapSqlParameterSource("cid", clusterId), String.class);
        return keys.isEmpty() ? null : keys.get(0);
    }

    /** 후보 종목의 이름·사업 설명 (stock 마스터). */
    public CandidateInfo candidateInfo(String ticker) {
        return jdbc.queryForObject("""
                SELECT name, coalesce(business_summary, '') AS summary
                  FROM stock
                 WHERE ticker = :ticker
                """, new MapSqlParameterSource("ticker", ticker),
                (rs, n) -> new CandidateInfo(rs.getString("name"), rs.getString("summary")));
    }

    /**
     * 1·2등급(BOTH·GDELT_ONLY) 확정 통과 수 — 3등급(EMBEDDING_ONLY) 발동 게이트(명세 §6.3, N=2).
     * check_state='DONE' 이고 verified=true 인 행만 센다. 이전 부분 실행분(재개)도 함께 집계된다.
     */
    public int verifiedPassCountTier12(long clusterId) {
        Integer count = jdbc.queryForObject("""
                SELECT count(*)
                  FROM cluster_stock
                 WHERE cluster_id = :cid AND check_state = 'DONE' AND verified = true
                   AND tier IN ('BOTH', 'GDELT_ONLY')
                """, new MapSqlParameterSource("cid", clusterId), Integer.class);
        return count == null ? 0 : count;
    }

    /**
     * 판정 완료 저장 (-50). check_state='DONE', verified/match_path/confidence/rationale 갱신.
     * 🔴 rationale 컬럼엔 rationale_ko(화면용)를 넣는다. 🔴 재사용 키(issue_key·prompt_version)도
     * 여기서 채운다(-67 은 안 채웠다 → -69 캐시-히트가 이 write 에 의존).
     * verified=false 면 match_path·confidence·rationale 이 null 로 저장된다(억지 연결 방지).
     */
    public void recordDone(
            long clusterId, String ticker, VerificationResponse resp,
            String issueKey, String promptVersion) {
        jdbc.update("""
                UPDATE cluster_stock
                   SET check_state    = 'DONE',
                       verified       = :verified,
                       match_path     = :matchPath,
                       confidence     = :confidence,
                       rationale      = :rationaleKo,
                       verified_at    = now(),
                       issue_key      = :issueKey,
                       prompt_version = :promptVersion
                 WHERE cluster_id = :cid AND ticker = :ticker
                """, new MapSqlParameterSource()
                .addValue("cid", clusterId)
                .addValue("ticker", ticker)
                .addValue("verified", resp.verified())
                .addValue("matchPath", resp.matchPath())
                .addValue("confidence", resp.confidence())
                .addValue("rationaleKo", resp.rationaleKo())
                .addValue("issueKey", issueKey)
                .addValue("promptVersion", promptVersion));
    }

    /**
     * 스키마 위반(정정 1회까지 실패) 기록 (-50). attempt_count+1, 3 도달 시 check_state='FAILED'.
     * PENDING 은 유지해 다음 폴에서 재시도하되, 3 도달분은 파킹해 무한 재시도·크레딧 몰림을 막는다.
     */
    public void recordSchemaFailure(long clusterId, String ticker) {
        jdbc.update("""
                UPDATE cluster_stock
                   SET attempt_count = attempt_count + 1,
                       check_state   = CASE WHEN attempt_count + 1 >= 3 THEN 'FAILED' ELSE check_state END
                 WHERE cluster_id = :cid AND ticker = :ticker
                """, new MapSqlParameterSource()
                .addValue("cid", clusterId)
                .addValue("ticker", ticker));
    }

    /**
     * 검증할 PENDING 후보가 있는, 버려지지 않은 클러스터 id. 최근 스냅샷부터.
     * 워커 폴러가 대상 클러스터를 고를 때 쓴다.
     */
    public List<Long> clustersWithPending(int limit) {
        return jdbc.queryForList("""
                SELECT DISTINCT c.id
                  FROM issue_cluster c
                  JOIN cluster_stock cs ON cs.cluster_id = c.id
                 WHERE c.status <> 'DISCARDED' AND cs.check_state = 'PENDING'
                 ORDER BY c.id DESC
                 LIMIT :limit
                """, new MapSqlParameterSource("limit", limit), Long.class);
    }
}
