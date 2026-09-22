package io.wikipulse.backend.page;

import com.fasterxml.jackson.databind.JsonNode;
import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import io.github.resilience4j.ratelimiter.annotation.RateLimiter;
import io.github.resilience4j.retry.annotation.Retry;
import io.wikipulse.backend.matching.UpstreamFailures;
import io.wikipulse.backend.matching.UpstreamUnavailableException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
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
 * 영문 제목을 한국어로 기계 번역한다 (Azure Translator, en→ko).
 *
 * <p>🔴 <b>2단 폴백 전용이다.</b> {@code wiki_page.title_ko_fallback} 에만 들어가고,
 * ko.wikipedia 정식 제목({@code title_ko})이나 영문 정본({@code title})은 건드리지 않는다.
 * 이 값으로 위키백과 링크를 만들지 않는다 — 실제 문서 제목이 아니기 때문이다.
 *
 * <p><b>왜 별도 클라이언트인가.</b> {@link io.wikipulse.backend.matching.WikipediaExtractClient}
 * 는 {@code en.wikipedia.org} 하나를 보는 RestClient 라 baseUrl·UA·신뢰성 인스턴스를 공유할 수
 * 없다. Azure 는 호스트·인증 헤더·쿼터가 전부 다르고, 특히 <b>회로를 따로 열어야 한다</b> —
 * Azure 가 죽었다고 위키 langlinks 조회까지 같이 막히면 1단 폴백마저 멈춘다.
 * named instance 는 {@code azure} 다.
 *
 * <p><b>요청 형식</b> (Translator v3):
 * {@code POST {endpoint}/translate?api-version=3.0&from=en&to=ko}, 본문은
 * {@code [{"Text":"..."}, ...]}, 응답은 같은 순서의 배열이다. 순서로 짝을 맞추므로
 * <b>응답 길이가 요청과 다르면 통째로 버린다</b> — 어긋난 채 짝지으면 A 문서에 B 문서의
 * 번역이 붙고, 값이 그럴듯해서 화면만 봐서는 틀린 줄 모른다.
 *
 * <p>🔴 키는 저장소에 넣지 않는다. {@code AZURE_TRANSLATOR_KEY} 환경변수로만 주입하며,
 * 비어 있으면 {@link #isConfigured()} 가 false 라 호출 자체를 하지 않는다(번역 없이 영문 표시).
 */
@Component
public class AzureTranslatorClient {

    private static final Logger log = LoggerFactory.getLogger(AzureTranslatorClient.class);

    /** 한 요청에 담을 제목 수. Translator v3 상한(요소 1,000 / 50,000자)보다 훨씬 보수적으로 잡는다. */
    public static final int TEXTS_PER_REQUEST = 50;

    private final PageTitleProperties.Azure cfg;
    private final RestClient client;

    public AzureTranslatorClient(PageTitleProperties props) {
        this.cfg = props.getAzure();
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        // 🔴 타임아웃 필수 — 없으면 소켓 hang 하나가 단일 스케줄러 스레드를 영구 정지시킨다.
        factory.setConnectTimeout(cfg.getConnectTimeout());
        factory.setReadTimeout(cfg.getReadTimeout());
        this.client = RestClient.builder()
                .baseUrl(cfg.getEndpoint())
                .requestFactory(factory)
                .build();
    }

    /** 키·엔드포인트가 주입됐는가. false 면 호출자는 번역 단계를 통째로 건너뛴다. */
    public boolean isConfigured() {
        return !cfg.getKey().isBlank() && !cfg.getEndpoint().isBlank();
    }

    /**
     * 영문 제목 → 한국어 기계 번역.
     *
     * @param titles 최대 {@value #TEXTS_PER_REQUEST} 개. 호출자가 쪼갠다
     * @return 번역이 나온 제목만 담긴 맵. 빈 번역·순서 불일치는 버려서 키가 없다
     * @throws IllegalArgumentException 제목이 상한을 넘을 때
     * @throws UpstreamUnavailableException 전송 실패 — 🔴 빈 맵으로 삼키지 않는다.
     *         삼키면 Azure 일시 장애 구간 문서가 "번역 없음"으로 굳어 영구히 영문이 된다
     */
    @RateLimiter(name = "azure")
    @CircuitBreaker(name = "azure")
    @Retry(name = "azure", fallbackMethod = "translateFallback")
    public Map<String, String> translate(List<String> titles) {
        if (titles.size() > TEXTS_PER_REQUEST) {
            throw new IllegalArgumentException(
                    "titles 는 한 요청에 " + TEXTS_PER_REQUEST + "개까지다: " + titles.size());
        }
        if (titles.isEmpty() || !isConfigured()) {
            return Map.of();
        }
        List<Map<String, String>> body = titles.stream().map(t -> Map.of("Text", t)).toList();
        JsonNode root;
        try {
            root = client.post()
                    .uri(uriBuilder -> uriBuilder
                            .path("/translate")
                            .queryParam("api-version", "3.0")
                            .queryParam("from", "en")
                            .queryParam("to", "ko")
                            .build())
                    .header("Ocp-Apim-Subscription-Key", cfg.getKey())
                    .header("Ocp-Apim-Subscription-Region", cfg.getRegion())
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(body)
                    .retrieve()
                    .body(JsonNode.class);
        } catch (RestClientException e) {
            // F0 는 쿼터 초과도 429 로 온다. 위키와 달리 크레딧(쿼터) 자원이라 하드로 본다 —
            // 재시도하면 남은 쿼터를 더 태운다.
            throw UpstreamFailures.classify("AzureTranslator", e, false);
        }
        return parse(root, titles);
    }

    /** 응답 → (보낸 제목 → 번역). 순서로 짝을 맞춘다. 패키지 공개는 테스트용. */
    static Map<String, String> parse(JsonNode root, List<String> requested) {
        if (root == null || !root.isArray()) {
            return Map.of();
        }
        if (root.size() != requested.size()) {
            // 🔴 순서 짝짓기가 전제다. 길이가 다르면 어느 것이 밀렸는지 알 수 없으므로
            //    일부만 취하지 않고 통째로 버린다 — 잘못 짝지으면 조용히 틀린다.
            log.warn("Azure 응답 길이 불일치 요청={} 응답={} — 이 청크를 버린다",
                    requested.size(), root.size());
            return Map.of();
        }
        Map<String, String> out = new LinkedHashMap<>();
        for (int i = 0; i < requested.size(); i++) {
            JsonNode text = root.path(i).path("translations").path(0).path("text");
            if (text.isTextual() && !text.asText().isBlank()) {
                out.put(requested.get(i), text.asText().strip());
            }
        }
        return out;
    }

    /** 번역 대상 목록을 요청 상한 단위로 쪼갠다. */
    static List<List<String>> chunk(List<String> titles) {
        List<List<String>> chunks = new ArrayList<>();
        for (int from = 0; from < titles.size(); from += TEXTS_PER_REQUEST) {
            chunks.add(titles.subList(from, Math.min(from + TEXTS_PER_REQUEST, titles.size())));
        }
        return chunks;
    }

    @SuppressWarnings("unused") // resilience4j 가 리플렉션으로 부른다.
    private Map<String, String> translateFallback(List<String> titles, Throwable t) {
        if (t instanceof IllegalArgumentException e) {
            throw e; // 우리 쪽 오용이다 — 전송 실패로 둔갑시키지 않는다.
        }
        throw new UpstreamUnavailableException(
                "Azure Translator 호출 불가 (" + t.getClass().getSimpleName() + "): "
                        + titles.size() + "건", t);
    }
}
