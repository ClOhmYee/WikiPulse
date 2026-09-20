package io.wikipulse.backend.matching;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import java.io.IOException;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceTransactionManagerAutoConfiguration;
import org.springframework.boot.autoconfigure.orm.jpa.HibernateJpaAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * LLM 검증 클라이언트가 -66 신뢰성 계층(named instance {@code gateway})에 실제로 얹혀 있는지
 * 확인한다 (WP-68). {@link ExternalCallResilienceTest} 와 같은 harness·FakeUpstream 을 쓴다.
 * 전송 계층만 본다 — 스키마 검증·정정은 {@link LlmVerifierTest}.
 */
@SpringBootTest(
        classes = GatewayVerificationClientTest.VerifyClientTestApp.class,
        properties = {
            "spring.main.banner-mode=off",
            "resilience4j.retry.instances.gateway.wait-duration=20ms",
            "resilience4j.ratelimiter.instances.gateway.limit-for-period=1000"
        })
class GatewayVerificationClientTest {

    /** Anthropic Messages 형태 OK 바디 — content[0].text 존재. */
    private static final String ANTHROPIC_OK =
            "{\"content\":[{\"type\":\"text\",\"text\":\"{\\\"verified\\\":false}\"}]}";

    private static FakeUpstream gateway;

    @DynamicPropertySource
    static void wireUpstream(DynamicPropertyRegistry registry) throws IOException {
        gateway = new FakeUpstream(ANTHROPIC_OK, 1500);
        registry.add("wikipulse.matching.gateway.base-url", () -> "http://127.0.0.1:" + gateway.port());
        registry.add("wikipulse.matching.gateway.api-key", () -> "test-key");
        registry.add("wikipulse.matching.gateway.connect-timeout", () -> "200ms");
        registry.add("wikipulse.matching.gateway.read-timeout", () -> "300ms");
    }

    @AfterAll
    static void stop() {
        if (gateway != null) {
            gateway.close();
        }
    }

    @Autowired
    GatewayVerificationClient client;
    @Autowired
    CircuitBreakerRegistry circuitBreakerRegistry;

    @BeforeEach
    void reset() {
        circuitBreakerRegistry.circuitBreaker("gateway").reset();
        gateway.resetCount();
    }

    private static final List<Map<String, String>> MSGS =
            List.of(Map.of("role", "user", "content", "hi"));

    @Test
    void 정상_200이면_content텍스트를_돌려준다() {
        gateway.mode(FakeUpstream.Mode.OK);
        assertThat(client.complete("system", MSGS)).contains("verified");
    }

    @Test
    void 프롬프트_캐싱을_쓰지_않는다() {
        // 🔴 회귀 고정 (WP-150). cache_control 을 붙이면 GATEWAY 에서 **쓰기만 되고 읽기가
        // 안 된다** — 4회 연속 실측 전부 write=1143 read=0. 캐시 쓰기는 입력 단가의 1.25배라
        // 켜면 25% 더 나간다(1,151 → 1,437). 상세는 클래스 주석·검증 문서.
        //
        // ⚠️ 조용히 틀린다: API 가 400 을 주지 않고 cache_creation_input_tokens 가 차올라
        // 로그만 보면 동작하는 것처럼 보인다. 그래서 요청 본문을 직접 본다.
        gateway.mode(FakeUpstream.Mode.OK);
        client.complete("긴 시스템 프롬프트", MSGS);

        String body = gateway.lastRequestBody();
        assertThat(body).doesNotContain("cache_control");
        assertThat(body).contains("긴 시스템 프롬프트");
    }

    @Test
    void 전이성_500은_재시도_후_UpstreamUnavailable로_정규화() {
        gateway.mode(FakeUpstream.Mode.STATUS_500);

        assertThatThrownBy(() -> client.complete("system", MSGS))
                .isInstanceOf(UpstreamUnavailableException.class);

        assertThat(gateway.requestCount()).isEqualTo(2); // max-attempts 2 (초기+재시도 1) — -66 gateway 재시도.
    }

    @Test
    void 하드_429는_재시도없이_UpstreamUnavailable() {
        gateway.mode(FakeUpstream.Mode.STATUS_429);

        assertThatThrownBy(() -> client.complete("system", MSGS))
                .isInstanceOf(UpstreamUnavailableException.class);

        // 🔴 GATEWAY 429 = 하드 → 재시도 0(공유 예산 보호). 임베딩과 같은 gateway 정책을 탄다.
        assertThat(gateway.requestCount()).isEqualTo(1);
    }

    @Test
    void 텍스트_없는_200은_스키마오류라_회로를_안_연다() {
        // -66/-68 경계: 200 인데 content[0].text 없음(크레딧 소진 바디)은 스키마 문제(-68 소관).
        gateway.mode(FakeUpstream.Mode.CREDIT_EXHAUSTED);

        for (int i = 0; i < 6; i++) {
            assertThatThrownBy(() -> client.complete("system", MSGS))
                    .isInstanceOf(IllegalStateException.class)
                    .hasMessageContaining("텍스트가 없다");
        }

        assertThat(gateway.requestCount()).isEqualTo(6); // 재시도 0.
        assertThat(circuitBreakerRegistry.circuitBreaker("gateway").getState())
                .isEqualTo(CircuitBreaker.State.CLOSED);
    }

    /** DB 자동설정 제외한 최소 컨텍스트 — 검증 클라이언트 + 설정 + resilience4j·AOP 자동설정. */
    @SpringBootConfiguration
    @EnableAutoConfiguration(exclude = {
        DataSourceAutoConfiguration.class,
        HibernateJpaAutoConfiguration.class,
        DataSourceTransactionManagerAutoConfiguration.class
    })
    @EnableConfigurationProperties(CandidateProperties.class)
    @Import(GatewayVerificationClient.class)
    static class VerifyClientTestApp {
    }
}
