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
 * 이슈 클러스터 하나를 한국어로 요약한다 (WP-119).
 *
 * <p>흐름: 시스템 프롬프트(리소스 고정) + user 메시지(영어 대표 텍스트 + GDELT 기관명 컨텍스트) →
 * {@link GatewayVerificationClient} 전송 → JSON 파싱·스키마 검증({@link SummaryResponse#fromJson}).
 * 스키마 위반이면 <b>같은 대화에 정정 요청 1회</b> 추가(-45 규칙과 동일), 그래도 실패하면 빈 결과.
 *
 * <p>🔴 <b>-66/-68 위에 얹는다 — 새 신뢰성 계층·새 GATEWAY 클라이언트를 만들지 않는다.</b>
 * {@link GatewayVerificationClient#complete}(named instance {@code gateway} 의 범용 Anthropic Messages 전송)를
 * {@link LlmVerifier} 와 <b>공유</b>한다. 전송 실패({@link UpstreamUnavailableException})는 여기서 잡지
 * 않고 그대로 전파해 호출자가 클러스터를 미확정(VERIFYING)으로 남기게 한다.
 *
 * <p>🔴 요약 입력은 영어 대표 텍스트 + GDELT <b>기관명</b>뿐이다. GDELT 테마·지역은 넣지 않는다
 * (기사 필터 술어 전용, 지라 계약). 요약 출력만 한국어다(사용자 노출).
 *
 * <p>할루시네이션 차단은 두 겹이다: (1) 근거 부족을 정직하게 신고한 경우
 * ({@link SummaryResponse#sufficientContext}=false)는 {@link #summarize} 가 빈 결과를 돌려줘
 * 저장을 건너뛴다(거부 문장 저장 방지 — 구조적). (2) 입력에 없는 사실을 지어내는 경우는
 * 프롬프트의 GROUNDING RULE 로 완화한다(구조가 아닌 프롬프트 의존 — {@link SummaryResponse} 참고).
 */
@Component
public class IssueSummarizer {

    private static final Logger log = LoggerFactory.getLogger(IssueSummarizer.class);

    /** 🔴 런타임에 ai/ 폴더를 참조하지 않는다 — 프롬프트는 백엔드 리소스로 가져왔다. */
    static final String PROMPT_VERSION = "summary_v1";
    private static final String PROMPT_RESOURCE = "llm/summary_system_v1.txt";

    private final GatewayVerificationClient client;
    private final ObjectMapper mapper;
    private final String systemPrompt;

    public IssueSummarizer(GatewayVerificationClient client, ObjectMapper mapper) {
        this.client = client;
        this.mapper = mapper;
        this.systemPrompt = loadPrompt();
    }

    /** 요약할 클러스터 하나의 입력. issueText 는 영어 대표 텍스트, gdeltContext 는 기관명 나열. */
    public record Input(String issueText, String gdeltContext) {
    }

    /**
     * 요약이 저장되지 못한 이유 (WP-182).
     *
     * <p>🔴 <b>둘을 구분해야 한다.</b> 둘 다 "저장 안 함"으로 끝나지만 원인과 대책이 다르다 —
     * 근거 부족은 대표 텍스트가 빈약해서 모델이 정직하게 거절한 것이고(입력을 고쳐야 풀린다),
     * 스키마 위반은 프롬프트·모델 문제다. 원장에 같은 값으로 남기면 나중에 구분할 수 없다.
     *
     * <p>전송 실패는 여기 없다 — 그건 {@link UpstreamUnavailableException} 으로 전파되고
     * 재시도해야 하는 일시 장애다.
     */
    public enum Failure {
        /** 요약 성공. */
        NONE,
        /** 모델이 {@code sufficient_context=false} 로 근거 부족을 신고했다. */
        INSUFFICIENT_CONTEXT,
        /** 정정 1회 후에도 응답이 스키마를 지키지 않았다. */
        SCHEMA_VIOLATION
    }

    /** 요약 결과. {@code summary} 가 비면 {@code failure} 가 왜 비었는지 말한다. */
    public record Outcome(Optional<String> summary, Failure failure) {

        static Outcome ok(String summaryKo) {
            return new Outcome(Optional.of(summaryKo), Failure.NONE);
        }

        static Outcome failed(Failure failure) {
            return new Outcome(Optional.empty(), failure);
        }
    }

    /**
     * 클러스터를 요약한다.
     *
     * @return 근거가 충분하고 스키마를 지킨 한국어 요약. 근거 부족(sufficient_context=false)이거나
     *     정정 1회까지도 스키마 위반이면 빈 요약 + 그 이유({@link Failure}) — 호출자는 저장하지
     *     않고 <b>시도를 원장에 남겨</b> 무한 재시도를 끊는다 (WP-182)
     * @throws UpstreamUnavailableException 전송 실패 (-66) — 호출자가 미확정 유지로 처리
     */
    public Outcome summarize(Input input) {
        List<Map<String, String>> messages = new ArrayList<>();
        messages.add(message("user", buildUserMessage(input)));

        for (int attempt = 0; attempt < 2; attempt++) {
            String raw = client.completeForSummary(systemPrompt, messages); // 전송 실패는 전파
            try {
                JsonNode node = mapper.readTree(LlmVerifier.stripFences(raw));
                SummaryResponse resp = SummaryResponse.fromJson(node);
                if (!resp.sufficientContext()) {
                    log.info("요약 근거 부족 — 저장 건너뜀 (sufficient_context=false)");
                    return Outcome.failed(Failure.INSUFFICIENT_CONTEXT);
                }
                return Outcome.ok(resp.summaryKo());
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
        log.warn("요약 스키마 위반 — 정정 1회 후에도 실패");
        return Outcome.failed(Failure.SCHEMA_VIOLATION);
    }

    private void appendCorrection(List<Map<String, String>> messages, String rawAssistant, String problem) {
        messages.add(message("assistant", rawAssistant));
        messages.add(message("user",
                "That response was invalid (" + problem + "). "
                        + "Return ONLY the JSON object matching the schema, nothing else."));
    }

    /** 대표 텍스트 + GDELT 기관명 컨텍스트. GDELT 컨텍스트가 비면 "(none available)". */
    static String buildUserMessage(Input in) {
        String context = in.gdeltContext() == null || in.gdeltContext().isBlank()
                ? "(none available)" : in.gdeltContext();
        return "## Issue\n" + nullToEmpty(in.issueText()) + "\n\n"
                + "## News co-mention context\n" + context + "\n\n"
                + "Write the Korean summary following the rules in the system prompt. "
                + "Output only the JSON object.";
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
                throw new IllegalStateException("요약 시스템 프롬프트가 비어 있다: " + PROMPT_RESOURCE);
            }
            return text;
        } catch (IOException e) {
            throw new UncheckedIOException("요약 시스템 프롬프트를 못 읽었다: " + PROMPT_RESOURCE, e);
        }
    }
}
