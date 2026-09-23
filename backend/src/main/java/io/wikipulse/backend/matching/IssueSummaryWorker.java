package io.wikipulse.backend.matching;

import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 이슈 요약·상태 전이 폴러 (WP-119). DETECTED·VERIFYING 클러스터를 주기적으로 집어
 * {@link IssueSummaryService#processCluster} 를 돌린다.
 *
 * <p>🔴 {@code wikipulse.matching.summary.enabled=true} 일 때만 뜬다 — {@link VerificationWorker}·
 * {@link StockCandidateWorker} 와 같은 이유로 <b>기본 꺼짐</b>. 명시적으로 켜기 전 LLM 자동 호출 0
 * (자동 호출 비용 보호). 서버에서 LLM_GATEWAY_KEY 를 넣고 켠다.
 *
 * <p>클러스터 하나가 전송 실패로 터져도({@link UpstreamUnavailableException}) 나머지는 계속 돌도록
 * 개별로 감싼다 — 실패한 클러스터는 VERIFYING 으로 남아 다음 폴에서 재시도된다.
 *
 * <p>🔴 <b>비용 상한은 {@code batchSize} 가 아니라 {@code top-per-snapshot} 이다</b>
 * (WP-165). batchSize 는 한 폴의 크기일 뿐이라 폴을 반복하면 미처리 클러스터 전체를
 * 훑는다. 대상 선택 규칙은 {@link IssueSummaryRepository#clustersNeedingSummary} 참고.
 */
@Component
@ConditionalOnProperty(prefix = "wikipulse.matching.summary", name = "enabled", havingValue = "true")
public class IssueSummaryWorker {

    private static final Logger log = LoggerFactory.getLogger(IssueSummaryWorker.class);

    private final IssueSummaryService service;
    private final IssueSummaryRepository repository;
    private final CandidateProperties props;

    public IssueSummaryWorker(
            IssueSummaryService service,
            IssueSummaryRepository repository,
            CandidateProperties props) {
        this.service = service;
        this.repository = repository;
        this.props = props;
    }

    @Scheduled(fixedDelayString = "${wikipulse.matching.summary.fixed-delay:PT5M}")
    public void pollAndSummarize() {
        List<Long> clusterIds = repository.clustersNeedingSummary(
                props.getSummary().getBatchSize(),
                props.getSummary().getTopPerSnapshot(),
                service.modelTag(),
                props.getSummary().getSource(),
                props.getSummary().getSnapshotDays(),
                props.getSummary().getMaxAttempts());
        if (clusterIds.isEmpty()) {
            return;
        }
        log.info("요약 대상 클러스터 {}건", clusterIds.size());
        for (Long clusterId : clusterIds) {
            try {
                service.processCluster(clusterId);
            } catch (BudgetExceededException e) {
                // 🔴 전송 실패가 아니다 (WP-191). ERROR + 스택트레이스로 찍으면
                //    진짜 장애와 섞여 "왜 요약이 안 붙지" 를 뒤지게 된다.
                //    남은 클러스터도 같은 벽에 부딪히므로 루프를 끊는다.
                log.warn("요약 예산 소진 — 이번 폴을 여기서 멈춘다 ({}). 처리 {}/{}건",
                        e.getMessage(), clusterIds.indexOf(clusterId), clusterIds.size());
                return;
            } catch (RuntimeException e) {
                // 전송 실패·기타 런타임 오류. 이미 올린 상태·요약은 커밋됐고 클러스터는 VERIFYING 으로 남는다.
                log.error("요약 실패 cluster={}, 건너뜀", clusterId, e);
            }
        }
    }
}
