package io.wikipulse.backend.matching;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

/** 워커 대상 스냅샷 날짜 설정 (WP-215). */
class SnapshotDaysTest {

    @Test
    void 빈_값은_한정_없음이다() {
        // 미설정 환경변수는 빈 문자열로 들어온다 — 기존 동작(전체)이어야 한다
        assertThat(SnapshotDays.toSqlArray(null)).isNull();
        assertThat(SnapshotDays.toSqlArray("")).isNull();
        assertThat(SnapshotDays.toSqlArray("  ")).isNull();
        assertThat(SnapshotDays.toSqlArray(" , ")).isNull();
    }

    @Test
    void 쉼표_구분_날짜를_배열_리터럴로() {
        assertThat(SnapshotDays.toSqlArray("2026-07-17, 2026-07-25"))
                .isEqualTo("{2026-07-17,2026-07-25}");
    }

    @Test
    void 틀린_형식은_조용히_무시하지_않고_터진다() {
        // 🔴 무시하면 설정이 안 먹은 채 전체 대상으로 돌아 크레딧이 샌다
        assertThatThrownBy(() -> SnapshotDays.toSqlArray("2026-7-17"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> SnapshotDays.toSqlArray("07/17/2026"))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
