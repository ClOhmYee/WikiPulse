package io.wikipulse.backend.matching;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Component;
import org.springframework.util.StreamUtils;

/**
 * 후보 하나를 LLM 으로 검증한다 (WP-68, 계약은 -45 · ai/llm-verify-poc).
 *
 * <p>흐름: 시스템 프롬프트(리소스 고정) + user 메시지(이슈 텍스트 + GDELT 컨텍스트 + 후보) →
 * {@link GatewayVerificationClient} 전송 → JSON 파싱·스키마 검증({@link VerificationResponse#fromJson}).
 * 스키마 위반이면 <b>같은 대화에 정정 요청 1회</b> 추가(-45 규칙), 그래도 실패하면 빈 결과.
 *
 * <p>🔴 이 재시도는 -66 전송 재시도와 다른 축이다. 전송 실패({@link UpstreamUnavailableException})는
 * 여기서 잡지 않고 그대로 전파해 오케스트레이터가 후보를 PENDING 으로 남기게 한다(-50). 여기서
 * 다루는 건 "전송은 됐는데 스키마를 안 지킨" 경우뿐이다.
 */
@Component
public class LlmVerifier {

    private static final Logger log = LoggerFactory.getLogger(LlmVerifier.class);

    /** 🔴 런타임에 ai/ 폴더를 참조하지 않는다 — 프롬프트는 백엔드 리소스로 가져왔다(-68). */
    static final String PROMPT_VERSION = "v1";
    private static final String PROMPT_RESOURCE = "llm/verify_system_" + PROMPT_VERSION + ".txt";

    private final GatewayVerificationClient client;
    private final ObjectMapper mapper;
    private final String systemPrompt;
    private final CandidateProperties props;

    public LlmVerifier(
            GatewayVerificationClient client, ObjectMapper mapper, CandidateProperties props) {
        this.client = client;
        this.mapper = mapper;
        this.props = props;
        this.systemPrompt = loadPrompt();
    }

    /**
     * 판정 재사용 키에 쓸 버전 문자열 (WP-172).
     *
     * <p>🔴 <b>프롬프트 버전만으로는 부족하다.</b> 같은 프롬프트라도 모델이 다르면 다른 판정이
     * 나온다 — 실측에서 Sonnet 은 Milton 노이즈 3개를 통과시켰고 nano 는 0개였다. 모델을 바꿨는데
     * 버전이 그대로면 <b>옛 모델의 판정이 조용히 재사용</b>된다.
     *
     * <p>{@code issue_report.model} 이 모델+프롬프트버전을 한 문자열로 담는 것과 같은 방식이다
     * ({@link IssueSummaryService} {@code modelTag}) — 새 컬럼·마이그레이션 없이 같은 의도를 이룬다.
     *
     * @return 예: {@code "v1+gpt-5.4-nano"}
     */
    String verdictVersion() {
        return PROMPT_VERSION + "+" + props.getGateway().getVerificationModel();
    }

    /** 검증할 후보 한 건의 입력. issueText·gdeltContext 는 클러스터 단위로 한 번 만들어 공유된다. */
    public record Input(
            String issueText, String gdeltContext, String name, String ticker, String summary) {
    }

    /**
     * 후보를 검증한다.
     *
     * @return 스키마를 지킨 판정. 정정 1회까지도 스키마 위반이면 {@link Optional#empty()}
     * @throws UpstreamUnavailableException 전송 실패 (-66) — 호출자가 PENDING 유지로 처리
     */
    public Optional<VerificationResponse> verify(Input input) {
        List<Map<String, String>> messages = new ArrayList<>();
        messages.add(message("user", buildUserMessage(input)));

        for (int attempt = 0; attempt < 2; attempt++) {
            String raw = client.complete(systemPrompt, messages); // 전송 실패는 전파
            try {
                JsonNode node = mapper.readTree(stripFences(raw));
                return Optional.of(VerificationResponse.fromJson(node));
            } catch (IOException e) {
                if (attempt == 0) {
                    appendCorrection(messages, raw, "JSON 파싱 실패: " + e.getMessage());
                }
            } catch (SchemaViolationException e) {
                if (attempt == 0) {
                    appendCorrection(messages, raw, e.getMessage());
                }
            }
        }
        log.warn("검증 스키마 위반 — 정정 1회 후에도 실패, 후보={} 티커={}", input.name(), input.ticker());
        return Optional.empty();
    }

    private void appendCorrection(List<Map<String, String>> messages, String rawAssistant, String problem) {
        messages.add(message("assistant", rawAssistant));
        messages.add(message("user",
                "That response was invalid (" + problem + "). "
                        + "Return ONLY the JSON object matching the schema, nothing else."));
    }

    /** POC build_user_message 와 동일 포맷. GDELT 컨텍스트가 비면 "(none available)". */
    static String buildUserMessage(Input in) {
        String context = in.gdeltContext() == null || in.gdeltContext().isBlank()
                ? "(none available)" : in.gdeltContext();
        return "## Issue\n" + nullToEmpty(in.issueText()) + "\n\n"
                + "## News co-mention context\n" + context + "\n\n"
                + "## Candidate company\n"
                + "Name: " + nullToEmpty(in.name()) + "\n"
                + "Ticker: " + nullToEmpty(in.ticker()) + "\n"
                + "Business description: " + nullToEmpty(in.summary()) + "\n\n"
                + "Decide whether this candidate is verified as related to the issue above, "
                + "following the rules in the system prompt. Output only the JSON object.";
    }

    /** ```json ... ``` 펜스를 벗긴다 (POC strip_fences 이식). */
    static String stripFences(String text) {
        String t = text.strip();
        if (t.startsWith("```")) {
            int nl = t.indexOf('\n');
            t = nl >= 0 ? t.substring(nl + 1) : t;
            int fence = t.lastIndexOf("```");
            if (fence >= 0) {
                t = t.substring(0, fence);
            }
        }
        return t.strip();
    }

    private static Map<String, String> message(String role, String content) {
        return Map.of("role", role, "content", content);
    }

    private static String nullToEmpty(String s) {
        return s == null ? "" : s;
    }

    private String loadPrompt() {
        try {
            String text = StreamUtils.copyToString(
                    new ClassPathResource(PROMPT_RESOURCE).getInputStream(), StandardCharsets.UTF_8);
            if (text.isBlank()) {
                throw new IllegalStateException("검증 시스템 프롬프트가 비어 있다: " + PROMPT_RESOURCE);
            }
            return text;
        } catch (IOException e) {
            throw new UncheckedIOException("검증 시스템 프롬프트를 못 읽었다: " + PROMPT_RESOURCE, e);
        }
    }
}
