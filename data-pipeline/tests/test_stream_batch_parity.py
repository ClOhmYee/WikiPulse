"""배치 집계 == 스트리밍 집계 대조 (WP-83).

같은 `edit_event` 표본을 두 경로에 넣어 `(wiki, title, window_start)` 별 `edit_count` 가
같은지 고정한다. 두 경로가 갈리면 `edit_z` 가 통째로 어긋나는데 **에러 없이 숫자만 틀린다** —
그래서 회귀 테스트로 남긴다.

| 경로 | 코드 |
| --- | --- |
| 스트리밍 | `streaming/edit_windows.py` `aggregate_edit_windows()` |
| 배치 | `batch/historical_windows.py` `aggregate_edits()` |

## 무엇을 "같다"고 보는가 (⚠️ 이걸 먼저 정해야 대조가 성립한다)

스트리밍은 `F.window(size, slide)` **슬라이딩**이고 배치는 정각 **tumbling** 이다.
슬라이드가 있으면 한 편집이 12개 윈도우(1시간 / 5분)에 들어가므로 행 수부터 다르다.

`slide` 가 `size` 를 나누므로 **정각에서 시작하는 윈도우가 항상 존재**하고, 그 구간이
배치의 tumbling 윈도우와 정확히 같다. 그래서 대조는 **정각 시작 윈도우만** 본다.
나머지 슬라이딩 윈도우는 배치에 대응물이 없다 — 없는 걸 비교하는 게 아니라 비교 대상이
아닌 것이다.

Kafka 없이 돈다. 스트리밍 소스 대신 같은 변환을 배치 DataFrame 에 건다.
"""

from __future__ import annotations

import json

import pytest

from batch.historical_windows import aggregate_edits, floor_to_hour

pyspark = pytest.importorskip("pyspark", reason="pyspark 미설치 — 이 파일은 건너뛴다")

from pyspark.sql import SparkSession  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

from streaming.edit_windows import (  # noqa: E402
    EDIT_EVENT_SCHEMA,
    aggregate_edit_windows,
)


def edit(title, ts, user="alice", *, wiki="enwiki", is_bot=False, byte_delta=10,
         rev_id=1):
    """producer/normalize.py · batch/normalize_dump.py 가 내보내는 형태.

    두 소스 모두 `event_ts` 를 Z 접미 UTC 로 낸다 (2026-09-15 실측: 덤프
    `2025-06-01T00:00:01.000Z`). 오프셋 표기(`+09:00`)는 이 경로에 안 들어온다 —
    들어오면 배치 `datetime.fromisoformat(...).hour` 가 로컬 시를 내서 갈린다.

    🔴 **title 은 canonical 공백형으로 준다.** 두 소스 다 `canonical_title` 을 거친
    값을 내기 때문이다(WP-79). 밑줄형을 주면 두 경로가 갈리는데, 그건 버그가
    아니라 아래 `test_스트리밍은_비정규_제목을_자가_보정하지_않는다` 가 고정하는 계약이다.
    """
    record = {
        "wiki": wiki, "domain": "en.wikipedia.org", "title": title,
        "event_type": "edit", "rev_id": rev_id, "rev_parent_id": None,
        "byte_delta": byte_delta, "new_length": 100, "user": user,
        "is_minor": False, "event_ts": ts, "event_ts_ms": 0,
        "source": "test", "meta_id": f"test:{title}:{ts}:{user}",
    }
    if is_bot is not None:          # None 이면 키 자체를 뺀다 (is_bot 결측)
        record["is_bot"] = is_bot
    return record


@pytest.fixture(scope="module")
def spark():
    session = (
        SparkSession.builder.appName("test-stream-batch-parity")
        .master("local[2]")
        # 🔴 naive 해석을 막는다. 이게 없으면 드라이버 로컬 시간대(KST)로 읽혀
        # 윈도우가 9시간 밀리는데 에러가 안 난다.
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "2")
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


def stream_windows(spark, events, **kwargs):
    """스트리밍 경로 결과를 {(wiki, title, 정각 문자열): (편집 수, 편집자 수)} 로.

    정각에서 시작하는 윈도우만 남긴다 — 위 모듈 docstring 참고.

    🔴 **타임스탬프를 Python 으로 꺼내지 않는다.** 시각 포맷·필터를 전부 Spark SQL 에서
    끝낸다. `collect()` 는 timestamp 를 **드라이버 로컬 시간대**(KST)의 naive datetime
    으로 바꿔 준다 — `spark.sql.session.timeZone=UTC` 로도 안 막힌다. 실제로 이 테스트가
    처음엔 전부 9시간 밀려 실패했다 (2026-09-15). 입력 쪽 함정(naive datetime 을
    createDataFrame 에 주면 밀린다)의 **출력판**이고, 역시 에러가 안 난다.
    """
    raw = spark.createDataFrame(
        [(json.dumps(e, ensure_ascii=False),) for e in events], "value string")
    parsed = (
        raw.select(F.from_json(F.col("value"), EDIT_EVENT_SCHEMA).alias("e"))
        .select("e.*")
        .withColumn("event_ts", F.to_timestamp("event_ts"))
    )
    aggregated = (
        aggregate_edit_windows(parsed, **kwargs)
        .filter((F.minute("window_start") == 0) & (F.second("window_start") == 0))
        .select(
            "wiki",
            "title",
            F.date_format("window_start", "yyyy-MM-dd'T'HH:00:00").alias("hour"),
            "edit_count",
            "editor_count",
        )
    )
    return {
        (r["wiki"], r["title"], r["hour"]): (r["edit_count"], r["editor_count"])
        for r in aggregated.collect()
    }


def batch_windows(events):
    """배치 경로 결과를 같은 모양으로.

    편집 수·편집자 수만 본다(`agg[:2]`). 시점 증거는 `batch_evidence` 가 따로 대조한다 —
    한 헬퍼에 섞으면 값이 갈렸을 때 어느 축이 어긋났는지 안 보인다.
    """
    return {
        (wiki, title, hour): tuple(agg[:2])
        for (wiki, title, hour), agg in aggregate_edits(events).items()
    }


def stream_evidence(spark, events, **kwargs):
    """스트리밍 경로의 시점 증거 (V9, WP-129 2번).

    타임스탬프는 Spark SQL 에서 문자열로 만든다 — collect() 로 datetime 을 꺼내면
    드라이버 로컬 시간대로 밀린다(위 stream_windows 🔴와 같은 함정).
    """
    raw = spark.createDataFrame(
        [(json.dumps(e, ensure_ascii=False),) for e in events], "value string")
    parsed = (
        raw.select(F.from_json(F.col("value"), EDIT_EVENT_SCHEMA).alias("e"))
        .select("e.*")
        .withColumn("event_ts", F.to_timestamp("event_ts"))
    )
    aggregated = (
        aggregate_edit_windows(parsed, **kwargs)
        .filter((F.minute("window_start") == 0) & (F.second("window_start") == 0))
        .select(
            "wiki",
            "title",
            F.date_format("window_start", "yyyy-MM-dd'T'HH:00:00").alias("hour"),
            "max_rev_id",
            F.date_format("last_edit_ts", "yyyy-MM-dd'T'HH:mm:ss").alias("last_edit"),
        )
    )
    return {
        (r["wiki"], r["title"], r["hour"]): (r["max_rev_id"], r["last_edit"])
        for r in aggregated.collect()
    }


def batch_evidence(events):
    """배치 경로의 같은 증거. 배치는 event_ts 문자열을 그대로 들고 있어 초까지 자른다."""
    return {
        key: (agg.max_rev_id, agg.last_edit_ts.replace("Z", "")[:19])
        for key, agg in aggregate_edits(events).items()
    }


# ---------------------------------------------------------------- 기본 대조

def test_시점_증거도_양쪽이_같다(spark):
    """🔴 증거가 두 경로에서 갈리면 감사 자체를 못 믿는다 (WP-129 2번).

    같은 덤프를 배치로 재생한 값과 LIVE 로 흘린 값이 다르면, 어느 쪽 증거가 맞는지
    판정할 수 없어 "무엇까지 보고 판정했나" 에 답이 둘 생긴다.
    """
    events = [
        edit("Hurricane Milton", "2024-10-06T19:05:00.000Z", "alice", rev_id=1_000),
        edit("Hurricane Milton", "2024-10-06T19:40:00.000Z", "bob", rev_id=1_250),
        edit("Hurricane Milton", "2024-10-06T19:20:00.000Z", "carol", rev_id=1_100),
    ]
    assert stream_evidence(spark, events) == batch_evidence(events)

    key = ("enwiki", "Hurricane Milton", "2024-10-06T19:00:00")
    # 최대값이지 마지막에 들어온 값이 아니다 — 입력 순서와 무관해야 한다.
    assert batch_evidence(events)[key] == (1_250, "2024-10-06T19:40:00")


def test_봇_편집의_증거는_양쪽_다_빠진다(spark):
    """봇은 집계에서 빠지므로 증거에서도 빠져야 한다. 한쪽만 빼면 편집 수는 같은데
    증거만 갈린다 — 조용히 틀리는 쪽이다."""
    events = [
        edit("Cat", "2025-06-01T10:10:00.000Z", "human", rev_id=500),
        edit("Cat", "2025-06-01T10:50:00.000Z", "bot", is_bot=True, rev_id=9_999),
    ]
    assert stream_evidence(spark, events) == batch_evidence(events)
    assert batch_evidence(events)[("enwiki", "Cat", "2025-06-01T10:00:00")][0] == 500


def test_같은_표본에_같은_편집수가_나온다(spark):
    events = [
        edit("Hurricane Milton", "2024-10-06T19:05:00.000Z", "alice"),
        edit("Hurricane Milton", "2024-10-06T19:40:00.000Z", "bob"),
        edit("Hurricane Milton", "2024-10-06T20:01:00.000Z", "carol"),
        edit("Strait of Hormuz", "2024-10-06T19:30:00.000Z", "dave"),
    ]
    assert stream_windows(spark, events) == batch_windows(events)


def test_봇_편집은_양쪽_다_빠진다(spark):
    events = [
        edit("Cat", "2025-06-01T10:10:00.000Z", "human"),
        edit("Cat", "2025-06-01T10:20:00.000Z", "botty", is_bot=True),
    ]
    stream, batch = stream_windows(spark, events), batch_windows(events)
    assert stream == batch
    assert batch[("enwiki", "Cat", "2025-06-01T10:00:00")] == (1, 1)


def test_is_bot_결측은_양쪽_다_봇이_아니다(spark):
    """스트리밍은 `~coalesce(is_bot, False)`, 배치는 `bool(rec.get("is_bot"))`.

    표현이 달라 갈리기 쉬운 지점이라 따로 고정한다. 둘 다 결측을 '봇 아님'으로 본다.
    """
    events = [
        edit("Cat", "2025-06-01T10:10:00.000Z", "alice", is_bot=None),   # 키 없음
        edit("Cat", "2025-06-01T10:20:00.000Z", "bob", is_bot=False),
    ]
    stream, batch = stream_windows(spark, events), batch_windows(events)
    assert stream == batch
    assert batch[("enwiki", "Cat", "2025-06-01T10:00:00")] == (2, 2)



def test_스트리밍은_비정규_제목을_자가_보정하지_않는다(spark):
    """🔴 두 경로의 제목 계약이 비대칭이다. 알고 두는 것과 모르고 당하는 것은 다르다.

    | 경로 | 제목 정규화 |
    | --- | --- |
    | 배치 | **읽는 지점에서 한다** (WP-92) — 구세대 -56 샤드가 밑줄형이라 |
    | 스트리밍 | 안 한다 — `producer/normalize.py` 가 Kafka 에 넣기 전에 이미 맞춘다 |

    스트리밍 쪽에 Spark 표현식으로 같은 규칙을 또 구현하면 파이썬 판과 갈릴 수 있다 —
    WP-91 이 없앤 "이름 같고 동작 다른 canonical_title" 이 그대로 재현된다.
    그래서 규칙은 `producer.normalize.canonical_title` 한 곳에만 둔다.

    ⚠️ 이 계약이 깨지는 유일한 경로는 **정규화를 안 거친 이벤트가 토픽에 들어가는 것**이다.
    그때 배치는 합치고 스트리밍은 쪼갠다 — 이 테스트가 그 차이를 눈에 보이게 박아둔다.
    """
    events = [edit("Hurricane_Milton", "2024-10-06T19:10:00.000Z", "alice")]
    stream, batch = stream_windows(spark, events), batch_windows(events)

    assert list(batch) == [("enwiki", "Hurricane Milton", "2024-10-06T19:00:00")]
    assert list(stream) == [("enwiki", "Hurricane_Milton", "2024-10-06T19:00:00")]
    assert stream != batch

# ---------------------------------------------------------------- 경계 조건

def test_정각에_걸친_편집은_다음_윈도우에_들어간다(spark):
    """`[start, end)` — 10:00:00 은 09시 창이 아니라 10시 창이다. 양쪽 같아야 한다."""
    events = [
        edit("Cat", "2025-06-01T09:59:59.999Z", "alice"),
        edit("Cat", "2025-06-01T10:00:00.000Z", "bob"),
    ]
    stream, batch = stream_windows(spark, events), batch_windows(events)
    assert stream == batch
    assert batch[("enwiki", "Cat", "2025-06-01T09:00:00")] == (1, 1)
    assert batch[("enwiki", "Cat", "2025-06-01T10:00:00")] == (1, 1)


def test_같은_초에_여러_편집도_각각_센다(spark):
    events = [
        edit("Cat", "2025-06-01T10:00:00.000Z", "alice"),
        edit("Cat", "2025-06-01T10:00:00.000Z", "bob"),
        edit("Cat", "2025-06-01T10:00:00.000Z", "alice"),
    ]
    stream, batch = stream_windows(spark, events), batch_windows(events)
    assert stream == batch
    assert batch[("enwiki", "Cat", "2025-06-01T10:00:00")] == (3, 2)   # 편집 3·편집자 2


def test_초_정밀도와_밀리초_정밀도가_같은_윈도우로_간다(spark):
    """덤프는 `.000Z`, EventStreams 는 초 정밀도(`Z`)로 온다. 파서가 둘 다 받아야 한다."""
    events = [
        edit("Cat", "2025-06-01T10:10:00Z", "alice"),
        edit("Cat", "2025-06-01T10:20:00.000Z", "bob"),
    ]
    stream, batch = stream_windows(spark, events), batch_windows(events)
    assert stream == batch
    assert batch[("enwiki", "Cat", "2025-06-01T10:00:00")] == (2, 2)


def test_날짜가_바뀌는_자정_경계(spark):
    events = [
        edit("Cat", "2025-05-31T23:50:00.000Z", "alice"),
        edit("Cat", "2025-06-01T00:10:00.000Z", "bob"),
    ]
    stream, batch = stream_windows(spark, events), batch_windows(events)
    assert stream == batch
    assert set(batch) == {
        ("enwiki", "Cat", "2025-05-31T23:00:00"),
        ("enwiki", "Cat", "2025-06-01T00:00:00"),
    }


def test_다른_위키_같은_제목은_안_섞인다(spark):
    events = [
        edit("Cat", "2025-06-01T10:10:00.000Z", "alice", wiki="enwiki"),
        edit("Cat", "2025-06-01T10:20:00.000Z", "bob", wiki="kowiki"),
    ]
    stream, batch = stream_windows(spark, events), batch_windows(events)
    assert stream == batch
    assert batch[("enwiki", "Cat", "2025-06-01T10:00:00")] == (1, 1)
    assert batch[("kowiki", "Cat", "2025-06-01T10:00:00")] == (1, 1)


# ---------------------------------------------------------------- 윈도우 길이 계약

def test_윈도우_길이_기본값이_양쪽_같다():
    """🔴 스트리밍 `DEFAULT_WINDOW_SIZE` 와 배치 `WINDOW_HOURS` 가 갈리면 안 된다.

    한쪽만 6시간으로 바꾸는 변경(WP-85 후속 검토)이 실제로 거론됐다.
    숫자를 코드에서 직접 읽어 비교한다 — 문서 주석은 갈려도 이 테스트는 안 갈린다.
    """
    from batch.historical_windows import WINDOW_HOURS
    from streaming.edit_windows import DEFAULT_WINDOW_SIZE

    assert DEFAULT_WINDOW_SIZE == f"{WINDOW_HOURS} hour"


def test_슬라이드가_윈도우_길이를_나눈다():
    """정각 시작 윈도우가 존재해야 배치와 대조할 수 있다.

    슬라이드가 윈도우 길이를 나누지 않으면(예: 7분) 정각에서 시작하는 윈도우가 안 생겨
    두 경로를 겹쳐 볼 구간 자체가 사라진다.
    """
    from streaming.edit_windows import DEFAULT_SLIDE_SIZE, DEFAULT_WINDOW_SIZE

    hours = int(DEFAULT_WINDOW_SIZE.split()[0])
    minutes = int(DEFAULT_SLIDE_SIZE.split()[0])
    assert (hours * 60) % minutes == 0


def test_editor_count_정밀도가_의도한_값인지():
    """🔴 `EDITOR_COUNT_RSD` 는 편집자 하한 게이트를 뒤집는 값이다.

    실덤프 200,000 events 대조에서 기본 `rsd=0.05` 가 13개 윈도우를 `2 → 1` 로
    과소 계수해 급증을 떨어뜨렸다 (2026-09-15, WP-83). `rsd=0.01` 과
    정확 `count_distinct` 는 불일치 0건이라 **0.01 로 확정했다**(WP-89).

    이 테스트는 값을 **고정**하는 게 아니라 **의식적으로 바꾸게** 하는 장치다.
    바꿀 때는 `streaming/edit_windows.py` 의 근거 주석과 명세 §11 을 같이 갱신한다.

    ⚠️ 합성 표본으로는 이 문제가 안 잡힌다 — 편집자가 몇 명뿐이면 HLL 희소 표현이
    정확하다. 그래서 상수 자체를 보는 테스트로 남긴다.
    """
    from streaming.edit_windows import EDITOR_COUNT_RSD

    assert EDITOR_COUNT_RSD == 0.01, (
        "값을 바꿨다면 실덤프 대조를 다시 돌리고 근거를 §11 에 남길 것"
    )


def test_창_길이를_바꾸면_두_경로가_같이_움직여야_한다(spark):
    """6시간 창으로 대조. 배치 판에는 창 길이 파라미터가 없어 정각 집계를 6시간으로 접는다.

    ⚠️ 이 테스트가 증명하는 건 "같은 창이면 같은 값" 까지다. 배치 `WINDOW_HOURS` 를
    실제로 6으로 바꾸는 건 별건이다 — `hour_of_day` 슬롯 정의(0..23)와 baseline 이
    같이 움직여야 한다.
    """
    events = [
        edit("Cat", "2025-06-01T12:10:00.000Z", "alice"),
        edit("Cat", "2025-06-01T14:20:00.000Z", "bob"),
        edit("Cat", "2025-06-01T17:59:00.000Z", "carol"),
        edit("Cat", "2025-06-01T18:01:00.000Z", "dave"),      # 다음 6시간 창
    ]
    stream = stream_windows(
        spark, events, window_size="6 hours", slide_size="6 hours")

    six_hour_start = {}
    for (wiki, title, hour), (count, _) in batch_windows(events).items():
        bucket = f"{hour[:11]}{(int(hour[11:13]) // 6) * 6:02d}:00:00"
        key = (wiki, title, bucket)
        six_hour_start[key] = six_hour_start.get(key, 0) + count

    assert {k: v[0] for k, v in stream.items()} == six_hour_start
