package io.wikipulse.backend.matching;

/**
 * 재시도로 회복 가능한 전이성 전송 실패 (WP-66): 5xx, 연결 거부, connect/read 타임아웃,
 * 그리고 Wikipedia 의 429(레이트리밋). {@code @Retry} 의 {@code retry-exceptions} 대상.
 *
 * <p>🔴 GATEWAY 의 429 는 여기 넣지 않는다 — 공유 예산 소진 신호일 수 있어 재시도가 예산을 더 태운다.
 * GATEWAY 429 는 {@link HardUpstreamException} 이다({@link UpstreamFailures#classify} 참고).
 */
public class TransientUpstreamException extends UpstreamTransportException {

    public TransientUpstreamException(String message, Throwable cause) {
        super(message, cause);
    }
}
