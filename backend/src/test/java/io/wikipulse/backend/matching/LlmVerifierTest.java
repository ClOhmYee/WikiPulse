package io.wikipulse.backend.matching;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * 판정기 (WP-68). 전송 이음매({@link GatewayVerificationClient})는 목이라 네트워크 없이
 * 파싱·스키마 검증·정정 재요청(-45)·전송 실패 전파를 본다.
 */
@ExtendWith(MockitoExtension.class)
class LlmVerifierTest {

    @Mock
    GatewayVerificationClient client;

    final CandidateProperties props = new CandidateProperties();

    LlmVerifier verifier() {
        return new LlmVerifier(client, new ObjectMapper(), props);
    }

    @Test
    void 재사용_버전에_모델이_박힌다() {
        // 🔴 같은 프롬프트라도 모델이 다르면 판정이 다르다(-170 실측: 같은 Milton 노이즈를
        //    Sonnet 은 3개 통과시켰고 nano 는 0개였다). 버전이 프롬프트만 담으면 모델을 바꿔도
        //    옛 모델 판정이 조용히 재사용된다.
        props.getGateway().setVerificationModel("gpt-5.4-nano");
        assertThat(verifier().verdictVersion()).isEqualTo("v1+gpt-5.4-nano");

        props.getGateway().setVerificationModel("claude-sonnet-4-5-20250929");
        assertThat(verifier().verdictVersion()).isEqualTo("v1+claude-sonnet-4-5-20250929");
    }

    private static final String VALID = """
            {"issue_class":"SECTOR_OR_REGION_EVENT","verified":true,
             "match_path":"REGION","confidence":"strong",
             "rationale_en":"Florida utility exposure.","rationale_ko":"플로리다 전력 노출."}
            """;

    private LlmVerifier.Input input() {
        return new LlmVerifier.Input("Hurricane Milton: ...", "NextEra Energy, Duke Energy",
                "NextEra Energy", "NEE", "A Florida utility.");
    }

    @Test
    void 스키마_통과면_한_번_호출하고_판정을_돌려준다() {
        when(client.complete(anyString(), anyList())).thenReturn(VALID);

        Optional<VerificationResponse> r = verifier().verify(input());

        assertThat(r).isPresent();
        assertThat(r.get().verified()).isTrue();
        assertThat(r.get().rationaleKo()).isEqualTo("플로리다 전력 노출.");
        verify(client, times(1)).complete(anyString(), anyList());
    }

    @Test
    void 코드펜스로_감싸도_파싱한다() {
        when(client.complete(anyString(), anyList()))
                .thenReturn("```json\n" + VALID + "\n```");

        assertThat(verifier().verify(input())).isPresent();
    }

    @Test
    void 스키마_위반이면_정정_1회_후_성공하면_통과() {
        when(client.complete(anyString(), anyList()))
                .thenReturn("{\"verified\": true}")  // 1차: 키 불일치
                .thenReturn(VALID);                    // 정정 후: 통과

        Optional<VerificationResponse> r = verifier().verify(input());

        assertThat(r).isPresent();
        verify(client, times(2)).complete(anyString(), anyList());
    }

    @Test
    @SuppressWarnings("unchecked")
    void 정정_요청은_같은_대화에_이전_응답과_교정지시를_덧붙인다() {
        when(client.complete(anyString(), anyList()))
                .thenReturn("not json at all")
                .thenReturn(VALID);

        verifier().verify(input());

        ArgumentCaptor<List<Map<String, String>>> captor = ArgumentCaptor.forClass(List.class);
        verify(client, times(2)).complete(anyString(), captor.capture());
        // 2차 호출의 대화: user(원본) → assistant(잘못된 응답) → user(정정 지시).
        List<Map<String, String>> second = captor.getValue();
        assertThat(second).hasSize(3);
        assertThat(second.get(1)).containsEntry("role", "assistant")
                .containsEntry("content", "not json at all");
        assertThat(second.get(2).get("role")).isEqualTo("user");
        assertThat(second.get(2).get("content")).contains("Return ONLY the JSON object");
    }

    @Test
    void 정정_1회까지_실패하면_빈_결과() {
        when(client.complete(anyString(), anyList()))
                .thenReturn("{\"verified\": true}")
                .thenReturn("still broken");

        Optional<VerificationResponse> r = verifier().verify(input());

        assertThat(r).isEmpty();
        verify(client, times(2)).complete(anyString(), anyList());
        verifyNoMoreInteractions(client);
    }

    @Test
    void 전송_실패는_삼키지_않고_전파한다() {
        when(client.complete(anyString(), anyList()))
                .thenThrow(new UpstreamUnavailableException("GATEWAY 검증 호출 불가", new RuntimeException("503")));

        assertThatThrownBy(() -> verifier().verify(input()))
                .isInstanceOf(UpstreamUnavailableException.class);
    }

    @Test
    void user_메시지에_GDELT_컨텍스트와_후보가_담긴다() {
        String msg = LlmVerifier.buildUserMessage(input());
        assertThat(msg).contains("## News co-mention context")
                .contains("NextEra Energy, Duke Energy")
                .contains("Ticker: NEE");
    }

    @Test
    void GDELT_컨텍스트가_비면_none_available_로_표기() {
        LlmVerifier.Input noGdelt = new LlmVerifier.Input("issue", "", "Name", "TCK", "summary");
        assertThat(LlmVerifier.buildUserMessage(noGdelt)).contains("(none available)");
    }
}
