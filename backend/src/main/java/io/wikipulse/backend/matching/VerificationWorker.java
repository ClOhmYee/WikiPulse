package io.wikipulse.backend.matching;

import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * LLM 검증 폴러 (WP-68). PENDING 후보가 있는 클러스터를 주기적으로 집어 검증한다.
 *
 * <p>{@code wikipulse.matching.verification.enabled=true} 일 때만 뜬다 — {@link StockCandidateWorker}
 * 와 같은 이유로 기본 꺼짐(CI·로컬에서 조용히 GATEWAY 를 때리지 않는다). 클러스터 하나가 전송 실패로
 * 터져도({@link UpstreamUnavailableException}) 나머지는 계속 돌도록 개별로 감싼다 — 실패한
 * 클러스터의 미판정 후보는 PENDING 으로 남아 다음 폴에서 재시도된다.
 *
 * <p>켜는 순서: 후보 생성(-67)이 PENDING 후보를 쌓은 뒤. 검증할 게 없으면 이 폴러는 아무것도
 * 안 한다. {@link VerificationService#verifyCluster} 는 항상 살아 있어 수동으로도 부를 수 있다.
 */
@Component
@ConditionalOnProperty(prefix = "wikipulse.matching.verification", name = "enabled", havingValue = "true")
public class VerificationWorker {

    private static final Logger log = LoggerFactory.getLogger(VerificationWorker.class);

    private final VerificationService service;
    private final VerificationRepository repository;
    private final CandidateProperties props;

    public VerificationWorker(
            VerificationService service,
            VerificationRepository repository,
            CandidateProperties props) {
        this.service = service;
        this.repository = repository;
        this.props = props;
    }

    @Scheduled(fixedDelayString = "${wikipulse.matching.verification.fixed-delay:PT5M}")
    public void pollAndVerify() {
        List<Long> clusterIds = repository.clustersWithPending(props.getVerification().getBatchSize());
        if (clusterIds.isEmpty()) {
            return;
        }
        log.info("검증 대상 클러스터 {}건", clusterIds.size());
        for (Long clusterId : clusterIds) {
            try {
                service.verifyCluster(clusterId);
            } catch (BudgetExceededException e) {
                // 🔴 전송 실패가 아니다 (WP-191). 판정한 후보는 커밋됐고 나머지는
                //    PENDING 으로 남아 다음 날 이어진다 — 상태로는 전송 실패와 같지만
                //    원인이 달라 로그에서 갈라 둔다.
                log.warn("검증 예산 소진 — 이번 폴을 여기서 멈춘다 ({}). 처리 {}/{}건",
                        e.getMessage(), clusterIds.indexOf(clusterId), clusterIds.size());
                return;
            } catch (RuntimeException e) {
                // 전송 실패·기타 런타임 오류. 판정한 후보는 커밋됐고 나머지는 PENDING 으로 남는다.
                log.error("검증 실패 cluster={}, 건너뜀", clusterId, e);
            }
        }
    }
}
