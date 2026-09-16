-- WP-100: spike 에 출처(provenance) 컬럼을 추가한다.
--
-- 왜 필요한가
--   `spike` 는 여태 리플레이 산출물만 담았다. 유일한 writer 가 `spike/spike_sink.py`
--   하나이고, 그걸 부르는 곳이 `spike/replay.py` 의 DB 모드뿐이었다(2026-09-15 실측).
--   그래서 출처를 구분할 필요가 없었다.
--
--   LIVE(EventStreams → Kafka → Spark 윈도우)를 같은 테이블에 적재하기 시작하면
--   그 전제가 깨진다. 두 출처가 한 테이블에 섞이는데 구분할 방법이 없으면:
--     - `cluster/driver.py` 가 리플레이 spike 를 읽어 `issue_cluster.source='live'` 로
--       저장하는 **거짓 라벨링**이 성립한다. -99 가 그래서 `SPIKE_SOURCE='replay'`
--       하나만 허용하는 가드를 뒀다 (cluster/driver.py 독스트링 🔴).
--     - 화면이 2024년 허리케인을 "지금 뜨는 이슈" 로 그린다. 에러가 안 나는 쪽이다.
--   이 마이그레이션이 그 가드를 걷을 수 있는 전제를 만든다. 걷는 것은 다음 스토리다.
--
-- 기존 행을 replay 로 backfill 하는 근거
--   위에 적은 대로 writer 가 하나뿐이고 그 호출 경로가 리플레이 전용이라,
--   현재 테이블에 있는 행은 정의상 전부 리플레이 산출물이다. 추측이 아니라
--   `grep -rn "INSERT INTO spike"` 로 확인한 사실이다 — 프로덕션 코드에서는
--   `spike/spike_sink.py:47` 한 곳, 나머지는 테스트다.
--
-- DEFAULT 를 남기지 않는 이유
--   backfill 에만 쓰고 바로 떼어낸다. 기본값이 남아 있으면 앞으로 source 를
--   빠뜨린 writer 가 **에러 없이** 'replay' 로 들어간다 — 이 저장소가 반복해서
--   당한 "조용히 틀리는" 유형이다. 경계에서 명시를 강제한다
--   (`SpikeSink(conn, source=...)` 가 생성 시점에 막는 것과 같은 이유).
--
-- 🔴 UNIQUE 키에 source 를 넣는 이유 — 이 마이그레이션의 핵심
--   기존 키는 `spike_unique_window UNIQUE (page_id, window_start)` 였다.
--   source 컬럼만 추가하고 이 키를 그대로 두면 **provenance 가 보존되지 않는다**:
--   같은 문서·같은 윈도우를 LIVE 가 다시 판정하는 순간 upsert 의
--   `ON CONFLICT DO UPDATE` 가 리플레이 행을 덮어쓰고 source 까지 'live' 로 바꾼다.
--   반대 방향도 같다. 즉 "리플레이가 live 로 덮어써지지 않는다" 를 애플리케이션
--   코드의 조심성에 맡기게 된다.
--   키에 source 를 넣으면 두 출처가 **서로 다른 행**이 되어 DB 가 구조적으로 막는다.
--   각 출처 안에서의 멱등성(같은 윈도우 재판정 → 행 안 늚)은 그대로다.
--
--   ⚠️ 이 테이블을 읽는 쪽은 이제 source 를 **직접 걸어야 한다.**
--   `cluster/driver.py` 의 `SELECT_SEEDS_SQL`·`SELECT_SNAPSHOT_TIMES_SQL` 에는
--   아직 source 조건이 없다(2026-09-15 확인). LIVE 행이 쌓이기 전까지는 결과가
--   같지만, 쌓이는 순간 리플레이 스냅샷에 LIVE 씨드가 섞인다.
--   그 필터는 -99 가드를 걷는 다음 스토리에서 같이 넣는다.

ALTER TABLE spike ADD COLUMN source TEXT NOT NULL DEFAULT 'replay';

-- backfill 이 끝났으니 기본값을 뗀다. 이후 INSERT 는 source 를 명시해야 한다.
ALTER TABLE spike ALTER COLUMN source DROP DEFAULT;

ALTER TABLE spike ADD CONSTRAINT spike_source_check
    CHECK (source IN ('live', 'replay'));

-- 출처별로 같은 윈도우가 공존한다. 출처 안에서는 여전히 한 행이다.
ALTER TABLE spike DROP CONSTRAINT spike_unique_window;
ALTER TABLE spike ADD CONSTRAINT spike_unique_window
    UNIQUE (source, page_id, window_start);

COMMENT ON COLUMN spike.source IS
    '산출 경로. live = EventStreams→Kafka→Spark 윈도우(WP-100), '
    'replay = 과거 덤프 재생(spike/replay.py --dsn). '
    'issue_cluster.source 와 같은 어휘다. UNIQUE 키에 들어가므로 두 출처가 같은 '
    '문서·윈도우를 각각 가질 수 있고, 서로 덮어쓰지 않는다.';
