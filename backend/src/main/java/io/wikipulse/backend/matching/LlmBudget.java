package io.wikipulse.backend.matching;

import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Component;

/**
 * 하루에 쓸 수 있는 LLM 호출 수를 묶는다 (WP-191).
 *
 * <h2>이미 있던 상한들과 축이 다르다</h2>
 * <ul>
 *   <li>{@code top-per-snapshot} (-165·-176) — <b>스냅샷당</b> 몇 개를 고르나</li>
 *   <li>{@code summary.max-attempts} (-182) — <b>클러스터당</b> 몇 번 시도하나</li>
 *   <li><b>이 클래스</b> — <b>하루에</b> 몇 번 부르나</li>
 * </ul>
 *
 * <p>셋 다 필요하다. 2026-09-22 에 51분간 5,414 크레딧이 나갔을 때 앞의 둘은 켜져 있었다 —
 * 같은 클러스터를 반복해 집는 경로였고, 그건 -182 가 막았다. 총량 상한이 있었으면 그
 * 경로가 살아 있었어도 상한만큼만 샜다.
 *
 * <h2>🔴 카운터는 DB 에 둔다</h2>
 * 프로세스 메모리에 두면 백엔드 재배포마다 그 날 예산이 초기화된다. develop 머지가 곧
 * 배포라 하루에도 여러 번 돈다 — 상한이 있으나 마나가 된다.
 *
 * <h2>🔴 증가와 검사를 한 문장으로 한다</h2>
 * 읽고 나서 쓰면 폴러 둘이 같은 순간에 통과한다. {@code ON CONFLICT ... WHERE} 로 상한
 * 미만일 때만 증가시키고, 증가된 행이 안 돌아오면 초과다.
 *
 * <h2>호출 수인 이유</h2>
 * 크레딧으로 묶으려면 GATEWAY {@code key-info} 를 주기적으로 읽어야 하는데 그 값은 지연되고
 * 소액 호출은 델타가 0 으로 반올림된다(-170 실측). 호출 수는 원자적으로 셀 수 있다.
 * ⚠️ 대신 단가가 모델마다 다르다 — 환산은 {@link CandidateProperties.Budget} 주석에 적었다.
 */
@Component
public class LlmBudget {

    private static final Logger log = LoggerFactory.getLogger(LlmBudget.class);

    /** 예산을 나누는 축. DB {@code llm_daily_usage.kind} 의 CHECK 와 같은 값이어야 한다. */
    public static final String SUMMARY = "summary";
    public static final String VERIFICATION = "verification";

    private final NamedParameterJdbcTemplate jdbc;
    private final CandidateProperties props;

    public LlmBudget(NamedParameterJdbcTemplate jdbc, CandidateProperties props) {
        this.jdbc = jdbc;
        this.props = props;
    }

    /**
     * 호출 하나를 예산에서 깎는다.
     *
     * @throws BudgetExceededException 오늘 이 종류의 예산을 다 썼을 때. 🔴 전송 실패와
     *     구분되는 별개 예외다 — 그 이유는 {@link BudgetExceededException} 참고
     */
    public void consume(String kind) {
        int limit = limitFor(kind);
        if (limit <= 0) {
            // 0 이하 = 무제한. ⚠️ 기본값으로 쓰지 않는다 — 이 이슈 이전 동작이다.
            return;
        }
        Integer calls = consumeOrNull(kind, limit);
        if (calls == null) {
            log.warn("예산 초과 — {} 호출을 건너뛴다 (상한 {}회/일, UTC 기준). "
                     + "전송 실패가 아니라 우리가 멈춘 것이다.", kind, limit);
            throw new BudgetExceededException(kind, limit);
        }
        if (calls == limit || calls % 25 == 0) {
            log.info("LLM 예산 {} {}/{}회 (UTC 오늘)", kind, calls, limit);
        }
    }

    /**
     * 오늘 쓴 호출 수. 운영 확인·테스트용이며 판정에는 쓰지 않는다
     * (판정은 {@link #consume} 한 문장 안에서 원자적으로 한다).
     */
    public int usedToday(String kind) {
        List<Integer> rows = jdbc.queryForList("""
                SELECT calls FROM llm_daily_usage
                 WHERE usage_date = (now() AT TIME ZONE 'UTC')::date AND kind = :kind
                """, new MapSqlParameterSource("kind", kind), Integer.class);
        return rows.isEmpty() ? 0 : rows.get(0);
    }

    private int limitFor(String kind) {
        CandidateProperties.Budget budget = props.getBudget();
        return SUMMARY.equals(kind) ? budget.getSummaryCalls() : budget.getVerificationCalls();
    }

    /**
     * 상한 미만이면 1 증가시키고 증가 후 값을, 이미 상한이면 {@code null} 을 돌려준다.
     *
     * <p>🔴 <b>날짜는 DB 가 UTC 로 정한다.</b> 애플리케이션 시계로 정하면 서버 시간대에 따라
     * 리셋 경계가 달라진다 — "하루"의 뜻이 환경마다 갈리면 상한이 새는지 조이는지 알 수 없다.
     *
     * <p>⚠️ {@code ON CONFLICT ... DO UPDATE ... WHERE} 는 조건이 거짓이면 <b>아무 행도
     * 돌려주지 않는다</b>(충돌 행을 갱신하지 않으므로 RETURNING 이 빈다). 그게 초과 신호다.
     */
    private Integer consumeOrNull(String kind, int limit) {
        List<Integer> rows = jdbc.queryForList("""
                INSERT INTO llm_daily_usage (usage_date, kind, calls)
                VALUES ((now() AT TIME ZONE 'UTC')::date, :kind, 1)
                ON CONFLICT (usage_date, kind) DO UPDATE
                   SET calls = llm_daily_usage.calls + 1
                 WHERE llm_daily_usage.calls < :limit
                RETURNING calls
                """, new MapSqlParameterSource()
                .addValue("kind", kind)
                .addValue("limit", limit), Integer.class);
        return rows.isEmpty() ? null : rows.get(0);
    }
}
