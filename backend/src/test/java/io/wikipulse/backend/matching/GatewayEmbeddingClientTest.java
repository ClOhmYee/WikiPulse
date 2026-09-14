package io.wikipulse.backend.matching;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

/**
 * GATEWAY 키 부재 가드 (명세 §4). 키가 없으면 조용히 빈 벡터를 내지 않고 명확히 실패한다 —
 * 그래야 "이유 없이 후보 0건"이 안 된다. HTTP 호출 이전에 던지므로 네트워크 불요.
 */
class GatewayEmbeddingClientTest {

    @Test
    void 키가_비어있으면_IllegalStateException() {
        CandidateProperties props = new CandidateProperties(); // gateway.apiKey 기본 ""
        GatewayEmbeddingClient client = new GatewayEmbeddingClient(props);

        assertThatThrownBy(() -> client.embed("anything"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("LLM_GATEWAY_KEY");
    }
}
