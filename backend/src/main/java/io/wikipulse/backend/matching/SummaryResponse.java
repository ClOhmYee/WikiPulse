package io.wikipulse.backend.matching;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.Set;

/**
 * 이슈 요약 LLM 응답 (WP-119, 프롬프트 llm/summary_system_v1.txt).
 *
 * <p>{@code sufficientContext} 는 판정 전 강제 게이트다. 모델이 근거 부족을 <b>정직하게</b>
 * {@code sufficient_context=false} 로 신고하면 {@code summaryKo} 가 null 이라 호출자가
 * <b>저장하지 않는다</b> — "설명할 수 없다"는 거부 문장이 요약으로 저장되는 실패 모드
 * (ai/issue-text-poc/RESULT.md ②)를 구조적으로 막는다.
 *
 * <p>⚠️ 다만 이 게이트가 막는 것은 <b>정직-불충분 신고 경로뿐</b>이다. 모델이
 * {@code sufficient_context=true} 로 신고하면서 입력에 없는 사실을 지어내면(RESULT.md ③) 스키마를
 * 통과해 그대로 저장된다 — 이 경로의 방어는 구조가 아니라 프롬프트의 GROUNDING RULE
 * (llm/summary_system_v1.txt)이다. {@link VerificationResponse} 의 {@code issueClass} 는 enum 강제
 * 분류라 프롬프트 로직이 오탐을 실제로 차단하는 반면, 여기 {@code sufficientContext} 는 모델
 * 자기신고 boolean 이라 지어냄에 대한 실질 방어력은 프롬프트에 의존한다.
 *
 * <p>🔴 요약만 한국어다(사용자 노출). 파이프라인 내부 텍스트는 영어 유지(명세 §6.2, CLAUDE.md 폐기 절).
 */
public record SummaryResponse(boolean sufficientContext, String summaryKo) {

    static final Set<String> REQUIRED_KEYS = Set.of("sufficient_context", "summary_ko");

    /**
     * 파싱된 JSON 을 스키마(v1)로 검증하고 매핑한다: 정확히 2키, sufficient_context 는 boolean 필수,
     * true 면 summary_ko 는 non-null·비지 않음, false 면 summary_ko 는 null.
     *
     * @throws SchemaViolationException 스키마 위반
     */
    static SummaryResponse fromJson(JsonNode node) {
        if (node == null || !node.isObject()) {
            throw new SchemaViolationException("object 아님");
        }
        Set<String> keys = fieldNames(node);
        if (!keys.equals(REQUIRED_KEYS)) {
            throw new SchemaViolationException("키 불일치: " + keys);
        }
        JsonNode sufficientNode = node.get("sufficient_context");
        if (!sufficientNode.isBoolean()) {
            throw new SchemaViolationException("sufficient_context 가 boolean 아님");
        }
        boolean sufficient = sufficientNode.asBoolean();

        JsonNode summaryNode = node.get("summary_ko");
        if (sufficient) {
            if (summaryNode == null || !summaryNode.isTextual() || summaryNode.asText().isBlank()) {
                throw new SchemaViolationException("sufficient_context=true 인데 summary_ko 가 비어있음");
            }
            return new SummaryResponse(true, summaryNode.asText());
        }
        if (summaryNode == null || !summaryNode.isNull()) {
            throw new SchemaViolationException("sufficient_context=false 인데 summary_ko 가 null 아님");
        }
        return new SummaryResponse(false, null);
    }

    private static Set<String> fieldNames(JsonNode node) {
        java.util.Set<String> names = new java.util.HashSet<>();
        node.fieldNames().forEachRemaining(names::add);
        return names;
    }
}
