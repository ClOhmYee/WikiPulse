package io.wikipulse.backend.matching;

import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.List;

/**
 * 워커 대상 스냅샷 날짜 설정을 SQL 파라미터로 바꾼다 (WP-215).
 *
 * <p>설정값은 쉼표 구분 <b>UTC 날짜</b>다 — {@code 2026-07-17,2026-07-25}. {@code snapshot_ts} 가
 * UTC 라 날짜도 UTC 로 자른다. KST 로 읽으면 하루 경계가 9시간 밀려 전날 밤 스냅샷이 섞인다.
 *
 * <p>빈 값은 "한정 없음"(NULL)이다 — 미설정 환경변수가 빈 문자열로 들어오기 때문이다
 * ({@code source} 와 같은 관습).
 *
 * <p>🔴 형식이 틀리면 <b>기동 시점이 아니라 첫 폴에서</b> 예외가 난다. 조용히 무시하면 설정이
 * 안 먹은 채 전체 대상으로 돌아 크레딧이 새므로, 틀린 값은 반드시 터뜨린다.
 */
final class SnapshotDays {

    private SnapshotDays() {
    }

    /**
     * @return PostgreSQL 배열 리터럴({@code {2026-07-17,2026-07-25}}). 빈 설정이면 {@code null}
     * @throws IllegalArgumentException 날짜 형식이 틀렸을 때
     */
    static String toSqlArray(String config) {
        if (config == null || config.isBlank()) {
            return null;
        }
        List<String> days = new ArrayList<>();
        for (String raw : config.split(",")) {
            String day = raw.strip();
            if (day.isEmpty()) {
                continue;
            }
            try {
                days.add(LocalDate.parse(day).toString());
            } catch (DateTimeParseException e) {
                throw new IllegalArgumentException(
                        "snapshot-days 형식이 틀렸다 (YYYY-MM-DD 쉼표 구분, UTC): " + config, e);
            }
        }
        return days.isEmpty() ? null : "{" + String.join(",", days) + "}";
    }
}
