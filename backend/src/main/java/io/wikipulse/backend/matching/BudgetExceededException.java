package io.wikipulse.backend.matching;

/**
 * 오늘의 LLM 호출 예산을 다 썼다 (WP-191).
 *
 * <p>🔴 <b>전송 실패가 아니다.</b> {@link UpstreamUnavailableException} 과 반드시 구분된다 —
 * 전자는 "GATEWAY 가 응답을 못 준다"(재시도하면 될 수도 있다)이고 이건 "우리가 오늘 그만
 * 쓰기로 했다"(내일까지 재시도해도 소용없다)다. 같은 예외로 뭉치면 로그에서 "왜 요약이
 * 안 붙지"를 몇 시간 뒤진다 — 지라 인수 조건 3번이 이걸 요구한다.
 *
 * <p>resilience4j 설정상 이 예외는 재시도도 회로 집계도 타지 않는다. {@code retry-exceptions}
 * 와 {@code record-exceptions} 가 허용목록 방식이라 여기 없는 예외는 자동으로 빠진다
 * (application.yml). ⚠️ 다만 {@code completeFallback} 은 {@code Throwable} 을 받으므로
 * 거기서 <b>원형 전파</b>해야 한다 — {@link IllegalStateException} 과 같은 처리다.
 */
public class BudgetExceededException extends RuntimeException {

    private final String kind;
    private final int limit;

    public BudgetExceededException(String kind, int limit) {
        super("오늘 " + kind + " LLM 예산 " + limit + "회를 다 썼다. 다음 날 리셋된다.");
        this.kind = kind;
        this.limit = limit;
    }

    public String kind() {
        return kind;
    }

    public int limit() {
        return limit;
    }
}
