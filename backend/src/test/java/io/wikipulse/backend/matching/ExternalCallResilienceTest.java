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
            "resilience4j.circuitbreaker.instances.gateway.sliding-window-size=4",
            "resilience4j.circuitbreaker.instances.gateway.minimum-number-of-calls=4",
            "resilience4j.circuitbreaker.instances.gateway.wait-duration-in-open-state=60s"
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
    CircuitBreakerRegistry circuitBreakerRegistry;

    @BeforeEach
    void reset() {
        circuitBreakerRegistry.circuitBreaker("gateway").reset(); // 메서드 간 CB 상태 누수 방지.
        gateway.resetCount();
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
