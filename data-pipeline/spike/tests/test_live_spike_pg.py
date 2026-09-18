"""LIVE 마이크로배치 왕복 — 실 Spark + 실 PostgreSQL (WP-100).

`tests/test_live_spike.py` 의 매핑 검사는 dict 까지만 본다. "Spark DataFrame 이
실제로 저 컬럼을 낸다"·"마이크로배치를 두 번 돌려도 행이 안 는다"·"리플레이 행과
LIVE 행이 공존한다" 는 둘 다 실물이 있어야 확인된다.

돌리는 법 — 저장소 루트에서 개발 스택을 띄우고:

    docker compose up -d postgres
    cd data-pipeline && .venv/Scripts/python.exe -m pytest spike/tests/test_live_spike_pg.py

DATABASE_URL 이 있으면 그걸 쓰고, 없으면 docker-compose 기본 DSN 으로 붙는다.
pyspark·psycopg 가 없거나 DB 에 못 붙으면 skip 한다.

⚠️ 이 파일은 V5(`spike.source`)가 적용된 DB 를 전제한다. 안 돼 있으면 skip 한다 —
   "컬럼이 없다" 는 실패는 코드 결함이 아니라 마이그레이션 미적용이라서다.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)

psycopg = pytest.importorskip("psycopg", reason="psycopg 미설치 — 이 파일은 건너뛴다")
pyspark = pytest.importorskip("pyspark", reason="pyspark 미설치 — 이 파일은 건너뛴다")

from pyspark.sql import SparkSession                        # noqa: E402
from pyspark.sql import functions as F                      # noqa: E402

from spike.baseline_repository import BaselineRepository    # noqa: E402
from spike.baseline_rows import build_rows                  # noqa: E402
from spike.baseline_sink import load                        # noqa: E402
from spike.detector import MIN_ABSOLUTE_EDITS, MIN_ABSOLUTE_VIEWS   # noqa: E402
from spike.runtime import PageWindow, SpikeRuntime          # noqa: E402
from spike.spike_sink import SpikeSink                      # noqa: E402
from streaming.edit_windows import aggregate_edit_windows   # noqa: E402
from streaming.live_spike import (                          # noqa: E402
    LIVE_SOURCE,
    process_batch,
    to_runtime_frame,
)

DEFAULT_DSN = "postgresql://wikipulse:wikipulse@localhost:5432/wikipulse"
UTC = timezone.utc

#: 2024-10-06T19:00:00Z — 정각 윈도우.
WINDOW_START = datetime(2024, 10, 6, 19, tzinfo=UTC)


@pytest.fixture(scope="module")
def spark():
    session = (
        SparkSession.builder.appName("wikipulse-live-spike-test")
        .master("local[1]")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


@pytest.fixture()
def conn():
    dsn = os.environ.get("DATABASE_URL") or DEFAULT_DSN
    try:
        connection = psycopg.connect(dsn, connect_timeout=5)
    except psycopg.OperationalError as err:
        pytest.skip(f"PostgreSQL 연결 불가 — docker compose up -d postgres ({err})")
    with connection:
        with connection.cursor() as cur:
            cur.execute("SELECT 1 FROM information_schema.columns "
                        "WHERE table_name='spike' AND column_name='source'")
            if cur.fetchone() is None:
                pytest.skip("spike.source 없음 — V5 마이그레이션 미적용")
        yield connection


@pytest.fixture()
def title(conn):
    """테스트마다 고유 문서. 끝나면 지운다(spike 는 FK CASCADE).

    ⚠️ 밑줄을 쓰지 않는다 — 런타임이 제목을 canonical(공백형)로 맞춘다.
    """
    name = f"PyTest Live {uuid.uuid4().hex[:12]}"
    yield name
    with conn.cursor() as cur:
        cur.execute("DELETE FROM wiki_page WHERE wiki=%s AND title=%s", ("enwiki", name))
    conn.commit()


#: 이벤트 revision id 의 시작값. 실제 enwiki 값 대역(12억대)을 쓴다 — INTEGER 로 잡으면
#: 넘치는 크기라는 걸 눈에 보이게 하려는 것이다(spike.max_rev_id 는 BIGINT).
FIRST_REV_ID = 1_295_198_200


def edit_events(spark, title, *, count, editors, start=WINDOW_START):
    """편집 이벤트 DataFrame. `aggregate_edit_windows` 입력과 같은 형태다."""
    rows = [
        {
            "wiki": "enwiki",
            "title": title,
            "user": f"editor{i % editors}",
            "is_bot": False,
            "byte_delta": 100,
            # 윈도우 안에 고르게 흩는다.
            "event_ts": start + timedelta(minutes=(i % 55)),
            # 시점 감사 증거의 입력 (V9, WP-129 2번). 실제 스트림에도 있는 필드다.
            "rev_id": FIRST_REV_ID + i,
        }
        for i in range(count)
    ]
    return spark.createDataFrame(rows).select(
        "wiki", "title", "user", "is_bot", "byte_delta", "rev_id",
        F.col("event_ts").cast("timestamp").alias("event_ts"),
    )


#: 2단계 관문(WP-126)을 통과시키는 조회수. 아래 문서들은 조회수 기준선 표본이
#: 없어 절대 하한(MIN_ABSOLUTE_VIEWS=100)만 보는 "0 에서의 급등" 경로로 확정된다.
CONFIRMING_VIEWS = 5_000


def aggregated_batch(spark, title, *, count, editors, views=CONFIRMING_VIEWS):
    """편집 이벤트 -> 실제 집계 함수 -> LIVE 싱크가 받는 형태.

    슬라이드를 윈도우와 같게 줘서 정각 tumbling 하나만 나오게 한다 — 겹치는
    윈도우까지 세면 이 파일이 보려는 계약(멱등·출처)이 가려진다.
    """
    from pyspark.sql import functions as F

    windows = aggregate_edit_windows(
        edit_events(spark, title, count=count, editors=editors),
        window_size="1 hour", slide_size="1 hour",
    )
    if views is None:
        return windows
    # 🔴 **편집 스트림에는 조회수가 없다** (`streaming/live_spike.py` ⚠️). 이 파일이
    #    보려는 건 Spark -> 싱크 이음매(출처 라벨·멱등·공존)지 관문 자체가 아닌데,
    #    조회수가 없으면 전부 후보 대기가 돼 한 행도 안 남아 그 계약을 못 본다.
    #    그래서 여기서만 조회수를 실어 확정이 나게 한다. 실제 주입 경로는 -128 이다.
    #    조회수 없는 LIVE 의 진짜 결과는 `test_조회수_없는_LIVE_배치는_확정이_없다` 가 본다.
    return windows.withColumn("views", F.lit(views))


def seed_baseline(conn, title, *, edit_ewma, edit_stddev, sample_days):
    """`baseline_sink.load` 로 실제 행을 넣는다 — 직접 INSERT 하지 않는다."""
    rows = build_rows(
        [{"wiki": "enwiki", "title": title, "hour_of_day": WINDOW_START.hour,
          "window_start": f"2024-09-{day:02d}T{WINDOW_START.hour:02d}:00:00",
          "edit_count": value, "views": None}
         for day, value in zip(range(1, sample_days + 1),
                               _values(edit_ewma, edit_stddev, sample_days))],
        as_of=date(2024, 9, sample_days),
        halflife_days=10_000,      # 사실상 균등 가중
    )
    load(conn, rows)


def _values(mean, stddev, n):
    half = n // 2
    return [mean - stddev] * half + [mean + stddev] * half + ([mean] if n % 2 else [])


def spikes(conn, title, source=None):
    sql = ("SELECT s.source, s.window_start, s.detected_at, s.edit_count, s.spike_score "
           "FROM spike s JOIN wiki_page p ON p.id = s.page_id "
           "WHERE p.wiki=%s AND p.title=%s")
    params = ["enwiki", title]
    if source is not None:
        sql += " AND s.source=%s"
        params.append(source)
    with conn.cursor() as cur:
        cur.execute(sql + " ORDER BY s.source, s.window_start", params)
        return cur.fetchall()


def save_replay_spike(conn, title, *, edits):
    """리플레이 출처로 한 건 적재 — 공존 검사의 대조군."""
    SpikeRuntime(BaselineRepository(conn), SpikeSink(conn, source="replay")).process(
        PageWindow(wiki="enwiki", title=title, window_start=WINDOW_START,
                   edit_count=edits, editor_count=4, views=CONFIRMING_VIEWS))
    conn.commit()


# ------------------------------------------------- Spark 집계 -> 런타임 입력 형태

def test_집계_결과가_런타임_입력_컬럼을_낸다(spark):
    """`to_runtime_frame` 이 기대하는 컬럼이 실제 집계 출력에 다 있다."""
    # last_edit_epoch·max_rev_id 는 시점 감사 증거다 (V9, WP-129 2번).
    required = {"wiki", "title", "window_start_epoch", "window_end_epoch",
                "edit_count", "editor_count", "last_edit_epoch", "max_rev_id"}

    # 편집 스트림 그대로 — 조회수 컬럼이 없다. 없는 걸 만들어 내지 않는다.
    bare = to_runtime_frame(aggregated_batch(spark, "X", count=5, editors=2, views=None))
    assert set(bare.columns) == required

    # 조회수가 붙은 프레임이면 그대로 싣는다 (WP-128 이 쓸 이음매).
    with_views = to_runtime_frame(aggregated_batch(spark, "X", count=5, editors=2))
    assert set(with_views.columns) == required | {"views"}


def test_epoch_변환이_UTC_순간값을_보존한다(spark):
    """🔴 드라이버가 KST 여도 값이 안 밀린다 — 회귀 방지의 핵심 검사.

    PySpark 의 datetime 변환은 로컬 시간대 naive 를 낸다(2026-09-15 실측:
    UTC 19:00 -> datetime(2024, 10, 7, 4, 0), tzinfo=None). epoch 경계가 그걸 막는다.
    """
    row = to_runtime_frame(aggregated_batch(spark, "X", count=5, editors=2)).collect()[0]
    assert datetime.fromtimestamp(row["window_start_epoch"], tz=UTC) == WINDOW_START
    assert row["window_end_epoch"] - row["window_start_epoch"] == 3600


# ----------------------------------------------------------- 마이크로배치 왕복

def test_마이크로배치가_source_live로_적재한다(spark, conn, title):
    """Spark 윈도우 -> SpikeRuntime -> spike(source='live') 관통."""
    batch = aggregated_batch(spark, title, count=MIN_ABSOLUTE_EDITS + 5, editors=4)
    summary = process_batch(conn, batch, batch_id=0)

    assert (summary.evaluated, summary.detected, summary.persisted) == (1, 1, 1)

    rows = spikes(conn, title)
    assert len(rows) == 1
    source, window_start, detected_at, edit_count, _ = rows[0]
    assert source == LIVE_SOURCE
    assert window_start == WINDOW_START
    # detected_at = 윈도우 끝. now() 가 아니다 — 재실행에도 안 흔들린다.
    assert detected_at == WINDOW_START + timedelta(hours=1)
    assert edit_count == MIN_ABSOLUTE_EDITS + 5


def test_시점_증거가_spike에_같이_적재된다(spark, conn, title):
    """무엇까지 보고 판정했는지 (V9, WP-129 2번).

    🔴 이게 없으면 "이 구간 판정에 미래 편집이 안 섞였다" 를 나중에 보일 수가 없다.
    덤프를 잘못 자르거나 구간이 겹쳐도 spike 행은 똑같이 생긴다.
    """
    count = MIN_ABSOLUTE_EDITS + 5
    process_batch(conn, aggregated_batch(spark, title, count=count, editors=4), batch_id=0)

    with conn.cursor() as cur:
        cur.execute("SELECT s.max_rev_id, s.last_edit_ts, s.window_start, s.detected_at "
                    "FROM spike s JOIN wiki_page p ON p.id = s.page_id "
                    "WHERE p.wiki=%s AND p.title=%s", ("enwiki", title))
        max_rev_id, last_edit_ts, window_start, detected_at = cur.fetchone()

    # 이벤트는 rev_id 를 FIRST_REV_ID 부터 하나씩 올려 만든다 — 최대값이 마지막 것이다.
    assert max_rev_id == FIRST_REV_ID + count - 1
    # 자체 검증식: 마지막 편집은 윈도우 안에 있다 (detected_at = 윈도우 끝).
    assert window_start <= last_edit_ts < detected_at


def test_미탐은_저장하지_않는다(spark, conn, title):
    """🔴 ~~편집자 1명이면 편집 관문에서 걸린다~~ → 편집자 수는 관문이 아니다
    (WP-126). 폐기를 내는 건 조회수다 — 절대 하한 미만이면 REJECTED 다.
    """
    batch = aggregated_batch(spark, title, count=MIN_ABSOLUTE_EDITS + 5, editors=1,
                             views=MIN_ABSOLUTE_VIEWS - 1)
    summary = process_batch(conn, batch, batch_id=0)

    assert (summary.detected, summary.persisted) == (0, 0)
    assert spikes(conn, title) == []


def test_조회수_없는_LIVE_배치는_확정이_없다(spark, conn, title):
    """🔴 지금 LIVE 의 실제 상태다 — 버그가 아니라 계약이다 (WP-126).

    `wiki.edits` 에 조회수가 없어서 2단계를 못 넘는다. 확정도 폐기도 아닌 후보 대기라
    `spike` 에 한 행도 안 남는다. `other/pageviews` 를 붙이는 -128 이 이걸 푼다.
    이 테스트가 깨지면 둘 중 하나다: 조회수가 실제로 붙었거나(좋음, 이 검사를 바꾼다),
    조회수 없는 윈도우가 다시 확정되기 시작했거나(나쁨, 관문이 뚫렸다).
    """
    batch = aggregated_batch(spark, title, count=MIN_ABSOLUTE_EDITS + 5, editors=4,
                             views=None)
    summary = process_batch(conn, batch, batch_id=0)

    assert (summary.evaluated, summary.detected, summary.persisted) == (1, 0, 0)
    assert summary.pending_views == 1
    assert spikes(conn, title) == []


def test_같은_배치를_두_번_처리해도_행이_안_는다(spark, conn, title):
    """Structured Streaming 은 같은 마이크로배치를 재처리할 수 있다.

    멱등의 근거는 V5 의 UNIQUE (source, page_id, window_start) 다.
    """
    batch = aggregated_batch(spark, title, count=MIN_ABSOLUTE_EDITS + 5, editors=4)

    process_batch(conn, batch, batch_id=7)
    first = spikes(conn, title)
    process_batch(conn, batch, batch_id=7)      # 같은 batch_id 로 재처리
    second = spikes(conn, title)

    assert len(first) == 1
    assert second == first          # 행 수도 값도 그대로


def test_재처리에서_편집수가_늘면_값만_갱신된다(spark, conn, title):
    """update 모드라 같은 윈도우가 더 큰 집계로 다시 온다. 행은 하나다."""
    process_batch(conn, aggregated_batch(spark, title,
                                         count=MIN_ABSOLUTE_EDITS + 5, editors=4),
                  batch_id=0)
    process_batch(conn, aggregated_batch(spark, title,
                                         count=MIN_ABSOLUTE_EDITS + 30, editors=6),
                  batch_id=1)

    rows = spikes(conn, title)
    assert len(rows) == 1
    assert rows[0][3] == MIN_ABSOLUTE_EDITS + 30


# --------------------------------------------------------- replay/live 공존·격리

def test_같은_문서_윈도우를_replay와_live가_각각_갖는다(spark, conn, title):
    """🔴 V5 가 UNIQUE 키에 source 를 넣은 이유가 이것이다.

    키가 (page_id, window_start) 였다면 뒤에 쓴 쪽이 앞의 행을 덮어쓰고
    source 까지 바꿔, 리플레이 산출물이 LIVE 로 둔갑한다.
    """
    save_replay_spike(conn, title, edits=MIN_ABSOLUTE_EDITS + 5)
    process_batch(conn, aggregated_batch(spark, title,
                                         count=MIN_ABSOLUTE_EDITS + 9, editors=4),
                  batch_id=0)

    rows = spikes(conn, title)
    assert [r[0] for r in rows] == ["live", "replay"]
    # 같은 윈도우다 — 다른 행으로 공존한다.
    assert rows[0][1] == rows[1][1] == WINDOW_START
    # 서로 값을 덮지 않았다.
    assert {r[0]: r[3] for r in rows} == {
        "live": MIN_ABSOLUTE_EDITS + 9,
        "replay": MIN_ABSOLUTE_EDITS + 5,
    }


def test_live_적재가_기존_replay_행을_건드리지_않는다(spark, conn, title):
    save_replay_spike(conn, title, edits=MIN_ABSOLUTE_EDITS + 5)
    before = spikes(conn, title, source="replay")

    process_batch(conn, aggregated_batch(spark, title,
                                         count=MIN_ABSOLUTE_EDITS + 50, editors=9),
                  batch_id=0)

    assert spikes(conn, title, source="replay") == before


# ------------------------------------------------------------- 기준선 캐시 수명

def test_배치마다_기준선_캐시를_다시_읽는다(spark, conn, title):
    """장수명 LIVE 프로세스에서 `page_baseline` 재적재가 다음 배치에 반영돼야 한다.

    캐시가 배치를 넘어 살면 기준선을 새로 넣어도 **영원히 옛 값으로 판정한다** —
    에러 없이 z 만 틀리는 쪽이다 (`spike/runtime.py` iter_process 🔴).

    두꺼운 기준선을 **첫 배치 뒤에** 넣고 같은 입력을 다시 흘린다. 캐시가 살아 있으면
    두 번째 배치도 "기준선 없음(absent)" 으로 판정할 것이다.
    """
    edits = MIN_ABSOLUTE_EDITS + 5
    batch = aggregated_batch(spark, title, count=edits, editors=4)

    first = process_batch(conn, batch, batch_id=0)
    assert first.baseline_absent == 1, "아직 기준선이 없다"

    # 평균이 편집수보다 훨씬 커서 z 가 안 뜨는 기준선.
    seed_baseline(conn, title, edit_ewma=edits * 20, edit_stddev=1.0, sample_days=30)
    conn.commit()

    second = process_batch(conn, batch, batch_id=1)
    # 캐시가 배치를 넘어 살았다면 여기도 absent 였을 것이다.
    assert second.baseline_absent == 0
    assert second.baseline_db == 1, "새로 넣은 기준선을 읽어 z 경로로 갔다"
