package io.wikipulse.backend.matching;

import com.fasterxml.jackson.databind.JsonNode;
import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import io.github.resilience4j.ratelimiter.annotation.RateLimiter;
import io.github.resilience4j.retry.annotation.Retry;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

/**
 * LLM 게이트웨이 경유 Anthropic Messages API 의 범용 전송 (WP-68·-119).
 * {@code {baseUrl}/api.anthropic.com/v1/messages}, 인증은 {@code x-api-key: {키}}.
 * 모델은 POC(ai/llm-verify-poc)에서 검증한 {@code claude-sonnet-4-5-20250929}(-45).
 *
 * <p>{@link #complete}(system + messages → assistant 텍스트)는 도메인 중립이라
 * <b>LLM 검증({@link LlmVerifier}, -68)과 이슈 요약({@link IssueSummarizer}, -119)이 공유</b>한다.
 * 두 용도 모두 같은 gateway 신뢰성 계층·모델·max_tokens 를 탄다 — 요약이 새 신뢰성 계층·새 클라이언트를
 * 만들지 않는다는 -119 계약을 이 공유로 지킨다.
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
 *
 * <h2>🔴 프롬프트 캐싱을 쓰지 않는다 — 켜면 오히려 25% 비싸진다 (WP-150)</h2>
 *
 * <p>{@link LlmVerifier} 는 <b>후보 하나당 1회</b> 호출이라, 한 클러스터의 후보 20~25개가 전부
 * 같은 시스템 프롬프트(4,773자)를 새로 싣는다 — 2026-09-20 운영 실측에서 요청의 <b>84%가
 * 후보마다 동일</b>했다. 그래서 {@code cache_control: ephemeral} 을 붙여 봤고, <b>실패했다.</b>
 *
 * <p>GATEWAY 게이트웨이에 같은 요청을 4회 연속 보낸 실측(2026-09-20):
 *
 * <pre>
 * cached 1: in=8 write=1143 read=0
 * cached 2: in=8 write=1143 read=0
 * cached 3: in=8 write=1143 read=0
 * cached 4: in=8 write=1143 read=0
 * plain   : in=1151 write=0  read=0   ← 캐시 안 쓴 기준선
 * </pre>
 *
 * <p><b>쓰기만 되고 읽기가 한 번도 안 된다.</b> 캐시 쓰기는 입력 단가의 1.25배라 결과적으로
 * {@code 1,151 → 8 + 1,143×1.25 = 1,437} 로 <b>25% 더 나간다.</b> 추정 원인은 GATEWAY 가 상위 계정을
 * 다중화하는 것이다 — Anthropic 프롬프트 캐시는 <b>조직 단위</b>라 요청마다 다른 상위로 가면
 * 앞 호출이 만든 캐시가 안 보인다. (게이트웨이 내부는 확인할 수 없어 <b>추정</b>이다. 다만
 * {@code cache_control} 자체는 통과된다 — {@code cache_creation_input_tokens} 가 차는 것이 증거다.)
 *
 * <p>⚠️ <b>이건 조용히 틀린다.</b> API 가 400 을 주지 않고, {@code cache_creation_input_tokens} 가
 * 차올라서 <b>로그만 보면 캐싱이 동작하는 것처럼 보인다.</b> {@code cache_read_input_tokens} 를
 * 같이 보지 않으면 비용이 늘어난 줄 모른다 — {@link #logUsage} 가 그래서 넷을 다 찍는다.
 *
 * <p>다시 시도하려면 <b>먼저 read 가 차는지부터 재고</b> 넣는다. 근거:
 * {@code docs/validation/2026-09-20-gateway-prompt-cache.md}.
 *
 * <p>⚠️ <b>알려진 잔여 위험 — 200 무텍스트의 상한 없는 재폴</b>: 200 인데 {@code content[0].text}
 * 가 비면 {@link IllegalStateException}(전송 taxonomy 아님 → 재시도·회로 대상 아님)이 워커까지
 * 전파돼 클러스터가 PENDING 으로 남고 {@code attempt_count} 는 안 오른다. 같은 응답이 지속되면
 * 폴 주기마다 <b>실호출이 반복</b>돼 크레딧이 샌다. 이는 {@link GatewayEmbeddingClient} 의 200 무벡터
 * 처리(−66 이 "회로를 안 연다"로 확정, {@code ExternalCallResilienceTest})와 <b>같은 계약</b>이라
 * −68 에서 바꾸지 않았다. 실제 트리거는 좁다: 크레딧 소진은 보통 429/401(→ 하드 → 회로 개방 →
 * 빠른 실패)로 오고, {@code max_tokens} 절단은 <b>부분 텍스트가 있어</b> 스키마 실패 경로(정정→
 * {@code attempt_count} 상한 → FAILED)로 흘러 유한하다. 상한 없이 남는 건 "200 + 진짜 빈 content"
 * 뿐이다. 경계에서 크레딧을 막는 근본 해소는 −66 공용 계약 변경이라 후속으로 둔다.
 */
@Component
public class GatewayVerificationClient {

    private static final Logger log = LoggerFactory.getLogger(GatewayVerificationClient.class);

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
        return call(system, messages, gateway.getVerificationModel(), gateway.getVerificationMaxTokens());
    }

    /**
     * 이슈 요약(-119)용 전송. 검증과 같은 gateway 신뢰성 계층·모델을 타되 <b>max_tokens 만 요약 전용값</b>을
     * 쓴다({@code summary-max-tokens}) — 검증 rationale 절단 방지용 예산과 사용자 노출 요약 예산을
     * 분리해, 한쪽 튜닝이 다른 쪽을 조용히 절단시키지 않게 한다. {@link #complete}(검증)의 동작은
     * 이 메서드 추가로 바뀌지 않는다(공용 전송은 {@link #call} 에 있고 검증 경로는 무손상).
     */
    @RateLimiter(name = "gateway")
    @CircuitBreaker(name = "gateway")
    @Retry(name = "gateway", fallbackMethod = "completeFallback")
    public String completeForSummary(String system, List<Map<String, String>> messages) {
        return call(system, messages, gateway.getVerificationModel(), gateway.getSummaryMaxTokens());
    }

    /**
     * 공용 전송 본체. 🔴 애노테이션 없음 — 신뢰성 계층은 위 두 public 진입점이 소유하고, 이
     * private 메서드는 그 안에서 호출돼 같은 aspect 로 감싸인다(자기호출 프록시 우회 아님).
     */
    private String call(
            String system, List<Map<String, String>> messages, String model, int maxTokens) {
        if (gateway.getApiKey() == null || gateway.getApiKey().isBlank()) {
            throw new IllegalStateException(
                    "LLM_GATEWAY_KEY 가 비어 있다. GATEWAY 를 호출할 수 없다 (명세 §4, tech-spec 환경변수).");
        }
        JsonNode root;
        try {
            root = client.post()
                    .uri("/api.anthropic.com/v1/messages")
                    .header("x-api-key", gateway.getApiKey())
                    .header("anthropic-version", "2023-06-01")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of(
                            "model", model,
                            "max_tokens", maxTokens,
                            "system", system,
                            "messages", messages))
                    .retrieve()
                    .body(JsonNode.class);
        } catch (RestClientException e) {
            // 전송 계층 실패만 taxonomy 로 번역(−66). 200 본문 검증은 아래·LlmVerifier(−68).
            throw UpstreamFailures.classify("GATEWAY", e, false); // 🔴 GATEWAY 429 = 하드(공유 예산 보호)
        }

        logUsage(root, model);

        JsonNode text = root == null ? null : root.path("content").path(0).path("text");
        if (text == null || !text.isTextual() || text.asText().isBlank()) {
            // 200 인데 텍스트 없음 = 스키마 문제(−68 소관). 전송 taxonomy 아님 → 회로에 안 센다.
            throw new IllegalStateException("GATEWAY 응답에 텍스트가 없다 (content[0].text 누락/빈 값)");
        }
        return text.asText();
    }

    /**
     * 응답의 {@code usage} 를 찍는다 (WP-150).
     *
     * <p>🔴 <b>여태 이 값을 버리고 있었다.</b> {@code content[0].text} 만 읽어서, 호출당 비용을
     * 아는 방법이 크레딧 잔액을 호출 전후로 빼 보는 것밖에 없었다 — 실제로 2026-09-20 에 그렇게
     * 쟀다(110건 = 6,781 크레딧, 건당 61.6). 캐시가 먹었는지도 이 값 없이는 확인이 안 된다.
     *
     * <p>{@code cache_read_input_tokens} 가 0 이면 캐시 미적중이다. 첫 호출(클러스터의 첫 후보)은
     * {@code cache_creation_input_tokens} 가 차고 이후 후보들이 read 로 붙는 것이 정상이다.
     * ⚠️ 계속 0 이면 셋 중 하나다 — 시스템 프롬프트가 1,024 토큰 미만으로 줄었거나, GATEWAY 게이트웨이가
     * {@code cache_control} 을 안 넘기거나, TTL(5분)이 지났거나.
     */
    private void logUsage(JsonNode root, String model) {
        JsonNode usage = root == null ? null : root.path("usage");
        if (usage == null || usage.isMissingNode()) {
            return;
        }
        log.info("GATEWAY usage model={} in={} out={} cache_write={} cache_read={}",
                model,
                usage.path("input_tokens").asInt(-1),
                usage.path("output_tokens").asInt(-1),
                usage.path("cache_creation_input_tokens").asInt(-1),
                usage.path("cache_read_input_tokens").asInt(-1));
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
