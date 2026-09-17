package io.wikipulse.backend.matching;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import java.io.IOException;
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
 * AFTER 검증 (WP-66). Spring 컨텍스트에서 resilience4j 애스펙트를 실제로 발동시켜
 * {@link GatewayEmbeddingClient} 의 재시도·서킷브레이커·폴백을 {@link FakeUpstream} 주입으로 확인한다.
 * before({@link ExternalCallBeforeCharacterizationTest}, 순수 new·AOP 없음)와 같은 harness 를 쓴다.
 *
 * <p>DB 자동설정은 제외한다 — 이 테스트는 전송 계층만 본다. CI 축약 타임아웃(connect 200ms/
 * read 300ms)·CB 창 4·재시도 20ms 로 빠르게 결정적으로 돌린다.
 */
@SpringBootTest(
        classes = ExternalCallResilienceTest.ResilienceTestApp.class,
        properties = {
            "spring.main.banner-mode=off",
            "resilience4j.retry.instances.gateway.wait-duration=20ms",
            "resilience4j.retry.instances.wikipedia.wait-duration=20ms",
            "resilience4j.circuitbreaker.instances.gateway.sliding-window-size=4",
            "resilience4j.circuitbreaker.instances.gateway.minimum-number-of-calls=4",
            "resilience4j.circuitbreaker.instances.gateway.wait-duration-in-open-state=60s",
            // RL 은 이 클래스의 관심사가 아니다(RL 캡은 GatewayRateLimiterTest 담당). 높게 잡아 재시도·CB
            // 테스트가 누적 호출로 RL 에 걸리는 결합을 제거한다.
            "resilience4j.ratelimiter.instances.gateway.limit-for-period=1000",
            "resilience4j.ratelimiter.instances.wikipedia.limit-for-period=1000"
        })
class ExternalCallResilienceTest {

    private static final long HANG_MILLIS = 1500;
    private static FakeUpstream gateway;
    private static FakeUpstream wiki;

    @DynamicPropertySource
    static void wireUpstreams(DynamicPropertyRegistry registry) throws IOException {
        gateway = new FakeUpstream(FakeUpstream.GATEWAY_OK_BODY, HANG_MILLIS);
        wiki = new FakeUpstream(FakeUpstream.WIKI_OK_BODY, HANG_MILLIS);
        registry.add("wikipulse.matching.gateway.base-url", () -> "http://127.0.0.1:" + gateway.port());
        registry.add("wikipulse.matching.gateway.api-key", () -> "test-key");
        registry.add("wikipulse.matching.gateway.connect-timeout", () -> "200ms");
        registry.add("wikipulse.matching.gateway.read-timeout", () -> "300ms");
        registry.add("wikipulse.matching.wikipedia.api-url", () -> "http://127.0.0.1:" + wiki.port() + "/w/api.php");
        registry.add("wikipulse.matching.wikipedia.connect-timeout", () -> "200ms");
        registry.add("wikipulse.matching.wikipedia.read-timeout", () -> "300ms");
    }

    @AfterAll
    static void stopUpstreams() {
        if (gateway != null) {
            gateway.close();
        }
        if (wiki != null) {
            wiki.close();
        }
    }

    @Autowired
    GatewayEmbeddingClient gatewayClient;
    @Autowired
    WikipediaExtractClient wikiClient;
    @Autowired
    CircuitBreakerRegistry circuitBreakerRegistry;

    @BeforeEach
    void reset() {
        // 메서드 간 CB 상태 누수 방지. RL 은 위 properties 에서 높게 잡아 결합을 제거했다(리셋 API 없음).
        circuitBreakerRegistry.circuitBreaker("gateway").reset();
        circuitBreakerRegistry.circuitBreaker("wikipedia").reset();
        gateway.resetCount();
        wiki.resetCount();
    }

    @Test
    void 전이성_500은_재시도_후_폴백신호() {
        gateway.mode(FakeUpstream.Mode.STATUS_500);

        assertThatThrownBy(() -> gatewayClient.embed("x"))
                .isInstanceOf(UpstreamUnavailableException.class); // 🔴 가짜 벡터 아님

        // max-attempts 2 → 업스트림 정확히 2회(초기+재시도 1).
        System.out.printf("[AFTER][retry 500] gateway호출=%d%n", gateway.requestCount());
        assertThat(gateway.requestCount()).isEqualTo(2);
    }

    @Test
    void 하드_429는_재시도없이_폴백신호() {
        gateway.mode(FakeUpstream.Mode.STATUS_429);

        assertThatThrownBy(() -> gatewayClient.embed("x"))
                .isInstanceOf(UpstreamUnavailableException.class);

        // 🔴 GATEWAY 429 = 하드 → 재시도 0 → 업스트림 1회. 죽은 예산에 재시도를 얹지 않는다.
        System.out.printf("[AFTER][hard 429] gateway호출=%d%n", gateway.requestCount());
        assertThat(gateway.requestCount()).isEqualTo(1);
    }

    @Test
    void 회로가_열리면_죽은GATEWAY를_더_안_두들긴다() {
        gateway.mode(FakeUpstream.Mode.STATUS_500);

        int countAfterOpen = -1;
        for (int i = 0; i < 6; i++) {
            try {
                gatewayClient.embed("x");
            } catch (RuntimeException expected) {
                // 전이성 소진 또는 회로 개방 → UpstreamUnavailableException.
            }
            if (circuitBreakerRegistry.circuitBreaker("gateway").getState() == CircuitBreaker.State.OPEN
                    && countAfterOpen < 0) {
                countAfterOpen = gateway.requestCount(); // 개방 직후 업스트림 호출 수를 고정.
            }
        }

        // 개방 후로는 업스트림 호출이 늘지 않아야 한다(빠른 실패). window 4 → 2 embed(=4시도)에 개방.
        System.out.printf("[AFTER][CB open] 개방시점호출=%d 최종호출=%d state=%s%n",
                countAfterOpen, gateway.requestCount(),
                circuitBreakerRegistry.circuitBreaker("gateway").getState());
        assertThat(circuitBreakerRegistry.circuitBreaker("gateway").getState())
                .isEqualTo(CircuitBreaker.State.OPEN);
        assertThat(gateway.requestCount()).isEqualTo(countAfterOpen).isLessThanOrEqualTo(4);
    }

    @Test
    void hang_반복시_회로개방후_스레드가_안_언다() {
        gateway.mode(FakeUpstream.Mode.HANG);

        // 개방 전: read 타임아웃(300ms)까지 블록되며 창을 채운다.
        for (int i = 0; i < 3; i++) {
            try {
                gatewayClient.embed("x");
            } catch (RuntimeException expected) {
                // hang → SocketTimeout → 전이성 → 재시도 → 소진 → UpstreamUnavailableException.
            }
        }
        assertThat(circuitBreakerRegistry.circuitBreaker("gateway").getState())
                .isEqualTo(CircuitBreaker.State.OPEN);

        // 개방 후: 소켓을 기다리지 않고 즉시 실패해야 한다(스레드 프리즈 해소).
        long start = System.nanoTime();
        assertThatThrownBy(() -> gatewayClient.embed("x"))
                .isInstanceOf(UpstreamUnavailableException.class);
        long elapsedMs = (System.nanoTime() - start) / 1_000_000;

        System.out.printf("[AFTER][hang→open] 개방후 embed elapsedMs=%d (read타임아웃 300ms 대비)%n", elapsedMs);
        assertThat(elapsedMs).isLessThan(100); // read 타임아웃보다 훨씬 짧게 = 안 언다.
    }

    @Test
    void 스키마오류_200무벡터는_전송실패가_아니라_회로를_안_연다() {
        // 🔴 -66/-68 경계 가드: 200 인데 벡터 없음(크레딧 소진 바디 등)은 스키마 문제(-68 소관).
        // 폴백이 IllegalStateException 을 원형 rethrow 하고(UpstreamUnavailableException 로 안 감쌈),
        // record-exceptions 가 UpstreamTransportException 뿐이라 회로에 안 세어져 CB 가 안 열린다.
        gateway.mode(FakeUpstream.Mode.CREDIT_EXHAUSTED);

        for (int i = 0; i < 6; i++) {
            assertThatThrownBy(() -> gatewayClient.embed("x"))
                    .isInstanceOf(IllegalStateException.class) // UpstreamUnavailableException 아님
                    .hasMessageContaining("벡터가 없다");
        }

        // 스키마 실패는 재시도 대상도 회로 기록 대상도 아님 → 호출 6회(재시도 0)·회로 CLOSED 유지.
        System.out.printf("[AFTER][schema 200-novec] gateway호출=%d state=%s%n",
                gateway.requestCount(), circuitBreakerRegistry.circuitBreaker("gateway").getState());
        assertThat(gateway.requestCount()).isEqualTo(6);
        assertThat(circuitBreakerRegistry.circuitBreaker("gateway").getState())
                .isEqualTo(CircuitBreaker.State.CLOSED);
    }

    @Test
    void wikipedia_전이성_500도_재시도_후_폴백신호() {
        // Wikipedia 게이트웨이도 같은 골격이 발동하는지(별도 named instance). 위키는 크레딧 무관이라
        // 429 도 전이성이지만 여기선 5xx 로 재시도 경로만 확인한다.
        wiki.mode(FakeUpstream.Mode.STATUS_500);

        assertThatThrownBy(() -> wikiClient.intro("Iran"))
                .isInstanceOf(UpstreamUnavailableException.class);

        System.out.printf("[AFTER][wiki retry 500] wiki호출=%d%n", wiki.requestCount());
        assertThat(wiki.requestCount()).isEqualTo(2); // max-attempts 2
    }

    /** DB 자동설정을 뺀 최소 컨텍스트: 두 클라이언트 + 설정 + resilience4j·AOP 자동설정. */
    @SpringBootConfiguration
    @EnableAutoConfiguration(exclude = {
        DataSourceAutoConfiguration.class,
        HibernateJpaAutoConfiguration.class,
        DataSourceTransactionManagerAutoConfiguration.class
    })
    @EnableConfigurationProperties(CandidateProperties.class)
    @Import({GatewayEmbeddingClient.class, WikipediaExtractClient.class})
    static class ResilienceTestApp {
    }
}
