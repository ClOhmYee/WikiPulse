package io.wikipulse.backend.matching;

/**
 * LLM 응답이 검증 스키마(v1)를 어겼다는 신호 (WP-68). JSON 파싱 실패도 포함한다.
 *
 * <p>전송 실패({@link UpstreamUnavailableException})와는 다른 축이다 — 전송은 성공했으나 내용이
 * 계약을 안 지킨 경우다. {@link LlmVerifier} 가 정정 재요청 1회로 흡수를 시도하고(-45), 그래도
 * 남으면 {@code attempt_count} 를 올린다(-50). 회로·재시도(-66) 대상이 아니다.
 */
public class SchemaViolationException extends RuntimeException {

    public SchemaViolationException(String message) {
        super(message);
    }
}
