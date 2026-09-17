package io.wikipulse.backend.matching;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * AFTER — GATEWAY 레이트리밋 처리량 캡 (WP-66). 공유 예산 폭주 상한이 실제로 막는지 확인한다.
 * limit-for-period 를 3 으로 낮추고 refresh 를 길게 잡아, 즉시 5회 호출 중 3회만 통과하고
 * 초과 2회는 폴백 신호로 떨어지는지 본다. 컨텍스트 격리를 위해 별도 클래스로 둔다
 * ({@link ExternalCallResilienceTest} 는 CB 검증에 4콜 이상이 필요해 limit 을 못 낮춘다).
 */
@SpringBootTest(
        classes = ExternalCallResilienceTest.ResilienceTestApp.class,
        properties = {
            "spring.main.banner-mode=off",
            "resilience4j.ratelimiter.instances.gateway.limit-for-period=3",
            "resilience4j.ratelimiter.instances.gateway.limit-refresh-period=1h",
            "resilience4j.ratelimiter.instances.gateway.timeout-duration=0"
        })
class GatewayRateLimiterTest {

    private static FakeUpstream gateway;
    private static FakeUpstream wiki;

    @DynamicPropertySource
    static void wireUpstreams(DynamicPropertyRegistry registry) throws IOException {
        gateway = new FakeUpstream(FakeUpstream.GATEWAY_OK_BODY, 1500);
        wiki = new FakeUpstream(FakeUpstream.WIKI_OK_BODY, 1500);
        registry.add("wikipulse.matching.gateway.base-url", () -> "http://127.0.0.1:" + gateway.port());
        registry.add("wikipulse.matching.gateway.api-key", () -> "test-key");
        registry.add("wikipulse.matching.gateway.connect-timeout", () -> "500ms");
        // OK 응답 3회 성공 카운트가 정확성의 전제라 read-timeout 을 넉넉히 잡는다(hang 테스트 없음).
        // 짧게 잡으면 부하 걸린 CI 에서 loopback OK 가 타임아웃→전이성으로 새어 ok==3 이 깨질 수 있다.
        registry.add("wikipulse.matching.gateway.read-timeout", () -> "5s");
        registry.add("wikipulse.matching.wikipedia.api-url", () -> "http://127.0.0.1:" + wiki.port() + "/w/api.php");
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

    @Test
    void 처리량_캡을_넘으면_초과호출은_폴백신호로_떨어진다() {
        gateway.mode(FakeUpstream.Mode.OK);

        int ok = 0;
        int rejected = 0;
        for (int i = 0; i < 5; i++) {
            try {
                gatewayClient.embed("x");
                ok++;
            } catch (UpstreamUnavailableException e) {
                rejected++; // RL 거부(RequestNotPermitted) → 폴백 → 호출 못 함 신호.
            }
        }

        // limit 3 → 3회만 업스트림에 닿고, 초과 2회는 업스트림을 안 때린다(예산 보호).
        System.out.printf("[AFTER][RL cap] 통과=%d 거부=%d gateway호출=%d%n", ok, rejected, gateway.requestCount());
        assertThat(ok).isEqualTo(3);
        assertThat(rejected).isEqualTo(2);
        assertThat(gateway.requestCount()).isEqualTo(3);
    }
}
