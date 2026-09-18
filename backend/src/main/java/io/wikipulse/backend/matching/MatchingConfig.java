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

    /** 후보 생성 폴러가 켜질 때만 @Scheduled 가 동작하도록 스케줄링을 조건부로 켠다. */
    @Configuration
    @EnableScheduling
    @ConditionalOnProperty(prefix = "wikipulse.matching.scheduler", name = "enabled", havingValue = "true")
    static class SchedulingConfig {
    }

    /**
     * LLM 검증 폴러(-68)가 켜질 때도 스케줄링을 켠다 — 후보 생성 폴러와 독립으로 켤 수 있어야
     * 한다(검증만 돌리는 서버 구성). @EnableScheduling 은 후처리기를 싱글턴으로 등록하므로
     * 두 조건부 설정이 동시에 켜져도 중복 없이 한 번만 활성화된다.
     */
    @Configuration
    @EnableScheduling
    @ConditionalOnProperty(prefix = "wikipulse.matching.verification", name = "enabled", havingValue = "true")
    static class VerificationSchedulingConfig {
    }

    /**
     * 이슈 요약 writer 폴러(-119)가 켜질 때도 스케줄링을 켠다 — 위 둘과 독립으로 켤 수 있어야
     * 한다. 🔴 이 설정이 없으면 {@code summary.enabled=true} 만 켠 서버에서
     * {@link IssueSummaryWorker} 빈은 뜨지만 @Scheduled 후처리기가 등록되지 않아 폴이 조용히
     * 안 돈다(verification·scheduler 를 함께 켤 때만 우연히 동작). @EnableScheduling 싱글턴 등록이라
     * 셋이 동시에 켜져도 중복 없이 한 번만 활성화된다.
     */
    @Configuration
    @EnableScheduling
    @ConditionalOnProperty(prefix = "wikipulse.matching.summary", name = "enabled", havingValue = "true")
    static class SummarySchedulingConfig {
    }
}
