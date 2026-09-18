-- WP-84: 기준선 슬롯을 요일×시간(168) -> 시간(24) 으로 바꾼다.
--
-- 왜 바꾸나 (2026-09-15 실측, 명세 §11)
--   hour_of_week 슬롯은 주에 한 번만 온다. 28일 창에서 한 슬롯의 관측이 최대 4개뿐이라
--   sample_days 가 MIN_BASELINE_SAMPLE_DAYS(7) 에 **구조적으로 도달하지 못했다** —
--   기존 문서도 항상 is_thin 으로 판정돼 z 경로가 실행되지 않았다.
--   hour_of_day 로 바꾸면 같은 슬롯이 매일 오므로 28일에 최대 28관측이 된다.
--   실덤프 재생에서 대조군 오탐이 395 -> 271 건으로 줄었고(편집자 하한과 함께 쓰면 57건),
--   대상 재현율은 변하지 않았다.
--
-- 포기하는 것
--   "위키 편집은 요일을 크게 탄다"는 168 슬롯의 원래 근거를 버린다. 평일/주말 차이는
--   이제 기준선에 흡수되지 않는다. 실측에서 그 손실보다 표본 확보 이득이 컸다.
--
-- 기존 행을 변환하지 않고 비우는 이유
--   page_baseline 은 덤프에서 재계산되는 **파생 데이터**다. 게다가 hour_of_week % 24 로
--   접으면 한 page_id 의 7개 슬롯이 같은 hour_of_day 로 몰려 PK 가 충돌한다.
--   비우고 spike.baseline_sink 로 다시 채운다.

TRUNCATE TABLE page_baseline;

ALTER TABLE page_baseline DROP CONSTRAINT page_baseline_pkey;
ALTER TABLE page_baseline DROP CONSTRAINT page_baseline_hour_of_week_check;
ALTER TABLE page_baseline RENAME COLUMN hour_of_week TO hour_of_day;

ALTER TABLE page_baseline
    ADD CONSTRAINT page_baseline_hour_of_day_check CHECK (hour_of_day BETWEEN 0 AND 23);
ALTER TABLE page_baseline ADD PRIMARY KEY (page_id, hour_of_day);

COMMENT ON TABLE page_baseline IS
    '문서 × 시간대(0~23, UTC) 기준선. 28일치를 EWMA 로 굴린다. '
    '~~요일×시간대(0~167)~~ -> 시간대(0~23) (2026-09-15, WP-84) — 주 1회 슬롯은 '
    '28일 창에서 관측이 최대 4개라 sample_days 가 7 에 도달하지 못해 z 경로가 죽어 있었다. '
    '생성 28일 미만 문서는 생성 이후 표본을 즉시 쓰며, 통계 산출 불가 또는 기준 조회수 0이면 '
    '현재 조회수 100 이상을 급등으로 본다(WP-118).';

COMMENT ON COLUMN page_baseline.hour_of_day IS
    'UTC 0시 = 0, 23시 = 23. 같은 슬롯이 매일 오므로 28일 창에서 최대 28관측이다.';
