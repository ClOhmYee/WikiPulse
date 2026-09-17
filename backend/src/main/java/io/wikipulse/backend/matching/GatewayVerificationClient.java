package io.wikipulse.backend.matching;

import com.fasterxml.jackson.databind.JsonNode;
import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import io.github.resilience4j.ratelimiter.annotation.RateLimiter;
import io.github.resilience4j.retry.annotation.Retry;
import java.util.List;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

/**
 * LLM 검증 호출 (WP-68) — LLM 게이트웨이 경유 Anthropic Messages API.
 * {@code {baseUrl}/api.anthropic.com/v1/messages}, 인증은 {@code x-api-key: {키}}.
 * 모델은 POC(ai/llm-verify-poc)에서 검증한 {@code claude-sonnet-4-5-20250929}(-45).
 *
 * <p>🔴 <b>-66 위에 얹는다 — 새 신뢰성 계층을 만들지 않는다.</b> named instance {@code gateway} 를
 * {@link GatewayEmbeddingClient} 와 <b>공유</b>한다(임베딩·LLM 공용 게이트웨이). 같은 RateLimiter(공유
 * 예산 상한)·CircuitBreaker(죽은 GATEWAY 빠른 실패)·Retry(전이성만) 인스턴스를 탄다 —
 * 임베딩이 GATEWAY 를 죽였다고 보면 검증도 같은 회로로 빠르게 실패한다. 전송 실패는
 * {@link UpstreamFailures#classify} 로 전이성/하드를 가르고(🔴 429·키만료는 하드 → 재시도 없이
 * 회로 개방, 유한 크레딧 보호), 폴백은 {@link UpstreamUnavailableException} 을 던진다.
 *
 * <p>이 클라이언트는 <b>전송만</b> 한다. 응답 JSON 의 스키마 검증·정정 재요청은 {@link LlmVerifier}
 * 몫이다(−66/−68 경계, {@link GatewayEmbeddingClient} 의 "200 무벡터는 −68 소관"과 같은 분리).
 */
@Component
public class GatewayVerificationClient {

    private final RestClient client;
    private final CandidateProperties.Gateway gateway;

    public GatewayVerificationClient(CandidateProperties props) {
        this.gateway = props.getGateway();
        // 🔴 타임아웃 필수 — 없으면 소켓 hang 이 단일 워커 스레드를 영구 정지시킨다.
        // 정적 RestClient.builder 는 Boot 의 spring.http.client 자동설정을 안 타므로 여기서 명시한다.
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(gateway.getConnectTimeout());
        factory.setReadTimeout(gateway.getReadTimeout());
        this.client = RestClient.builder()
                .baseUrl(gateway.getBaseUrl())
                .requestFactory(factory)
                .build();
    }

    /**
     * 시스템 프롬프트 + 대화 메시지로 한 번 호출하고 assistant 텍스트를 돌려준다.
     *
     * @param system   고정 시스템 프롬프트 (verify_system_v1.txt)
     * @param messages Anthropic messages 배열: 각 원소가 {@code {"role","content"}}
     * @return assistant 응답 텍스트 (JSON 문자열일 것으로 기대 — 검증은 호출자)
     * @throws IllegalStateException GATEWAY 키가 없거나 응답에 텍스트가 없을 때(−68 소관, 회로에 안 셈)
     * @throws UpstreamUnavailableException 전송 계층 실패(−66 폴백)
     */
    @RateLimiter(name = "gateway")
    @CircuitBreaker(name = "gateway")
    @Retry(name = "gateway", fallbackMethod = "completeFallback")
    public String complete(String system, List<Map<String, String>> messages) {
        if (gateway.getApiKey() == null || gateway.getApiKey().isBlank()) {
            throw new IllegalStateException(
                    "LLM_GATEWAY_KEY 가 비어 있다. LLM 검증을 호출할 수 없다 (명세 §4, tech-spec 환경변수).");
        }
        JsonNode root;
        try {
            root = client.post()
                    .uri("/api.anthropic.com/v1/messages")
                    .header("x-api-key", gateway.getApiKey())
                    .header("anthropic-version", "2023-06-01")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of(
                            "model", gateway.getVerificationModel(),
                            "max_tokens", gateway.getVerificationMaxTokens(),
                            "system", system,
                            "messages", messages))
                    .retrieve()
                    .body(JsonNode.class);
        } catch (RestClientException e) {
            // 전송 계층 실패만 taxonomy 로 번역(−66). 200 본문 검증은 아래·LlmVerifier(−68).
            throw UpstreamFailures.classify("GATEWAY", e, false); // 🔴 GATEWAY 429 = 하드(공유 예산 보호)
        }

        JsonNode text = root == null ? null : root.path("content").path(0).path("text");
        if (text == null || !text.isTextual() || text.asText().isBlank()) {
            // 200 인데 텍스트 없음 = 스키마 문제(−68 소관). 전송 taxonomy 아님 → 회로에 안 센다.
            throw new IllegalStateException("GATEWAY 검증 응답에 텍스트가 없다 (content[0].text 누락/빈 값)");
        }
        return text.asText();
    }

    /**
     * 재시도 소진·하드 실패·회로 개방·레이트리밋 거부를 단일 "호출 못 함" 신호로 정규화한다.
     * 키 부재·응답 스키마({@link IllegalStateException})는 −66 전송 실패가 아니므로 원형 전파한다
     * (폴백이 삼키지 않는다 — {@link GatewayEmbeddingClient#embedFallback} 과 같은 계약).
     */
    @SuppressWarnings("unused") // resilience4j 가 리플렉션으로 부른다.
    private String completeFallback(String system, List<Map<String, String>> messages, Throwable t) {
        if (t instanceof IllegalStateException ise) {
            throw ise; // 키 부재·스키마: −66 소관 아님 → 원형 유지.
        }
        throw new UpstreamUnavailableException(
                "GATEWAY 검증 호출 불가 (" + t.getClass().getSimpleName() + ")", t);
    }
}
