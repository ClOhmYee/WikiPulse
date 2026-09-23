package io.wikipulse.backend.matching;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

/** 워커 대상 스냅샷 한정 설정 (WP-215). */
class SnapshotDaysTest {

    @Test
    void 빈_값은_한정_없음이다() {
        // 미설정 환경변수는 빈 문자열로 들어온다 — 기존 동작(전체)이어야 한다
        for (String blank : new String[] {null, "", "  ", " , "}) {
            SnapshotDays.Scope s = SnapshotDays.parse(blank);
            assertThat(s.days()).isNull();
            assertThat(s.times()).isNull();
        }
    }

    @Test
    void 쉼표_구분_날짜를_배열_리터럴로() {
        SnapshotDays.Scope s = SnapshotDays.parse("2026-07-17, 2026-07-25");
        assertThat(s.days()).isEqualTo("{2026-07-17,2026-07-25}");
        assertThat(s.times()).isNull();
    }

    @Test
    void 시각은_UTC_스냅샷_하나로_읽는다() {
        // 🔴 이틀로 좁혀도 검증 9,400회라 시연 스냅샷만 고른다
        SnapshotDays.Scope s = SnapshotDays.parse("2026-07-17T01:00,2026-08-02T19:00");
        assertThat(s.days()).isNull();
        assertThat(s.times()).isEqualTo("{2026-07-17T01:00Z,2026-08-02T19:00Z}");
    }

    @Test
    void 날짜와_시각을_섞어_쓸_수_있다() {
        SnapshotDays.Scope s = SnapshotDays.parse("2026-07-17,2026-08-02T19:00");
        assertThat(s.days()).isEqualTo("{2026-07-17}");
        assertThat(s.times()).isEqualTo("{2026-08-02T19:00Z}");
    }

    @Test
    void 틀린_형식은_조용히_무시하지_않고_터진다() {
        // 🔴 무시하면 설정이 안 먹은 채 전체 대상으로 돌아 크레딧이 샌다
        assertThatThrownBy(() -> SnapshotDays.parse("2026-7-17"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> SnapshotDays.parse("07/17/2026"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> SnapshotDays.parse("2026-07-17T25:00"))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
