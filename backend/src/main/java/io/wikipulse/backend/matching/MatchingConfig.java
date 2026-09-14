package io.wikipulse.backend.matching;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * 매칭(후보 생성) 모듈 설정 (WP-67).
 *
 * <p>{@link CandidateProperties} 바인딩은 항상 켠다 — 클라이언트·서비스가 설정을 필요로 한다.
 * 스케줄링 인프라는 폴러가 켜질 때만 활성화한다({@code scheduler.enabled=true}).
 */
@Configuration
@EnableConfigurationProperties(CandidateProperties.class)
public class MatchingConfig {

    /** 폴러가 켜질 때만 @Scheduled 가 동작하도록 스케줄링을 조건부로 켠다. */
    @Configuration
    @EnableScheduling
    @ConditionalOnProperty(prefix = "wikipulse.matching.scheduler", name = "enabled", havingValue = "true")
    static class SchedulingConfig {
    }
}
