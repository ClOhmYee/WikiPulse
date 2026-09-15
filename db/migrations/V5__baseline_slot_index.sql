-- WP-88: 기준선 슬롯을 시간(24) -> 6시간(4) 으로 넓히고 이름을 slot_index 로.
--
-- 왜 또 바꾸나 (2026-09-15 전수 실측, 명세 §11)
--   V3 가 hour_of_week(168) -> hour_of_day(24) 로 바꿔 "28일 창에 최대 4관측" 을 고쳤지만,
--   24 슬롯도 여전히 얇았다. 편집이 24개 슬롯에 흩어지는 문서는 슬롯당 관측 날짜가
--   MIN_BASELINE_SAMPLE_DAYS(7) 에 못 미쳐 is_thin -> 신규 문서 경로로 빠진다.
--
--   실덤프 2025-06 · 2024-10 (두 달 값이 1pp 이내로 일치):
--     슬롯당 sample_days>=7 도달률   1h 1.5% / 3h 5.4% / 6h 13.0% / 일 58.1%
--     문서 중 1개라도 통과           1h 4.8% / 3h 13.7% / 6h 25.2% / 일 58.1%
--   월 편집 수 구간별로는 20~49편집 0.8% · 100~299편집 39.9% · 300~999편집 83.3% —
--   즉 24 슬롯의 z 경로는 **월 300편집 이상 문서 전용**이었다. Boeing_787_Dreamliner
--   (2011년 생성, 월 197편집)가 is_new_page=True 로 판정된 게 예외가 아니라 정상이었다.
--
-- 왜 일 단위(1슬롯)까지 안 갔나
--   하루를 통으로 묶으면 시간대 패턴을 전부 버린다. 6시간이면 새벽·오전·오후·저녁
--   네 구간이 남아 일주기 모양을 유지한다. 도달률 58% 대 25% 를 그 대가로 포기한다.
--
-- 무엇을 잃나 (같은 관측에 1h·6h 기준선을 각각 물려 실측)
--   판정 대상 2,134 윈도우 중 z 경로 가능: 1h 482(23%) -> 6h 1,726(81%)
--   둘 다 z 가능한 479 윈도우에서 임계 판정 일치 469 (97.9%)
--   불일치 10건 — 1h만 급증 7 · 6h만 급증 3. z 차이 중앙값 +0.07
--   얻는 쪽(1,244 윈도우가 z 경로 진입)이 잃는 쪽(겹치는 구간 2.1% 불일치)보다 크다.
--
-- 왜 이름을 바꾸나
--   값이 더 이상 "시(hour)" 가 아니다. hour_of_day 라는 이름으로 0~3 을 담으면
--   읽는 사람이 UTC 시로 오해한다. 폭은 batch/historical_windows.py 의 SLOT_HOURS
--   한 곳에서만 온다 — 컬럼 이름에 숫자를 박지 않는 이유다(다음에 또 바꾸면 V6 가 된다).
--
-- 기존 행을 변환하지 않고 비우는 이유
--   V3 와 같다. page_baseline 은 덤프에서 재계산되는 파생 데이터이고, hour_of_day/6 으로
--   접으면 한 page_id 의 6개 슬롯이 같은 slot_index 로 몰려 PK 가 충돌한다.
--   비우고 spike.baseline_sink 로 다시 채운다.

TRUNCATE TABLE page_baseline;

ALTER TABLE page_baseline DROP CONSTRAINT page_baseline_pkey;
ALTER TABLE page_baseline DROP CONSTRAINT page_baseline_hour_of_day_check;
ALTER TABLE page_baseline RENAME COLUMN hour_of_day TO slot_index;

ALTER TABLE page_baseline
    ADD CONSTRAINT page_baseline_slot_index_check CHECK (slot_index BETWEEN 0 AND 3);
ALTER TABLE page_baseline ADD PRIMARY KEY (page_id, slot_index);

COMMENT ON TABLE page_baseline IS
    '문서 × 6시간 슬롯(0~3, UTC) 기준선. 28일치를 EWMA 로 굴린다. '
    '~~요일×시간대(0~167)~~ -> 시간대(0~23) (WP-84) -> ~~시간대~~ 6시간 4슬롯 '
    '(2026-09-15, WP-88) — 24 슬롯도 얇아서 z 경로가 월 300편집 이상 문서에만 '
    '돌았다. sample_days 가 적으면(신규 문서) 판정을 보류한다.';

COMMENT ON COLUMN page_baseline.slot_index IS
    'UTC 시 // 6. 0=00~05시, 1=06~11시, 2=12~17시, 3=18~23시. '
    '🔴 폭은 batch/historical_windows.py 의 SLOT_HOURS 한 곳에서만 온다 — '
    '여기 값과 갈리면 기준선이 조용히 어긋난다.';
