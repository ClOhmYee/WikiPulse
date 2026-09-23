package io.wikipulse.backend.matching;

import com.fasterxml.jackson.databind.JsonNode;
import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import io.github.resilience4j.ratelimiter.annotation.RateLimiter;
import io.github.resilience4j.retry.annotation.Retry;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

/**
 * 문서 도입부 평문을 Wikipedia API 로 가져온다 (명세 §6.2).
 *
 * <ul>
 *   <li>LIVE: {@link #intro(String)} — {@code prop=extracts&exintro&explaintext&redirects=1},
 *       리다이렉트를 따라간다
 *   <li>리플레이: {@link #revisionAt(String, java.time.OffsetDateTime)} 로 {@code snapshot_ts}
 *       이하 마지막 revision 을 찾고 {@link #introAt(long)} 로 그 시점 도입부를 뽑는다
 *       (WP-129)
 * </ul>
 *
 * <p>🔴 <b>두 경로를 섞지 않는다.</b> 리플레이에서 {@link #intro(String)} 를 부르면 과거 이슈에
 * 현재 문서 내용이 섞인다 — 명세 §6.2 가 금지하는 폴백이다.
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

    /** 한 시점의 revision 좌표. 명세 §6.2 가 "page ID·revision ID·기준 시각을 함께 고정" 하라는 그것. */
    public record Revision(long revId, OffsetDateTime revTs, Long wikiPageId) {
    }

    /**
     * {@code asOf} 이하의 마지막 revision (명세 §6.2 리플레이 출처).
     *
     * <p>{@code rvdir=older&rvstart=asOf&rvlimit=1} = "그 시각에서 과거로 한 걸음" 이다.
     * 그 시점에 아직 없던 문서는 revision 이 없어 {@link Optional#empty()} 다 — 실패가 아니라
     * "그때는 이 문서가 없었다" 는 정상 답이다.
     */
    @RateLimiter(name = "wikipedia")
    @CircuitBreaker(name = "wikipedia")
    @Retry(name = "wikipedia", fallbackMethod = "revisionAtFallback")
    public Optional<Revision> revisionAt(String title, OffsetDateTime asOf) {
        String start = DateTimeFormatter.ISO_INSTANT.format(asOf.toInstant());
        JsonNode root;
        try {
            root = client.get()
                    .uri(uriBuilder -> uriBuilder
                            .queryParam("action", "query")
                            .queryParam("prop", "revisions")
                            .queryParam("rvlimit", "1")
                            .queryParam("rvdir", "older")
                            .queryParam("rvstart", start)
                            .queryParam("rvprop", "ids|timestamp")
                            .queryParam("redirects", "1")
                            .queryParam("format", "json")
                            .queryParam("formatversion", "2")
                            .queryParam("titles", title)
                            .build())
                    .retrieve()
                    .body(JsonNode.class);
        } catch (RestClientException e) {
            throw UpstreamFailures.classify("Wikipedia", e, true);
        }
        if (root == null) {
            return Optional.empty();
        }
        JsonNode page = root.path("query").path("pages").path(0);
        JsonNode revision = page.path("revisions").path(0);
        if (revision.path("revid").isMissingNode()) {
            return Optional.empty();
        }
        Long wikiPageId = page.path("pageid").isMissingNode() ? null : page.path("pageid").asLong();
        return Optional.of(new Revision(
                revision.path("revid").asLong(),
                OffsetDateTime.ofInstant(
                        Instant.parse(revision.path("timestamp").asText()), java.time.ZoneOffset.UTC),
                wikiPageId));
    }

    /**
     * 그 revision 의 도입부 평문 (명세 §6.2 리플레이 출처).
     *
     * <p>🔴 <b>{@code prop=extracts} 로는 못 한다.</b> {@code revids} 를 줘도 현재 도입부가
     * 돌아온다 (2026-09-18 실측, {@link LeadSectionText} 참고). 그래서 리드 섹션 HTML 을 받아
     * 직접 평문으로 바꾼다.
     *
     * @return 도입부 평문. 리드 섹션에 문단이 없으면 빈 문자열
     */
    @RateLimiter(name = "wikipedia")
    @CircuitBreaker(name = "wikipedia")
    @Retry(name = "wikipedia", fallbackMethod = "introAtFallback")
    public String introAt(long revId) {
        JsonNode root;
        try {
            root = client.get()
                    .uri(uriBuilder -> uriBuilder
                            .queryParam("action", "parse")
                            .queryParam("oldid", revId)
                            .queryParam("prop", "text")
                            .queryParam("section", "0")
                            .queryParam("disabletoc", "1")
                            .queryParam("disableeditsection", "1")
                            .queryParam("format", "json")
                            .queryParam("formatversion", "2")
                            .build())
                    .retrieve()
                    .body(JsonNode.class);
        } catch (RestClientException e) {
            throw UpstreamFailures.classify("Wikipedia", e, true);
        }
        if (root == null) {
            return "";
        }
        return LeadSectionText.fromHtml(root.path("parse").path("text").asText(""));
    }

    /** {@code titles} 한 요청에 담을 수 있는 제목 수. 🔴 51개부터는 잘림이 아니라 에러다. */
    public static final int TITLES_PER_REQUEST = 50;

    /**
     * 영문 제목 → ko.wikipedia 대응 제목 (표시 전용).
     *
     * <p>🔴 <b>표시명 조회다. 식별자를 만들지 않는다.</b> 결과는 {@code wiki_page.title_ko} 에만
     * 들어가고 {@code title}(자연키·링크·조인)은 건드리지 않는다.
     *
     * <p><b>왜 이 클래스에 두나.</b> 같은 {@code en.wikipedia.org/w/api.php} 를 때리는데 클라이언트를
     * 하나 더 만들면 named instance {@code wikipedia} 의 RateLimiter 가 둘로 갈려 위키미디어
     * 입장에서는 초당 호출이 두 배가 된다 — 예절 상한이 상한 노릇을 못 한다. UA·타임아웃도
     * 두 벌이 된다. 그래서 RestClient 를 공유한다.
     *
     * <p>🔴 <b>{@code redirects} 파라미터를 주지 않는다.</b> 주면 응답의 {@code pages[].title} 이
     * 우리가 보낸 제목이 아니라 <b>리다이렉트 목적지</b>가 되어, A 문서에 B 문서의 한국어 이름이
     * 붙는다. 2026-09-22 실측: {@code Effects of Hurricane Milton in Florida} → {@code Hurricane
     * Milton}("허리케인 밀턴"), {@code 2025 Iran threat of Strait of Hormuz closure} →
     * {@code Twelve-Day War}("12일 전쟁"). 값이 그럴듯해서 화면만 봐서는 틀린 줄 모른다.
     * 파라미터를 빼면 리다이렉트 문서는 langlinks 없이 돌아와 그냥 미스가 되고, 화면은 영문으로
     * 떨어진다 — MVP 는 이 보수적인 쪽을 택한다. 정밀 매핑은 후속 범위다.
     *
     * <p>⚠️ 다만 MediaWiki 는 {@code redirects} 와 무관하게 <b>정규화</b>는 한다
     * ({@code Hurricane_Milton} → {@code Hurricane Milton}). 정규화는 같은 문서를 가리키는
     * 표기 차이라 안전하므로 {@code query.normalized} 로 되매핑한다. 그 매핑에도 안 걸리는
     * 제목은 미스로 둔다 — <b>추측해서 갖다 붙이지 않는다.</b>
     *
     * @param titles 최대 {@value #TITLES_PER_REQUEST} 개. 호출자가 쪼갠다
     * @return ko 대응이 <b>있는</b> 제목만 담긴 맵. 없는 제목은 키 자체가 없다 —
     *         "조회했고 없음"과 "조회 안 함"의 구분은 호출자(checked_at)가 한다
     * @throws IllegalArgumentException 제목이 {@value #TITLES_PER_REQUEST} 개를 넘을 때
     * @throws UpstreamUnavailableException 전송 실패 — 🔴 빈 맵으로 삼키지 않는다.
     *         삼키면 위키 일시 장애 구간 문서가 "ko 없음"으로 굳어 영구히 영문이 된다
     */
    @RateLimiter(name = "wikipedia")
    @CircuitBreaker(name = "wikipedia")
    @Retry(name = "wikipedia", fallbackMethod = "koTitlesFallback")
    public Map<String, String> koTitles(List<String> titles) {
        if (titles.size() > TITLES_PER_REQUEST) {
            throw new IllegalArgumentException(
                    "titles 는 한 요청에 " + TITLES_PER_REQUEST + "개까지다: " + titles.size());
        }
        if (titles.isEmpty()) {
            return Map.of();
        }
        String joined = String.join("|", titles);
        JsonNode root;
        try {
            root = client.get()
                    .uri(uriBuilder -> uriBuilder
                            .queryParam("action", "query")
                            .queryParam("prop", "langlinks")
                            .queryParam("lllang", "ko")
                            .queryParam("lllimit", "max")
                            .queryParam("format", "json")
                            .queryParam("formatversion", "2")
                            .queryParam("titles", joined)
                            .build())
                    .retrieve()
                    .body(JsonNode.class);
        } catch (RestClientException e) {
            throw UpstreamFailures.classify("Wikipedia", e, true); // 위키는 429 도 전이성
        }
        return parseKoTitles(root, titles);
    }

    /** 응답 → (보낸 제목 → ko 제목). 정규화만 되짚고 그 외 불일치는 버린다. 패키지 공개는 테스트용. */
    static Map<String, String> parseKoTitles(JsonNode root, List<String> requested) {
        if (root == null) {
            return Map.of();
        }
        JsonNode query = root.path("query");

        // 응답 제목(정규화된 형태) → ko. missing 문서·ko 없는 문서는 안 담긴다.
        Map<String, String> byResponseTitle = new LinkedHashMap<>();
        for (JsonNode page : query.path("pages")) {
            JsonNode ko = page.path("langlinks").path(0).path("title");
            if (!page.path("title").isTextual() || !ko.isTextual() || ko.asText().isBlank()) {
                continue;
            }
            byResponseTitle.put(page.path("title").asText(), ko.asText());
        }

        // 보낸 제목 → 응답에서 쓰인 제목. normalized 가 없으면 그대로 쓴다.
        Map<String, String> normalized = new LinkedHashMap<>();
        for (JsonNode n : query.path("normalized")) {
            if (n.path("from").isTextual() && n.path("to").isTextual()) {
                normalized.put(n.path("from").asText(), n.path("to").asText());
            }
        }

        Map<String, String> result = new LinkedHashMap<>();
        for (String title : requested) {
            String ko = byResponseTitle.get(normalized.getOrDefault(title, title));
            if (ko != null) {
                result.put(title, ko);
            }
        }
        return result;
    }

    @SuppressWarnings("unused") // resilience4j 가 리플렉션으로 부른다.
    private Map<String, String> koTitlesFallback(List<String> titles, Throwable t) {
        if (t instanceof IllegalArgumentException e) {
            throw e; // 우리 쪽 오용이다 — 전송 실패로 둔갑시키지 않는다.
        }
        throw new UpstreamUnavailableException(
                "Wikipedia langlinks 호출 불가 (" + t.getClass().getSimpleName() + "): "
                        + titles.size() + "건", t);
    }

    @SuppressWarnings("unused") // resilience4j 가 리플렉션으로 부른다.
    private Optional<Revision> revisionAtFallback(String title, OffsetDateTime asOf, Throwable t) {
        throw new UpstreamUnavailableException(
                "Wikipedia revision 조회 불가 (" + t.getClass().getSimpleName() + "): " + title, t);
    }

    @SuppressWarnings("unused") // resilience4j 가 리플렉션으로 부른다.
    private String introAtFallback(long revId, Throwable t) {
        throw new UpstreamUnavailableException(
                "Wikipedia 과거 도입부 호출 불가 (" + t.getClass().getSimpleName() + "): oldid=" + revId, t);
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
