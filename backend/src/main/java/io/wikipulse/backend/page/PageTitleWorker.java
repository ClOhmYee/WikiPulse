package io.wikipulse.backend.page;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * ko 제목 채우기 폴러.
 *
 * <p>🔴 {@code wikipulse.page-title.enabled=true} 일 때만 뜬다 — 매칭 폴러들과 같은 이유로
 * <b>기본 꺼짐</b>. 켜는 순간이 곧 백필 시작이다.
 *
 * <p>전송 실패로 폴이 터져도 다음 폴이 이어받는다. 실패한 청크는 {@code title_ko_checked_at} 이
 * NULL 로 남아 그대로 다시 집힌다 — 재시도 상태를 따로 들고 있지 않아도 되는 이유다.
 */
@Component
@ConditionalOnProperty(prefix = "wikipulse.page-title", name = "enabled", havingValue = "true")
public class PageTitleWorker {

    private static final Logger log = LoggerFactory.getLogger(PageTitleWorker.class);

    private final PageTitleService service;
    private final PageTitleProperties props;

    public PageTitleWorker(PageTitleService service, PageTitleProperties props) {
        this.service = service;
        this.props = props;
    }

    @Scheduled(fixedDelayString = "${wikipulse.page-title.fixed-delay:PT10M}")
    public void pollAndEnrich() {
        try {
            // 1단 langlinks + 2단 Azure 번역. 번역 실패는 서비스가 안에서 흡수한다.
            service.enrichAll(props.getBatchSize());
        } catch (RuntimeException e) {
            // 위키 전송 실패·기타 런타임 오류. 기록 안 된 문서는 미조회로 남아 다음 폴에서 재시도된다.
            log.error("ko 제목 조회 실패, 다음 폴에서 재시도", e);
        }
    }
}
