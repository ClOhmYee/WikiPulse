package io.wikipulse.backend.matching;

/**
 * 외부 게이트웨이 호출의 <b>전송 계층</b> 실패 (WP-66). 서킷브레이커가 게이트웨이 건강을
 * 판정하는 기준 — 이 타입만 회로에 기록한다({@code record-exceptions}).
 *
 * <p>스코프 경계: 응답 스키마 검증(2xx 본문 파싱)·{@code attempt_count}·{@code check_state}
 * 전이는 −68 몫이며 여기서 다루지 않는다. 200 인데 본문이 어긋난 경우는 이 타입이 아니라
 * 기존 {@link IllegalStateException}(−68 소관) 그대로 둔다.
 *
 * @see TransientUpstreamException 재시도로 회복 가능
 * @see HardUpstreamException 재시도 무의미 — 회로만 연다
 */
public abstract class UpstreamTransportException extends RuntimeException {

    protected UpstreamTransportException(String message, Throwable cause) {
        super(message, cause);
    }
}
