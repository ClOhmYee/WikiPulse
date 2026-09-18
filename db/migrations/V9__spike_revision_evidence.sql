-- WP-129 (2번): 감지 결과에 "무엇까지 보고 판정했는지" 를 남긴다.
--
-- 왜 필요한가
--   명세 v0.3 의 시점 계약은 "리플레이는 snapshot_ts 이하 revision 만 쓴다" 고 정한다.
--   그런데 저장된 값 어디에도 revision 이 없어서 **그 규칙이 지켜졌는지 확인할 방법이
--   없었다.** 덤프를 잘못 자르거나 구간이 겹쳐 미래 편집이 섞여 들어와도 spike 행은
--   똑같이 생겼다 — 에러도 없고 흔적도 없다.
--
--   🔴 이건 버그가 아니라 **감사 불가능** 이다. 지금 맞게 돌고 있어도, 맞게 돌았다는 걸
--      나중에 보일 수가 없다. EC2 재현(G7 게이트)에서 요구하는 종류의 증거가 이것이다.
--
-- 두 컬럼의 뜻
--   max_rev_id    그 윈도우 집계에 들어간 revision id 중 가장 큰 값. 위키미디어에서
--                 이 revision 의 시각을 조회하면 "그 뒤 편집은 안 썼다" 가 외부 검증된다.
--                 revision id 는 위키 전체에서 단조 증가하므로 최대값 하나로 충분하다.
--   last_edit_ts  그 윈도우에서 본 마지막 편집 시각. API 없이 자체 검증할 수 있는 값이다 —
--                 last_edit_ts <= window_end <= snapshot_ts 가 깨지면 그 자리에서 드러난다.
--
--   둘 다 두는 이유: 하나는 외부 대조용(rev id), 하나는 자체 대조용(시각)이다.
--   시각만 있으면 "우리가 기록한 시각" 을 우리가 검사하는 셈이라 순환이고,
--   rev id 만 있으면 검사할 때마다 API 를 때려야 한다.
--
-- NULL 의 뜻
--   둘 다 NULL = 이 마이그레이션 이전에 적재된 행이거나, revision id 를 안 싣는 입력으로
--   만든 행이다. ⚠️ "revision 이 없다" 가 아니라 "기록을 안 했다" 로 읽는다 — 감사에서는
--   통과가 아니라 **판정 보류** 다.
--
-- 기존 행
--   TRUNCATE 하지 않는다(V7 과 같은 이유 — 리플레이 산출물이라 지우면 클러스터가 사라진다).
--   옛 행은 NULL 로 남고, 다시 적재하면 채워진다.

ALTER TABLE spike ADD COLUMN max_rev_id   BIGINT;
ALTER TABLE spike ADD COLUMN last_edit_ts TIMESTAMPTZ;

-- "이 구간 spike 중 증거가 없는 행" 을 싸게 세기 위한 인덱스. 감사 질의의 경로다.
CREATE INDEX spike_missing_revision_idx ON spike (window_start DESC)
    WHERE max_rev_id IS NULL;

COMMENT ON COLUMN spike.max_rev_id IS
    '그 윈도우 집계에 들어간 최대 revision id. 이 revision 의 시각을 위키미디어에서 '
    '조회하면 "그 뒤 편집은 안 썼다" 가 외부 검증된다. '
    'NULL = 기록 안 함(감사 보류) — revision 이 없었다는 뜻이 아니다 (WP-129).';

COMMENT ON COLUMN spike.last_edit_ts IS
    '그 윈도우에서 본 마지막 편집 시각. last_edit_ts <= window_end 가 자체 검증식이다. '
    '리플레이는 여기에 더해 window_end <= snapshot_ts 여야 한다 (명세 v0.3 시점 계약).';
