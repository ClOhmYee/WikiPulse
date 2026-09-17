package io.wikipulse.backend.matching;

import com.fasterxml.jackson.databind.JsonNode;
import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import io.github.resilience4j.ratelimiter.annotation.RateLimiter;
import io.github.resilience4j.retry.annotation.Retry;
import java.util.Iterator;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

/**
 * 문서 도입부 평문을 Wikipedia API 로 가져온다 (명세 §6.2).
 * {@code prop=extracts&exintro&explaintext&redirects=1} — 리다이렉트를 따라간다.
 *
 * <p>🔴 실패 시멘틱을 구분한다. "문서에 도입부가 없다"(정상 200, extract 비었거나 missing)는
 * 빈 문자열로 흡수한다 — 그 문서는 대표 텍스트에서 빠질 뿐이다. 그러나 <b>네트워크·타임아웃·
 * 5xx·429 같은 전이성 실패는 삼키지 않고 예외로 전파</b>한다. 삼켜서 빈 문자열로 돌리면,
 * 위키가 일시적으로 죽은 사이 대표 텍스트가 통째로 비어 임베딩 경로 없이 GDELT 단독 후보가
 * cluster_stock 에 적재되고, 폴러가 그 클러스터를 "완료"로 보아 위키 회복 후에도 임베딩 후보를
 * 영영 안 만든다(멀티렌즈 finding#4). 전파하면 클러스터가 미완료로 남아 다음 폴에서 재시도된다.
 *
 * <p>🔴 connect/read 타임아웃을 반드시 건다. 없으면 소켓 hang 하나가 단일 스케줄러 스레드를
 * 영구 정지시켜 이후 모든 폴이 멈춘다(정적 RestClient.builder 는 Boot 의 타임아웃 자동설정을
 * 안 타므로 여기서 명시한다).
 *
 * <p><b>신뢰성 계층 (WP-66)</b>: named instance {@code wikipedia}(GATEWAY 와 별도 게이트웨이).
 * {@code @RateLimiter}(예절) → {@code @CircuitBreaker} → {@code @Retry}(전이성만, fallback).
 * Wikipedia 는 크레딧 무관이라 429 도 전이성으로 재시도한다. 전이성 실패의 "삼키지 않는다"
 * 계약은 폴백이 {@link UpstreamUnavailableException} 을 던져 유지한다(빈 문자열로 흡수 금지).
 */
@Component
public class WikipediaExtractClient {

    private final RestClient client;

    public WikipediaExtractClient(CandidateProperties props) {
        CandidateProperties.Wikipedia cfg = props.getWikipedia();
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(cfg.getConnectTimeout());
        factory.setReadTimeout(cfg.getReadTimeout());
        this.client = RestClient.builder()
                .baseUrl(cfg.getApiUrl())
                .defaultHeader("User-Agent", cfg.getUserAgent())
                .requestFactory(factory)
                .build();
    }

    /**
     * 도입부 평문. 문서에 도입부가 없으면 빈 문자열.
     *
     * @throws org.springframework.web.client.RestClientException 전이성 실패(타임아웃·5xx·429·
     *         연결 오류). 호출자는 이를 삼키지 말고 클러스터를 미완료로 남겨 재시도해야 한다.
     */
    @RateLimiter(name = "wikipedia")
    @CircuitBreaker(name = "wikipedia")
    @Retry(name = "wikipedia", fallbackMethod = "introFallback")
    public String intro(String title) {
        JsonNode root;
        try {
            root = client.get()
                    .uri(uriBuilder -> uriBuilder
                            .queryParam("action", "query")
                            .queryParam("prop", "extracts")
                            .queryParam("exintro", "1")
                            .queryParam("explaintext", "1")
                            .queryParam("redirects", "1")
                            .queryParam("format", "json")
                            .queryParam("titles", title)
                            .build())
                    .retrieve()
                    .body(JsonNode.class);
        } catch (RestClientException e) {
            throw UpstreamFailures.classify("Wikipedia", e, true); // 위키는 429 도 전이성(크레딧 무관)
        }
        if (root == null) {
            return "";
        }
        JsonNode pages = root.path("query").path("pages");
        for (Iterator<JsonNode> it = pages.elements(); it.hasNext(); ) {
            // 없는 문서는 200 에 missing 플래그로 오고 extract 가 없다 → "" (정상 빈 결과).
            return it.next().path("extract").asText("").strip();
        }
        return "";
    }

    /**
     * 재시도 소진·회로 개방·레이트리밋 거부를 "호출 못 함" 신호로 정규화한다. 🔴 빈 문자열로
     * 삼키지 않는다 — 그러면 위키 일시 장애 사이 대표 텍스트가 비어 클러스터가 조기 done 으로
     * 굳는다(finding#4). 신호를 던져 클러스터를 미완료로 남긴다.
     */
    @SuppressWarnings("unused") // resilience4j 가 리플렉션으로 부른다.
    private String introFallback(String title, Throwable t) {
        throw new UpstreamUnavailableException(
                "Wikipedia 도입부 호출 불가 (" + t.getClass().getSimpleName() + "): " + title, t);
    }
}
