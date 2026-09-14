package io.wikipulse.backend.matching;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/**
 * 텍스트를 벡터로 임베딩한다 — LLM 게이트웨이 경유 OpenAI {@code text-embedding-3-small}
 * (1,536차원, 명세 §4). GATEWAY 프록시는 원래 호스트 경로를 뒤에 붙인다:
 * {@code {baseUrl}/api.openai.com/v1/embeddings}, 인증은 {@code Authorization: Bearer {키}}.
 *
 * <p>🔴 키는 환경변수 {@code LLM_GATEWAY_KEY} 로만 온다. 비어 있으면 명확히 실패시킨다 —
 * 키 없이 조용히 빈 벡터를 내면 후보 생성이 이유 없이 0건이 된다.
 */
@Component
public class GatewayEmbeddingClient {

    private final RestClient client;
    private final CandidateProperties.Gateway gateway;

    public GatewayEmbeddingClient(CandidateProperties props) {
        this.gateway = props.getGateway();
        // 🔴 타임아웃 필수 — 없으면 소켓 hang 이 단일 스케줄러 스레드를 영구 정지시킨다.
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
     * 텍스트 하나를 임베딩한다.
     *
     * @return 1,536차원 벡터
     * @throws IllegalStateException GATEWAY 키가 없을 때
     * @throws org.springframework.web.client.RestClientException 게이트웨이 오류
     */
    public float[] embed(String text) {
        if (gateway.getApiKey() == null || gateway.getApiKey().isBlank()) {
            throw new IllegalStateException(
                    "LLM_GATEWAY_KEY 가 비어 있다. 이슈 임베딩을 만들 수 없다 (명세 §4, tech-spec 환경변수).");
        }
        JsonNode root = client.post()
                .uri("/api.openai.com/v1/embeddings")
                .header("Authorization", "Bearer " + gateway.getApiKey())
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("model", gateway.getEmbeddingModel(), "input", text))
                .retrieve()
                .body(JsonNode.class);

        JsonNode vector = root == null ? null : root.path("data").path(0).path("embedding");
        if (vector == null || !vector.isArray() || vector.isEmpty()) {
            // 응답 본문 전체를 메시지에 싣지 않는다 — 로그 비대·장래 에코형 게이트웨이의 위험 표면.
            throw new IllegalStateException("GATEWAY 임베딩 응답에 벡터가 없다 (data[0].embedding 누락/빈 배열)");
        }
        float[] out = new float[vector.size()];
        for (int i = 0; i < out.length; i++) {
            out[i] = (float) vector.get(i).asDouble();
        }
        return out;
    }
}
