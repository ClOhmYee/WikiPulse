package io.wikipulse.backend.matching;

import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * 이슈 요약 writer + 라이프사이클 전이 (WP-119). issue_cluster.status 를
 * DETECTED → VERIFYING → CONFIRMED 로 전이하고, 대표 텍스트 + GDELT 기관명으로 한국어 요약을
 * 생성·멱등 저장한다.
 *
 * <p>🔴 <b>이 서비스가 라이프사이클 전이를 owns 한다.</b> 파이프라인(-67 후보 생성 / -68 종목 검증)은
 * cluster_stock.check_state 만 다루고 issue_cluster.status 는 생성 시 DETECTED 로 박은 뒤 건드리지
 * 않는다(-119 조사 결론). 여기가 유일한 status 전이 지점이다.
 *
 * <h2>클러스터 하나의 처리 ({@link #processCluster})</h2>
 * <ol>
 *   <li>DISCARDED·CONFIRMED 는 종착 — 건너뛴다(멱등).</li>
 *   <li>DETECTED → VERIFYING (가드 UPDATE, 되돌리지 않음).</li>
 *   <li>issue_report 가 없으면: 같은 issue_key 의 다른 스냅샷 요약을 <b>복사</b>(재사용)하거나,
 *       없으면 LLM 으로 생성해 멱등 upsert. 근거 부족(sufficient_context=false)·스키마 실패면
 *       저장하지 않고 VERIFYING 으로 남는다.</li>
 *   <li>🔴 CONFIRMED 는 <b>요약 완료 AND 종목 검증 완료(cluster_stock PENDING 0)</b> 일 때만.
 *       통과 종목 0개도 둘 다 끝난 뒤엔 정상 0-종목 CONFIRMED 다(§10 11번).</li>
 * </ol>
 *
 * <p>전송 실패({@link UpstreamUnavailableException})는 잡지 않고 전파해 워커가 클러스터를 건너뛰고
 * VERIFYING 으로 남긴다(다음 폴 재시도). GATEWAY·GDELT 실패를 빈 정상 결과(CONFIRMED)로 만들지 않는다.
 *
 * <p>⚠️ <b>알려진 잔여 위험</b>: sufficient_context=false 나 스키마 실패가 <b>지속</b>되면 같은
 * 클러스터가 매 폴 요약을 재시도해 GATEWAY 를 반복 호출한다(요약 시도 카운터는 issue_report 스키마에
 * 없어 두지 않았다 — {@link GatewayVerificationClient} 의 200 무텍스트 잔여 위험과 같은 계약). 실제
 * 트리거는 좁다(위키피디아 도입부 대표 텍스트는 보통 충분하다). 근본 해소는 후속 스키마 작업.
 */
@Service
public class IssueSummaryService {

    private static final Logger log = LoggerFactory.getLogger(IssueSummaryService.class);

    private static final String STATUS_DISCARDED = "DISCARDED";
    private static final String STATUS_CONFIRMED = "CONFIRMED";
    private static final String STATUS_DETECTED = "DETECTED";

    private final IssueSummaryRepository repository;
    private final VerificationRepository verificationRepository;
    private final ClusterIssueText issueText;
    private final IssueSummarizer summarizer;
    private final CandidateProperties props;

    public IssueSummaryService(
            IssueSummaryRepository repository,
            VerificationRepository verificationRepository,
            ClusterIssueText issueText,
            IssueSummarizer summarizer,
            CandidateProperties props) {
        this.repository = repository;
        this.verificationRepository = verificationRepository;
        this.issueText = issueText;
        this.summarizer = summarizer;
        this.props = props;
    }

    /** 처리 결과 요약. 로그·측정용. */
    public record Result(long clusterId, boolean summarized, boolean reused, boolean confirmed) {

        static Result skipped(long clusterId) {
            return new Result(clusterId, false, false, false);
        }
    }

    /**
     * 클러스터 하나의 요약·상태 전이를 진행한다.
     *
     * <p>🔴 {@code @Transactional} 로 감싸지 않는다 — 단건 커밋이라 전송 실패가 중간에 나도 이미
     * 올린 상태·요약이 커밋된 채 남아 다음 폴에서 이어진다(-68 오케스트레이션과 같은 관습).
     *
     * @throws UpstreamUnavailableException 요약 전송 실패 시 — 상태는 VERIFYING 으로 남고 전파된다
     */
    public Result processCluster(long clusterId) {
        String status = repository.statusOf(clusterId);
        if (status == null || STATUS_DISCARDED.equals(status) || STATUS_CONFIRMED.equals(status)) {
            return Result.skipped(clusterId);
        }

        if (STATUS_DETECTED.equals(status)) {
            repository.advanceToVerifying(clusterId);
        }

        boolean summarized = false;
        boolean reused = false;
        boolean reportPresent = repository.hasReport(clusterId);
        if (!reportPresent) {
            EnsureResult ensured = ensureSummary(clusterId); // 전송 실패는 전파
            reportPresent = ensured.stored();
            summarized = ensured.stored() && !ensured.reused();
            reused = ensured.reused();
        }

        boolean confirmed = false;
        if (reportPresent && repository.stockVerificationComplete(clusterId)) {
            confirmed = repository.confirm(clusterId) > 0;
        }

        Result result = new Result(clusterId, summarized, reused, confirmed);
        log.info("요약 cluster={} 생성={} 재사용={} 확정={}",
                clusterId, summarized, reused, confirmed);
        return result;
    }

    private record EnsureResult(boolean stored, boolean reused) {
    }

    /** issue_report 를 채운다: 같은 issue_key 재사용 → 없으면 LLM 생성. 저장 못 하면 stored=false. */
    private EnsureResult ensureSummary(long clusterId) {
        String issueKey = verificationRepository.issueKeyOf(clusterId);
        String model = modelTag();

        // 재사용: 같은 issue_key + 같은 model(=모델·프롬프트버전)의 다른 스냅샷 요약을 복사한다(LLM 0).
        // issue_key 가 없는(V1 옛) 클러스터는 재사용을 못 써 아래 생성으로 내려간다.
        if (issueKey != null) {
            Optional<IssueSummaryRepository.PriorSummary> prior =
                    repository.findPriorSummary(clusterId, issueKey, model);
            if (prior.isPresent()) {
                repository.upsertReport(clusterId, prior.get().summary(), prior.get().model());
                log.debug("요약 재사용 cluster={} issueKey={}", clusterId, issueKey);
                return new EnsureResult(true, true);
            }
        }

        String text = issueText.build(verificationRepository.memberTitlesByPulse(clusterId));
        String gdelt = String.join(", ",
                verificationRepository.topOrgMentions(
                        clusterId, props.getVerification().getOrgContextLimit()));

        Optional<String> summary = summarizer.summarize(new IssueSummarizer.Input(text, gdelt));
        if (summary.isEmpty()) {
            // 근거 부족·스키마 실패 — 저장하지 않는다(거부/할루시네이션 저장 방지). VERIFYING 유지.
            return new EnsureResult(false, false);
        }
        repository.upsertReport(clusterId, summary.get(), model);
        return new EnsureResult(true, false);
    }

    /** issue_report.model 에 남길 모델 식별자. GATEWAY Anthropic 모델 + 프롬프트 버전. */
    private String modelTag() {
        return props.getGateway().getVerificationModel() + " (" + IssueSummarizer.PROMPT_VERSION + ")";
    }
}
