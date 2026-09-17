package io.wikipulse.backend.matching;

import java.util.List;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * 이슈 하나의 후보 종목을 LLM 으로 검증한다 (명세 §6.3 precision — WP-68).
 *
 * <p>-67 이 {@code cluster_stock} 에 verified=false·check_state='PENDING' 로 쌓은 후보를 tier
 * 순서로 하나씩 LLM 에 물어 확정한다. 통과분(check_state='DONE', verified=true)만 API 에 노출된다
 * ({@code IssueQueryRepository.findVerifiedStocks}).
 *
 * <h2>오케스트레이션 (명세 §6.3, WP-22 확정)</h2>
 * <ol>
 *   <li>tier 순서 BOTH → GDELT_ONLY → EMBEDDING_ONLY.</li>
 *   <li>EMBEDDING_ONLY(3등급)는 1·2등급 확정 통과가 N(=2) 미만일 때만 호출한다 — 돈 아낌.</li>
 * </ol>
 *
 * <h2>상태 전이 (-50)</h2>
 * <ul>
 *   <li>판정 성공(통과·탈락 둘 다) → check_state='DONE'. verified/match_path/confidence/rationale 저장.</li>
 *   <li>스키마 위반(정정 1회 실패) → attempt_count+1, 3 도달 시 FAILED.</li>
 *   <li>전송 실패({@link UpstreamUnavailableException}) → 후보 PENDING 유지, attempt 미증가, 예외 전파.</li>
 * </ul>
 * 전송 실패가 클러스터 중간에 나면 이미 판정한 후보는 커밋된 채 남고(멱등 재개), 예외는 워커로
 * 전파돼 다음 폴에서 나머지가 재시도된다.
 */
@Service
public class VerificationService {

    private static final Logger log = LoggerFactory.getLogger(VerificationService.class);

    private final VerificationRepository repository;
    private final ClusterIssueText issueText;
    private final LlmVerifier verifier;
    private final CandidateProperties props;

    public VerificationService(
            VerificationRepository repository,
            ClusterIssueText issueText,
            LlmVerifier verifier,
            CandidateProperties props) {
        this.repository = repository;
        this.issueText = issueText;
        this.verifier = verifier;
        this.props = props;
    }

    /**
     * 검증 결과 요약. 로그·측정용.
     *
     * <p>{@code reused} 는 LLM 을 부르지 않고 이전 판정을 복사한 후보 수(WP-69) — verified/
     * rejected 와 별개 버킷이다. verified/rejected 는 "이번 실행에서 LLM 이 새로 내린 판정" 의미를
     * 유지한다. 재사용률 = reused / (verified + rejected + schemaFailed + reused).
     */
    public record Result(
            long clusterId, int verified, int rejected, int schemaFailed, int tier3Skipped, int reused) {
    }

    /**
     * 클러스터 하나의 PENDING 후보를 검증한다.
     *
     * @throws UpstreamUnavailableException 전송 실패 시 — 이미 판정한 후보는 커밋되고 예외가 전파된다
     */
    public Result verifyCluster(long clusterId) {
        List<VerificationRepository.PendingCandidate> pending = repository.pendingCandidates(clusterId);
        if (pending.isEmpty()) {
            return new Result(clusterId, 0, 0, 0, 0, 0);
        }

        // 클러스터 단위 입력은 한 번만 만든다 — 후보마다 같은 이슈 텍스트·GDELT 컨텍스트를 공유한다.
        String text = issueText.build(repository.memberTitlesByPulse(clusterId));
        String gdelt = String.join(", ",
                repository.topOrgMentions(clusterId, props.getVerification().getOrgContextLimit()));
        String issueKey = repository.issueKeyOf(clusterId);

        int verified = 0;
        int rejected = 0;
        int schemaFailed = 0;
        int tier3Skipped = 0;
        int reused = 0;

        for (VerificationRepository.PendingCandidate c : pending) {
            // 재사용 캐시 (WP-69): 같은 (issue_key, ticker, prompt_version) 로 이미 DONE 인
            // 판정이 있으면 LLM 을 부르지 않고 그대로 복사한다. 🔴 tier3 게이트보다 앞이다 — 재사용은
            // LLM 0 이라 EMBEDDING_ONLY 라도 히트면 적용하는 게 결과가 완전해진다(게이트는 실 LLM
            // 호출만 막는다). issue_key 가 없는(V2 옛) 클러스터는 캐시를 못 써 아래로 내려간다.
            if (issueKey != null) {
                Optional<VerificationRepository.Verdict> prior =
                        repository.findPriorVerdict(clusterId, issueKey, c.ticker(), LlmVerifier.PROMPT_VERSION);
                if (prior.isPresent()) {
                    repository.recordReused(
                            clusterId, c.ticker(), prior.get(), issueKey, LlmVerifier.PROMPT_VERSION);
                    reused++;
                    log.debug("판정 재사용 cluster={} ticker={} verified={}",
                            clusterId, c.ticker(), prior.get().verified());
                    continue; // LLM 0. 재사용된 verified 행은 DB 에 DONE 으로 남아 게이트 카운트에 잡힌다.
                }
            }

            // 3등급 게이트: EMBEDDING_ONLY 는 1·2등급 확정 통과가 N 미만일 때만.
            if (c.tier() == CandidateTier.EMBEDDING_ONLY
                    && repository.verifiedPassCountTier12(clusterId)
                        >= props.getVerification().getTier3Threshold()) {
                tier3Skipped++;
                continue; // PENDING 유지 — 나중에 통과 수가 줄 일은 없으니 사실상 영구 스킵.
            }

            VerificationRepository.CandidateInfo info = repository.candidateInfo(c.ticker());
            LlmVerifier.Input input = new LlmVerifier.Input(
                    text, gdelt, info.name(), c.ticker(), info.summary());

            // 전송 실패는 여기서 잡지 않는다 — 예외가 워커로 전파돼 후보가 PENDING 으로 남는다.
            Optional<VerificationResponse> result = verifier.verify(input);
            if (result.isEmpty()) {
                repository.recordSchemaFailure(clusterId, c.ticker());
                schemaFailed++;
                continue;
            }
            VerificationResponse resp = result.get();
            repository.recordDone(clusterId, c.ticker(), resp, issueKey, LlmVerifier.PROMPT_VERSION);
            if (resp.verified()) {
                verified++;
                // 🔴 rationale_en 은 저장하지 않고 감사 로그로만 남긴다(화면용은 rationale_ko).
                log.debug("검증 통과 cluster={} ticker={} path={} confidence={} rationale_en={}",
                        clusterId, c.ticker(), resp.matchPath(), resp.confidence(), resp.rationaleEn());
            } else {
                rejected++;
            }
        }

        Result summary = new Result(clusterId, verified, rejected, schemaFailed, tier3Skipped, reused);
        log.info("검증 cluster={} 통과={} 탈락={} 스키마실패={} 3등급스킵={} 재사용={}",
                clusterId, verified, rejected, schemaFailed, tier3Skipped, reused);
        return summary;
    }
}
