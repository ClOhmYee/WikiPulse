package io.wikipulse.backend.matching;

import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.RestClientException;

/**
 * RestClient 예외를 −66 실패 taxonomy 로 번역한다 (전송 계층만). HTTP 상태·전송 오류로만 가른다 —
 * 2xx 본문 파싱(스키마 검증)은 −68 몫이라 여기서 하지 않는다.
 *
 * <p>재시도 정책이 게이트웨이마다 갈리는 유일한 축은 429다:
 * <ul>
 *   <li>Wikipedia({@code retry429=true}): 429 = 전이성(예절 백오프 후 재시도).</li>
 *   <li>GATEWAY({@code retry429=false}): 429 = 하드(공유 예산 소진 신호일 수 있어 재시도가 예산을 더 태운다).</li>
 *   <li>Azure Translator({@code retry429=false}): 429 = 하드. F0 는 쿼터 초과도 429 로 오므로
 *       재시도하면 남은 월 쿼터를 더 태운다 — GATEWAY 와 같은 이유다.</li>
 * </ul>
 *
 * <p>⚠️ ~~package-private~~ → public (2026-09-23, WP-205). {@code page} 패키지의
 *    Azure 클라이언트가 두 번째 게이트웨이로 붙었다. 분류 규칙을 복제하면 429 취급처럼
 *    게이트웨이마다 갈리는 축이 두 벌로 갈라져 조용히 어긋난다 — 한 곳에 둔다.
 */
public final class UpstreamFailures {

    private UpstreamFailures() {
    }

    /**
     * @param gateway  로그용 게이트웨이 이름("GATEWAY"·"Wikipedia")
     * @param e        RestClient 가 던진 전송 예외
     * @param retry429 429 를 전이성으로 볼지(Wikipedia) 하드로 볼지(GATEWAY·Azure)
     */
    public static UpstreamTransportException classify(String gateway, RestClientException e, boolean retry429) {
        if (e instanceof HttpStatusCodeException h) {
            int status = h.getStatusCode().value();
            if (status >= 500) {
                return new TransientUpstreamException(gateway + " " + status + " (5xx 전이성)", e);
            }
            if (status == 429) {
                return retry429
                        ? new TransientUpstreamException(gateway + " 429 (레이트리밋, 재시도)", e)
                        : new HardUpstreamException(gateway + " 429 (공유 예산 소진 신호, 재시도 안 함)", e);
            }
            if (status == 401 || status == 403 || status == 402) {
                return new HardUpstreamException(gateway + " " + status + " (인증/키/쿼터)", e);
            }
            return new HardUpstreamException(gateway + " " + status + " (비재시도 4xx)", e);
        }
        // ResourceAccessException 등 상태 없는 전송 오류: 연결 거부·connect/read 타임아웃 → 전이성.
        return new TransientUpstreamException(
                gateway + " 전송 오류 (" + e.getClass().getSimpleName() + ")", e);
    }
}
