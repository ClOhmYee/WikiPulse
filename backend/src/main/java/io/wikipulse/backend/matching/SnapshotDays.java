package io.wikipulse.backend.matching;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.List;

/**
 * 워커 대상 스냅샷 한정 설정을 SQL 파라미터로 바꾼다 (WP-215).
 *
 * <p>설정값은 쉼표 구분이고 항목마다 둘 중 하나다 — 모두 <b>UTC</b> 다.
 * <ul>
 *   <li><b>날짜</b> {@code 2026-07-17} — 그날 스냅샷 전부
 *   <li><b>시각</b> {@code 2026-07-17T01:00} — 정확히 그 스냅샷 하나
 * </ul>
 * 섞어 쓸 수 있다. 🔴 시각이 필요한 이유: 이틀로 좁혀도 스냅샷 47 × 상위 10 × 후보 20 이면
 * 검증 9,400회(mini 약 30만 크레딧)다. 시연에 쓰는 스냅샷 몇 개만 채운다.
 *
 * <p>{@code snapshot_ts} 가 UTC 라 날짜·시각도 UTC 로 읽는다. KST 로 읽으면 경계가 9시간 밀린다.
 *
 * <p>빈 값은 "한정 없음"(두 배열 모두 NULL)이다 — 미설정 환경변수가 빈 문자열로 들어오기 때문이다.
 *
 * <p>🔴 형식이 틀리면 첫 폴에서 예외가 난다. 조용히 무시하면 설정이 안 먹은 채 전체 대상으로 돌아
 * 크레딧이 새므로, 틀린 값은 반드시 터뜨린다.
 */
final class SnapshotDays {

    /** 날짜·시각 두 배열. 둘 다 null 이면 한정 없음. */
    record Scope(String days, String times) {
    }

    private SnapshotDays() {
    }

    /**
     * @return 날짜 배열 리터럴(없으면 null)과 시각 배열 리터럴(없으면 null)
     * @throws IllegalArgumentException 형식이 틀렸을 때
     */
    static Scope parse(String config) {
        if (config == null || config.isBlank()) {
            return new Scope(null, null);
        }
        List<String> days = new ArrayList<>();
        List<String> times = new ArrayList<>();
        for (String raw : config.split(",")) {
            String item = raw.strip();
            if (item.isEmpty()) {
                continue;
            }
            try {
                if (item.contains("T")) {
                    // 초 없이 적어도 된다. UTC 로 고정해 오프셋을 붙인다.
                    times.add(LocalDateTime.parse(item).atOffset(ZoneOffset.UTC).toString());
                } else {
                    days.add(LocalDate.parse(item).toString());
                }
            } catch (DateTimeParseException e) {
                throw new IllegalArgumentException(
                        "snapshot-days 형식이 틀렸다 (YYYY-MM-DD 또는 YYYY-MM-DDTHH:MM, 쉼표 구분, UTC): "
                                + config, e);
            }
        }
        return new Scope(
                days.isEmpty() ? null : "{" + String.join(",", days) + "}",
                times.isEmpty() ? null : "{" + String.join(",", times) + "}");
    }
}
