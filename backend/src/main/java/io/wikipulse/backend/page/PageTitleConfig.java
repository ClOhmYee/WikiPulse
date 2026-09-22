package io.wikipulse.backend.page;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * 표시용 한국어 제목 모듈 설정.
 *
 * <p>🔴 {@code @EnableScheduling} 을 이 조건에도 걸어야 한다. 없으면
 * {@code page-title.enabled=true} 만 켠 서버에서 {@link PageTitleWorker} 빈은 뜨지만
 * {@code @Scheduled} 후처리기가 등록되지 않아 폴이 <b>조용히</b> 안 돈다 — 매칭 폴러를 함께
 * 켰을 때만 우연히 동작한다. {@code MatchingConfig.SummarySchedulingConfig} 주석이 기록한
 * 것과 같은 함정이다. 싱글턴 등록이라 여러 조건부 설정이 동시에 켜져도 한 번만 활성화된다.
 */
@Configuration
@EnableConfigurationProperties(PageTitleProperties.class)
public class PageTitleConfig {

    @Configuration
    @EnableScheduling
    @ConditionalOnProperty(prefix = "wikipulse.page-title", name = "enabled", havingValue = "true")
    static class PageTitleSchedulingConfig {
    }
}
