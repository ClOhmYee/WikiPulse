"""Spark 판 build_baseline 이 순수 판과 **같은 값**을 내는지 (WP-60).

기준선은 두 경로로 계산된다.
    순수 파이썬 : baseline_rows.build_rows   (적재 경로, baseline_sink.py 가 쓴다)
    Spark 배치  : baseline.build_baseline    (대량 처리 경로)
🔴 두 판이 갈리면 기준선이 에러 없이 달라지고, edit_z 가 통째로 틀린다. 이 파일이
   같은 입력에 같은 값이 나오는지 고정한다.

Spark 세션을 띄우므로 pyspark 가 있어야 돌고, 느리다(수십 초). 순수 판 단독 검증은
test_baseline_rows.py 에 있다 — 같은 파일에 두면 pyspark 없는 환경에서 함께 skip 되어
정작 순수 판 계약이 깨져도 아무도 모른다.

⚠️ 워커 파이썬 경로는 conftest.py 가 고정한다. 안 하면 "CreateProcess error=2" 로 죽고
   파이썬 버전 문제로 오진하게 된다.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from spike.baseline_rows import build_rows

pyspark = pytest.importorskip("pyspark", reason="pyspark 미설치 — 이 파일은 건너뛴다")

from pyspark.sql import SparkSession  # noqa: E402
from pyspark.sql.types import (  # noqa: E402
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

from spike.baseline import build_baseline  # noqa: E402

SCHEMA = StructType([
    StructField("wiki", StringType()),
    StructField("title", StringType()),
    StructField("window_start", TimestampType()),
    StructField("edit_count", LongType()),
    StructField("views", DoubleType()),
])

HALFLIFE = 14.0
AS_OF = "2025-06-09"          # 월요일


@pytest.fixture(scope="module")
def spark():
    session = (
        SparkSession.builder.appName("wikipulse-baseline-test")
        .master("local[1]")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "1")
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


def utc(*args) -> datetime:
    """UTC 로 못박은 datetime.

    ⚠️ naive datetime 을 createDataFrame 에 주면 Spark 가 **드라이버의 로컬 시간대**로
    해석해 UTC 로 옮긴다. KST 개발 PC 에서는 9시간 밀려 hour_of_day 가 0 대신 15 가
    되는데, 에러 없이 슬롯만 조용히 틀린다(2026-09-14 실제로 겪음).
    세션 timeZone=UTC 는 이걸 막아주지 않는다 — 입력을 aware 로 준다.
    """
    return datetime(*args, tzinfo=timezone.utc)


def sample():
    """같은 슬롯(00시)에 2주치 관측 + 다른 슬롯(05시) 하나."""
    return [
        ("enwiki", "Iran", utc(2025, 6, 9, 0, 30), 10, 100.0),   # age 0
        ("enwiki", "Iran", utc(2025, 6, 2, 0, 15), 2, 20.0),     # age 7
        ("enwiki", "Iran", utc(2025, 6, 9, 5, 0), 4, 40.0),      # 다른 슬롯(05시)
    ]


def pure_rows():
    windows = [
        {"wiki": w, "title": t, "window_start": ts.strftime("%Y-%m-%dT%H:00:00"),
         "hour_of_day": ts.hour, "edit_count": e, "views": v}
        for w, t, ts, e, v in sample()
    ]
    return {(r.hour_of_day): r for r in build_rows(
        windows, as_of=date.fromisoformat(AS_OF), halflife_days=HALFLIFE)}


def spark_rows(spark):
    df = spark.createDataFrame(sample(), SCHEMA)
    out = build_baseline(df, AS_OF, halflife_days=HALFLIFE)
    return {r["hour_of_day"]: r for r in out.collect()}


def test_두_판이_같은_슬롯을_만든다(spark):
    assert set(spark_rows(spark)) == set(pure_rows())


def test_두_판의_edit_ewma가_같다(spark):
    pure, sp = pure_rows(), spark_rows(spark)
    for hour, row in pure.items():
        assert sp[hour]["edit_ewma"] == pytest.approx(row.edit_ewma, rel=1e-9), hour


def test_두_판의_edit_stddev가_같다(spark):
    """2-pass 가중 분산. 1-pass(sum(wv²)/sum(w)−mean²)로 바꾸면 여기서 갈린다."""
    pure, sp = pure_rows(), spark_rows(spark)
    for hour, row in pure.items():
        assert sp[hour]["edit_stddev"] == pytest.approx(row.edit_stddev, rel=1e-9), hour


def test_두_판의_view_ewma와_sample_days가_같다(spark):
    pure, sp = pure_rows(), spark_rows(spark)
    for hour, row in pure.items():
        assert sp[hour]["view_ewma"] == pytest.approx(row.view_ewma, rel=1e-9), hour
        assert sp[hour]["sample_days"] == row.sample_days, hour


def test_두_판의_view_stddev가_같다(spark):
    """WP-90 에서 추가된 컬럼. 조회수 z 의 유일한 입력이라 두 판이 갈리면
    배치로 만든 기준선과 Spark 로 만든 기준선이 **다른 급증 판정**을 낸다.

    조회수 결측은 분자·분모 양쪽에서 빠져야 한다 — 평균과 같은 표본을 써야 값이 맞는다.
    """
    pure, sp = pure_rows(), spark_rows(spark)
    for hour, row in pure.items():
        if row.view_stddev is None:
            assert sp[hour]["view_stddev"] is None, hour
        else:
            assert sp[hour]["view_stddev"] == pytest.approx(row.view_stddev, rel=1e-9), hour


def test_28일_경계가_양쪽_모두_적용된다(spark):
    """창 밖(29일 전) 관측은 두 판 모두 버려야 한다."""
    rows = sample() + [("enwiki", "Iran", utc(2025, 5, 1, 0, 0), 9999, 9999.0)]
    df = spark.createDataFrame(rows, SCHEMA)
    sp = {r["hour_of_day"]: r for r in
          build_baseline(df, AS_OF, halflife_days=HALFLIFE).collect()}
    # 창 밖 값(9999)이 섞였다면 edit_ewma 가 폭발한다
    assert sp[0]["edit_ewma"] == pytest.approx(pure_rows()[0].edit_ewma, rel=1e-9)
