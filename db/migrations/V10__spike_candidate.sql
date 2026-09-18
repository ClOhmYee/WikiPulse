-- WP-128: 1단계를 통과했지만 조회수가 아직 안 온 윈도우를 보관한다.
--
-- 왜 필요한가
--   2단계 계약(WP-126)에서 판정은 셋이다: 확정 / 폐기 / **후보 대기**.
--   `spike` 는 확정만 담고(V1 테이블 주석), 폐기는 버린다. 후보 대기는 갈 곳이 없어서
--   그냥 사라지고 있었다 — 조회수가 1시간쯤 뒤에 도착해도 다시 판정할 대상이 없다.
--   명세 §3.2 3번: "조회수가 아직 도착하지 않았으면 1단계 후보로 보관했다가 도착 시 재판정한다".
--
--   🔴 이 테이블이 없으면 LIVE 는 영영 확정을 못 낸다. 편집 스트림에는 조회수가 없고
--      (`streaming/live_spike.py`), 조회수는 항상 나중에 오기 때문이다.
--
-- 왜 spike 에 못 넣나
--   `spike` 한 행은 "이슈가 됐다" 는 뜻이고 클러스터·API 가 그걸 읽는다. 대기 상태를
--   같은 테이블에 두면 조회수를 안 본 문서가 이슈로 노출된다. `SpikeSink.save` 가
--   후보 대기를 명시적으로 거부하는 것도 같은 이유다.
--
-- 수명
--   확정되거나 폐기되면 **그 자리에서 지운다**. 안 지우면 후보가 무한히 쌓인다.
--   조회수가 영영 안 오는 문서(삭제·이동)는 `first_seen_at` 기준으로 만료시킨다 —
--   시간별 덤프가 윈도우 끝 기준 약 1시간 뒤에 나오므로(2026-09-18 실측), 하루가
--   넘도록 안 왔으면 그 시간 파일은 이미 나왔고 이 문서가 그 안에 없었던 것이다.
--
-- 키
--   `(source, page_id, window_start)` — `spike` 와 같은 키다(V5). 같은 윈도우가 다시
--   흘러와도(스트리밍 재처리) 행이 안 늘고 편집 수만 갱신된다.
--
-- 판정에 필요한 값만 담는다
--   재판정은 조회수만 새로 붙여 `detect()` 를 다시 태우는 것이라, 그때 필요한 입력
--   (편집 수·편집자 수·윈도우 경계)과 증거(max_rev_id·last_edit_ts)를 같이 들고 있어야
--   원본 스트림을 다시 안 읽는다. 기준선은 재판정 시점에 `page_baseline` 에서 다시 읽는다.

CREATE TABLE spike_candidate (
    source        TEXT        NOT NULL
                  CHECK (source IN ('live', 'replay')),
    page_id       BIGINT      NOT NULL REFERENCES wiki_page(id) ON DELETE CASCADE,
    window_start  TIMESTAMPTZ NOT NULL,
    window_end    TIMESTAMPTZ NOT NULL,
    edit_count    INTEGER     NOT NULL,
    editor_count  INTEGER     NOT NULL DEFAULT 0,
    max_rev_id    BIGINT,
    last_edit_ts  TIMESTAMPTZ,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    recheck_count INTEGER     NOT NULL DEFAULT 0,
    PRIMARY KEY (source, page_id, window_start)
);

COMMENT ON TABLE spike_candidate IS
    '1단계(사람 편집 >= 1)를 통과했고 조회수 판정이 남은 윈도우. 확정되면 spike 로 옮기고 '
    '폐기되면 지운다 — 이 테이블에 남아 있는 것은 "아직 판정 중" 뿐이다 (WP-128).';

COMMENT ON COLUMN spike_candidate.window_end IS
    '조회수 버킷을 찾는 기준이자 spike.detected_at 이 될 값. now() 를 쓰지 않는다 — '
    '재판정해도 값이 안 흔들려야 멱등이다.';

COMMENT ON COLUMN spike_candidate.first_seen_at IS
    '처음 대기로 들어온 시각. 만료 판단에만 쓴다. ⚠️ 판정 시각이 아니다.';

COMMENT ON COLUMN spike_candidate.recheck_count IS
    '재판정을 시도한 횟수. 조회수가 계속 안 오는 문서를 찾는 진단값이다.';

-- 재판정은 "조회수가 들어온 윈도우" 를 찾는 조회다. 오래된 것부터 본다.
CREATE INDEX spike_candidate_window_idx ON spike_candidate (window_start);
