package io.wikipulse.backend.matching;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.Iterator;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/**
 * 문서 도입부 평문을 Wikipedia API 로 가져온다 (명세 §6.2).
 * {@code prop=extracts&exintro&explaintext&redirects=1} — 리다이렉트를 따라간다.
 *
 * <p>실패(네트워크·404·파싱)는 빈 문자열로 흡수한다. 도입부 하나가 안 와도 나머지 문서로
 * 대표 텍스트를 만들 수 있어야 하고, 한 문서 때문에 이슈 전체 후보 생성이 죽으면 안 된다.
 * {@code ai/issue-text-poc} 의 {@code wiki_intro} 와 같은 호출이다.
 */
@Component
public class WikipediaExtractClient {

    private static final Logger log = LoggerFactory.getLogger(WikipediaExtractClient.class);

    private final RestClient client;

    public WikipediaExtractClient(CandidateProperties props) {
        this.client = RestClient.builder()
                .baseUrl(props.getWikipedia().getApiUrl())
                .defaultHeader("User-Agent", props.getWikipedia().getUserAgent())
                .build();
    }

    /** 도입부 평문. 없거나 실패하면 빈 문자열. */
    public String intro(String title) {
        try {
            JsonNode root = client.get()
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
            if (root == null) {
                return "";
            }
            JsonNode pages = root.path("query").path("pages");
            for (Iterator<JsonNode> it = pages.elements(); it.hasNext(); ) {
                String extract = it.next().path("extract").asText("");
                return extract.strip();
            }
            return "";
        } catch (RuntimeException e) {
            log.warn("Wikipedia 도입부 조회 실패, 건너뜀: title={} ({})", title, e.toString());
            return "";
        }
    }
}
