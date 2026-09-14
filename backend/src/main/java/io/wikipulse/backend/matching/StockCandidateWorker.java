package io.wikipulse.backend.matching;

import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 후보 생성 폴러 (WP-67). 후보가 아직 없는 클러스터를 주기적으로 집어 생성한다.
 *
 * <p>{@code wikipulse.matching.scheduler.enabled=true} 일 때만 뜬다 — 기본 꺼짐이라
 * CI·로컬에서 조용히 Wikipedia·GATEWAY 를 때리지 않는다. 클러스터 하나가 실패해도(도입부 조회·
 * GATEWAY 오류) 나머지는 계속 돌도록 개별로 감싼다.
 */
@Component
@ConditionalOnProperty(prefix = "wikipulse.matching.scheduler", name = "enabled", havingValue = "true")
public class StockCandidateWorker {

    private static final Logger log = LoggerFactory.getLogger(StockCandidateWorker.class);

    private final StockCandidateService service;
    private final CandidateRepository repository;
    private final CandidateProperties props;

    public StockCandidateWorker(
            StockCandidateService service,
            CandidateRepository repository,
            CandidateProperties props) {
        this.service = service;
        this.repository = repository;
        this.props = props;
    }

    @Scheduled(fixedDelayString = "${wikipulse.matching.scheduler.fixed-delay:PT5M}")
    public void pollAndGenerate() {
        List<Long> clusterIds = repository.pendingClusterIds(props.getScheduler().getBatchSize());
        if (clusterIds.isEmpty()) {
            return;
        }
        log.info("후보 생성 대상 클러스터 {}건", clusterIds.size());
        for (Long clusterId : clusterIds) {
            try {
                service.generateFor(clusterId);
            } catch (RuntimeException e) {
                log.error("후보 생성 실패 cluster={}, 건너뜀", clusterId, e);
            }
        }
    }
}
