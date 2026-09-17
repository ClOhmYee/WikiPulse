package io.wikipulse.backend.matching;

/**
 * "호출을 완수하지 못했다"는 <b>단일 폴백 신호</b> (WP-66). 재시도 소진·하드 실패·
 * 회로 개방·레이트리밋 거부를 이 한 타입으로 정규화해 폴백에서 던진다.
 *
 * <p>🔴 폴백은 가짜 빈 벡터/빈 문자열을 반환하지 않는다 — 그러면 클러스터가 근거 경로 없이
 * 조용히 후보 0건으로 굳는다(멀티렌즈 finding#4). 대신 이 신호를 던져 호출자가 클러스터를
 * <b>미완료(PENDING)로 남겨 다음 폴에서 재시도</b>하게 한다.
 *
 * <p>스코프 경계: 이 신호는 "전송이 완수되지 못함"만 뜻한다. {@code attempt_count} 증가와
 * {@code check_state} 의 DONE/FAILED 전이는 −68 이 이 신호를 보고 판단한다 — 여기서 하지 않는다.
 */
public class UpstreamUnavailableException extends RuntimeException {

    public UpstreamUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
