package io.wikipulse.backend.matching;

import java.util.List;
import java.util.Optional;
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
     * 재사용할 이전 판정 (WP-69). cluster_stock 에 저장된 판정 컬럼만 담는다 —
     * rationale 은 화면용 rationale_ko 다(rationale_en·issue_class 는 저장 안 돼 재사용 불가·불필요).
     */
    public record Verdict(boolean verified, String matchPath, String confidence, String rationale) {
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

    // 멤버 제목 조회는 ClusterIntroRepository.context 로 옮겼다 (WP-129) — 이유는
    // CandidateRepository 의 같은 자리 주석 참고.

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
     * 이전 판정 재사용 조회 (WP-69). 같은 (issue_key, ticker, prompt_version) 로 이미 DONE 인
     * 판정이 있으면 그걸 돌려준다 — LLM 을 다시 부르지 않고 복사해 쓴다(크레딧·지연 절약).
     *
     * <p>🔴 재사용 키는 cluster_id 가 아니다 — 진행 중인 이슈가 재감지될 때마다 새 cluster_id 가
     * 생겨 매번 캐시 미스한다(V6 마이그레이션 주석). issue_key 로 스냅샷을 가로질러 찾는다.
     * V6 부분 인덱스 {@code (issue_key, ticker, prompt_version) WHERE check_state='DONE'} 를 탄다.
     *
     * <p>여러 스냅샷에 DONE 이 걸쳐 있으면 대상 시점 이하의 가장 가까운 스냅샷을 고르고,
     * 같은 시점 안에서는 {@code verified_at} 최신 1행을 쓴다. 미래 판정을 과거 replay 로
     * 역복사하지 않는다(WP-208). 🔴 현재 처리 중인 cluster_id 행 자신은 세지 않는다
     * ({@code cluster_id <> :cid}) — PK 가 (cluster_id, ticker) 라 자기 행은
     * 하나뿐이고 지금 PENDING 이라 check_state='DONE' 필터로 이미 빠지지만, 의도를 명시한다.
     *
     * <p>⚠️ issue_cluster.status 로 재사용원을 거르지 않는다 — DISCARDED 스냅샷의 판정도 재사용한다.
     * 판정은 (issue_key, ticker) 관계에 대한 것이고 스냅샷 폐기는 그 관계를 부정하는 게 아니라
     * 스냅샷 하나를 버리는 것이라, 같은 이슈의 다른 스냅샷이 그 판정을 이어쓰는 게 맞다(status
     * 조인을 넣으면 index-only 조회가 깨지고 유효한 캐시 히트가 줄기만 한다).
     *
     * @return 재사용할 판정, 없으면 {@link java.util.Optional#empty()}
     */
    public Optional<Verdict> findPriorVerdict(
            long clusterId, String issueKey, String ticker, String promptVersion) {
        List<Verdict> rows = jdbc.query("""
                SELECT cs.verified, cs.match_path, cs.confidence, cs.rationale
                  FROM cluster_stock cs
                  JOIN issue_cluster source_cluster ON source_cluster.id = cs.cluster_id
                  JOIN issue_cluster target_cluster ON target_cluster.id = :cid
                 WHERE cs.issue_key = :issueKey AND cs.ticker = :ticker
                   AND cs.prompt_version = :promptVersion
                   AND cs.check_state = 'DONE'
                   AND cs.cluster_id <> :cid
                   AND source_cluster.snapshot_ts <= target_cluster.snapshot_ts
                 ORDER BY source_cluster.snapshot_ts DESC,
                          cs.verified_at DESC NULLS LAST
                 LIMIT 1
                """, new MapSqlParameterSource()
                .addValue("cid", clusterId)
                .addValue("issueKey", issueKey)
                .addValue("ticker", ticker)
                .addValue("promptVersion", promptVersion),
                (rs, n) -> new Verdict(
                        rs.getBoolean("verified"),
                        rs.getString("match_path"),
                        rs.getString("confidence"),
                        rs.getString("rationale")));
        return rows.isEmpty() ? Optional.empty() : Optional.of(rows.get(0));
    }

    /**
     * 재사용 판정 기록 (WP-69). {@link #recordDone} 과 같은 컬럼을 이전 판정({@link Verdict})
     * 값으로 채운다 — LLM 응답 없이. 이 (cluster_id, ticker) 행이 DONE+verified 로 남아
     * {@link #verifiedPassCountTier12} 에도 자연히 잡힌다.
     * rationale 컬럼엔 저장돼 있던 rationale_ko 를 그대로 넣는다.
     */
    public void recordReused(
            long clusterId, String ticker, Verdict verdict,
            String issueKey, String promptVersion) {
        jdbc.update("""
                UPDATE cluster_stock
                   SET check_state    = 'DONE',
                       verified       = :verified,
                       match_path     = :matchPath,
                       confidence     = :confidence,
                       rationale      = :rationale,
                       verified_at    = now(),
                       issue_key      = :issueKey,
                       prompt_version = :promptVersion
                 WHERE cluster_id = :cid AND ticker = :ticker
                """, new MapSqlParameterSource()
                .addValue("cid", clusterId)
                .addValue("ticker", ticker)
                .addValue("verified", verdict.verified())
                .addValue("matchPath", verdict.matchPath())
                .addValue("confidence", verdict.confidence())
                .addValue("rationale", verdict.rationale())
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
