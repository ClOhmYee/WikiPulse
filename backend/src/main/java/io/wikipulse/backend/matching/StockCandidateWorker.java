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
 *
 * <p>🔴 <b>활성화 순서 계약</b>: 이 폴러는 종목 임베딩(WP-34)이 <b>전량</b> 적재된
 * 뒤에 켠다. 임베딩이 없거나 일부만 있으면 임베딩 경로가 빈/편향 결과를 내는데, 아래 "완료 판정"
 * 한계 때문에 그 상태가 굳을 수 있다.
 *
 * <p>⚠️ <b>알려진 한계 — 완료 판정이 암묵적이다</b>(cluster_stock 행 존재 = 완료).
 * 이 단일 신호로는 상반된 두 경우를 동시에 못 푼다: ① 후보가 진짜 0건인 클러스터는 행이 안
 * 생겨 매 폴 재선택된다(무한 재시도, 부트스트랩 구간에선 GATEWAY 재과금). ② 전이성 실패로 한
 * 경로만 채워진 클러스터가 "완료"로 굳는다. ①의 임베딩 경로는 텍스트가 비면 GATEWAY 호출 전
 * 스킵되고(과금 없음), ②의 위키 전이성 실패는 {@link WikipediaExtractClient} 가 예외를
 * 전파해 재시도되도록 이 커밋에서 완화했다. 그러나 근본 해소(시도 시각·경로별 상태 마커)는
 * 스키마 변경(db 마이그레이션)과 LLM 검증 단계(WP-68)의 상태 전이 협의가 필요해
 * 후속 이슈로 분리한다. 그전까지 재생성은 {@link StockCandidateService#generateFor}를 직접
 * 호출해 한다.
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
