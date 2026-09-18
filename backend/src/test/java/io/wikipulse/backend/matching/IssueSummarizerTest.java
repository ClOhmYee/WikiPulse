package io.wikipulse.backend.matching;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * 요약기 (WP-119). 전송 이음매({@link GatewayVerificationClient})는 목이라 네트워크 없이
 * 파싱·게이트·정정 재요청·전송 실패 전파를 본다. 🔴 실 GATEWAY 호출 0.
 */
@ExtendWith(MockitoExtension.class)
class IssueSummarizerTest {

    @Mock
    GatewayVerificationClient client;

    IssueSummarizer summarizer() {
        return new IssueSummarizer(client, new ObjectMapper());
    }

    private static final String OK = """
            {"sufficient_context":true,"summary_ko":"이란-이스라엘 무력 충돌이 격화됐다."}
            """;

    private IssueSummarizer.Input input() {
        return new IssueSummarizer.Input("Iran: ...", "Reuters, Israel Defense Forces");
    }

    @Test
    void 근거_충분하면_한국어_요약을_돌려준다() {
        when(client.completeForSummary(anyString(), anyList())).thenReturn(OK);

        Optional<String> r = summarizer().summarize(input());

        assertThat(r).contains("이란-이스라엘 무력 충돌이 격화됐다.");
        verify(client, times(1)).completeForSummary(anyString(), anyList());
    }

    @Test
    void 코드펜스로_감싸도_파싱한다() {
        when(client.completeForSummary(anyString(), anyList())).thenReturn("```json\n" + OK + "\n```");

        assertThat(summarizer().summarize(input())).isPresent();
    }

    @Test
    void 근거_부족이면_빈_결과다_저장하지_않는다() {
        // 🔴 할루시네이션 게이트: sufficient_context=false 면 요약을 저장하지 않도록 빈 결과.
        when(client.completeForSummary(anyString(), anyList()))
                .thenReturn("{\"sufficient_context\":false,\"summary_ko\":null}");

        Optional<String> r = summarizer().summarize(input());

        assertThat(r).isEmpty();
        // 게이트 응답은 정상 스키마라 정정 재요청 없이 한 번만 호출한다.
        verify(client, times(1)).completeForSummary(anyString(), anyList());
    }

    @Test
    void 스키마_위반이면_정정_1회_후_성공하면_통과() {
        when(client.completeForSummary(anyString(), anyList()))
                .thenReturn("{\"summary_ko\":\"요약\"}")  // 1차: 키 불일치
                .thenReturn(OK);                          // 정정 후: 통과

        assertThat(summarizer().summarize(input())).isPresent();
        verify(client, times(2)).completeForSummary(anyString(), anyList());
    }

    @Test
    void 정정_1회까지_실패하면_빈_결과() {
        when(client.completeForSummary(anyString(), anyList()))
                .thenReturn("not json")
                .thenReturn("still broken");

        assertThat(summarizer().summarize(input())).isEmpty();
        verify(client, times(2)).completeForSummary(anyString(), anyList());
    }

    @Test
    void 전송_실패는_삼키지_않고_전파한다() {
        when(client.completeForSummary(anyString(), anyList()))
                .thenThrow(new UpstreamUnavailableException("GATEWAY 요약 호출 불가", new RuntimeException("503")));

        assertThatThrownBy(() -> summarizer().summarize(input()))
                .isInstanceOf(UpstreamUnavailableException.class);
    }

    @Test
    void user_메시지에_대표텍스트와_GDELT_기관명이_담긴다() {
        String msg = IssueSummarizer.buildUserMessage(input());
        assertThat(msg).contains("## Issue")
                .contains("Iran: ...")
                .contains("## News co-mention context")
                .contains("Reuters, Israel Defense Forces");
    }

    @Test
    void GDELT_컨텍스트가_비면_none_available_로_표기() {
        IssueSummarizer.Input noGdelt = new IssueSummarizer.Input("issue", "");
        assertThat(IssueSummarizer.buildUserMessage(noGdelt)).contains("(none available)");
    }
}
