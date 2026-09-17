package io.wikipulse.backend.matching;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.Set;

/**
 * LLM 검증 응답 (WP-45 스키마 v1, ai/llm-verify-poc/schema/verify_response_v1.json).
 *
 * <p>{@code issueClass} 는 판정 전 강제 분류 게이트(SINGLE_COMPANY_EVENT 에서 이슈 텍스트에 없는
 * 경쟁사를 배경지식만으로 통과시키는 오탐 차단)라 항상 채우지만 <b>저장하지 않는다</b> —
 * cluster_stock 에 컬럼이 없다. {@code confidence} 는 V5 에 컬럼이 생겨 저장한다(-50).
 * {@code rationaleEn} 은 감사·로그용, {@code rationaleKo} 만 화면(cluster_stock.rationale)에 넣는다.
 *
 * <p>{@code verified=false} 면 match_path·confidence·rationale 전부 null — 억지 연결 방지.
 */
public record VerificationResponse(
        String issueClass,
        boolean verified,
        String matchPath,
        String confidence,
        String rationaleEn,
        String rationaleKo) {

    static final Set<String> REQUIRED_KEYS = Set.of(
            "issue_class", "verified", "match_path", "confidence", "rationale_en", "rationale_ko");
    static final Set<String> ISSUE_CLASSES = Set.of("SINGLE_COMPANY_EVENT", "SECTOR_OR_REGION_EVENT");
    static final Set<String> MATCH_PATHS = Set.of(
            "DIRECT_MENTION", "PRODUCT_INDUSTRY", "SUPPLY_CHAIN", "REGION");
    static final Set<String> CONFIDENCES = Set.of("strong", "weak");

    /**
     * 파싱된 JSON 을 스키마(v1)로 검증하고 매핑한다. POC {@code verify_experiment.validate} 규칙을
     * 그대로 옮긴다: 정확히 6키, issue_class 필수·enum, verified=true 면 네 필드 non-null·enum·비지 않음,
     * verified=false 면 네 필드 전부 null.
     *
     * @return 유효하면 응답, 스키마 위반이면 사유를 담은 예외를 던진다
     * @throws SchemaViolationException 스키마 위반
     */
    static VerificationResponse fromJson(JsonNode node) {
        if (node == null || !node.isObject()) {
            throw new SchemaViolationException("object 아님");
        }
        Set<String> keys = fieldNames(node);
        if (!keys.equals(REQUIRED_KEYS)) {
            throw new SchemaViolationException("키 불일치: " + keys);
        }
        String issueClass = node.get("issue_class").asText(null);
        if (!ISSUE_CLASSES.contains(issueClass)) {
            throw new SchemaViolationException("issue_class 값 이상: " + issueClass);
        }
        JsonNode verifiedNode = node.get("verified");
        if (!verifiedNode.isBoolean()) {
            throw new SchemaViolationException("verified 가 boolean 아님");
        }
        boolean verified = verifiedNode.asBoolean();

        JsonNode matchPathNode = node.get("match_path");
        JsonNode confidenceNode = node.get("confidence");
        JsonNode rationaleEnNode = node.get("rationale_en");
        JsonNode rationaleKoNode = node.get("rationale_ko");

        if (verified) {
            String matchPath = asTextOrNull(matchPathNode);
            String confidence = asTextOrNull(confidenceNode);
            if (!MATCH_PATHS.contains(matchPath)) {
                throw new SchemaViolationException("match_path 값 이상: " + matchPath);
            }
            if (!CONFIDENCES.contains(confidence)) {
                throw new SchemaViolationException("confidence 값 이상: " + confidence);
            }
            String rationaleEn = requireNonBlank(rationaleEnNode, "rationale_en");
            String rationaleKo = requireNonBlank(rationaleKoNode, "rationale_ko");
            return new VerificationResponse(
                    issueClass, true, matchPath, confidence, rationaleEn, rationaleKo);
        }
        if (!matchPathNode.isNull() || !confidenceNode.isNull()
                || !rationaleEnNode.isNull() || !rationaleKoNode.isNull()) {
            throw new SchemaViolationException("verified=false 인데 나머지 필드가 null 아님");
        }
        return new VerificationResponse(issueClass, false, null, null, null, null);
    }

    private static Set<String> fieldNames(JsonNode node) {
        java.util.Set<String> names = new java.util.HashSet<>();
        node.fieldNames().forEachRemaining(names::add);
        return names;
    }

    private static String asTextOrNull(JsonNode node) {
        return node == null || node.isNull() ? null : node.asText();
    }

    private static String requireNonBlank(JsonNode node, String field) {
        if (node == null || !node.isTextual() || node.asText().isBlank()) {
            throw new SchemaViolationException(field + " 비어있음");
        }
        return node.asText();
    }
}
