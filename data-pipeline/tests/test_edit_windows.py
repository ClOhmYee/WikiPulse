"""Spark 집계 로직 검증.

여기서 잡으려는 실패는 하나다 — streaming/edit_windows.py 의 EDIT_EVENT_SCHEMA 가
producer/normalize.py 의 출력과 어긋나는 것. from_json 은 스키마가 안 맞으면
예외를 던지지 않고 조용히 null 을 채운다. 그러면 집계가 전부 0이 되는데
에러는 안 난다.

Kafka 없이 돈다. 스트리밍 소스 대신 같은 변환을 배치 DataFrame 에 적용한다.
Docker·Kafka 가 필요한 end-to-end 는 별개다.
"""

from __future__ import annotations

import copy
import json
import os
import time

import pytest

from producer.normalize import normalize

pyspark = pytest.importorskip("pyspark", reason="pyspark 미설치 — 이 파일은 건너뛴다")

from pyspark.sql import SparkSession  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

from streaming.edit_windows import (  # noqa: E402
    EDIT_EVENT_SCHEMA,
    aggregate_edit_windows,
    prepare_live_events,
)

BASE = {
    "$schema": "/mediawiki/recentchange/1.0.0",
    "meta": {
        "domain": "en.wikipedia.org",
        "id": "b18aa477-0c22-4475-9416-23367a447b2b",
        "dt": "2026-09-08T00:24:20.990Z",
    },
    "type": "edit",
    "namespace": 0,
    "title": "Hurricane Milton",
    "timestamp": 1788827059,
    "user": "Alice",
    "bot": False,
    "minor": False,
    "length": {"old": 1000, "new": 1100},
    "revision": {"old": 10, "new": 11},
    "wiki": "enwiki",
}


def event(**overrides):
    raw = copy.deepcopy(BASE)
    meta = overrides.pop("meta", {})
    raw["meta"].update(meta)
    raw.update(overrides)
    return json.dumps(normalize(raw), ensure_ascii=False)


@pytest.fixture(scope="module")
def spark():
    session = (
        SparkSession.builder.appName("test-edit-windows")
        .master("local[2]")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


def parse(spark, payloads):
    """edit_windows.py 의 파싱 단계와 같은 변환."""
    df = spark.createDataFrame([(p,) for p in payloads], "value string")
    return (
        df.select(F.from_json(F.col("value"), EDIT_EVENT_SCHEMA).alias("e"))
        .select("e.*")
        .withColumn("event_ts", F.to_timestamp("event_ts"))
    )


def test_live_preparation_removes_duplicate_meta_id(spark):
    duplicate = event(meta={"id": "same-id"})
    raw = spark.createDataFrame([(duplicate,), (duplicate,)], "value string")
    assert prepare_live_events(raw, watermark="10 minutes").count() == 1


@pytest.mark.parametrize("meta_id", [None, "", " \t"])
def test_live_preparation_rejects_missing_or_blank_meta_id(spark, meta_id):
    payload = json.loads(event())
    payload["meta_id"] = meta_id
    payload = json.dumps(payload)
    raw = spark.createDataFrame([(payload,)], "value string")
    assert prepare_live_events(raw, watermark="10 minutes").count() == 0


def test_live_pipeline_does_not_crash_when_planning_second_micro_batch(spark):
    raw = (
        spark.readStream.format("rate-micro-batch")
        .option("rowsPerBatch", 1)
        .option("advanceMillisPerBatch", 1000)
        .option("startTimestamp", 1788826200000)
        .load()
        .select(
            F.to_json(
                F.struct(
                    F.lit("enwiki").alias("wiki"),
                    F.lit("en.wikipedia.org").alias("domain"),
                    F.lit("Hurricane Milton").alias("title"),
                    F.lit("edit").alias("event_type"),
                    (F.col("value") + 1).cast("long").alias("rev_id"),
                    F.col("value").cast("long").alias("rev_parent_id"),
                    F.lit(100).alias("byte_delta"),
                    F.lit(1100).alias("new_length"),
                    F.lit("Alice").alias("user"),
                    F.lit(False).alias("is_bot"),
                    F.lit(False).alias("is_minor"),
                    F.col("timestamp").cast("string").alias("event_ts"),
                    (F.col("timestamp").cast("double") * 1000)
                    .cast("long")
                    .alias("event_ts_ms"),
                    F.lit("eventstreams").alias("source"),
                    F.concat(F.lit("batch-"), F.col("value")).alias("meta_id"),
                )
            ).alias("value")
        )
    )
    aggregated = aggregate_edit_windows(
        prepare_live_events(raw, watermark="10 minutes")
    )

    def count_watermarks(plan):
        children = plan.children()
        return int(plan.nodeName() == "EventTimeWatermark") + sum(
            count_watermarks(children.apply(index)) for index in range(children.size())
        )

    # Windows PySpark cannot create a local streaming checkpoint without Hadoop's
    # native DLL.  The logical plan still gives a platform-independent regression:
    # the broken implementation contains two EventTimeWatermark nodes.
    assert count_watermarks(aggregated._jdf.logicalPlan()) == 1
    if os.name == "nt":
        pytest.skip("Windows lacks the Hadoop native DLL required by writeStream")

    query = (
        aggregated.writeStream.format("memory")
        .queryName("test_second_micro_batch_watermark")
        .outputMode("update")
        .trigger(processingTime="100 milliseconds")
        .start()
    )
    try:
        deadline = time.monotonic() + 30
        while query.isActive and len(query.recentProgress) < 2:
            query.awaitTermination(0.2)
            assert time.monotonic() < deadline, "second micro-batch did not finish"
        assert len(query.recentProgress) >= 2
    finally:
        query.stop()


def test_스키마가_프로듀서_출력과_맞는다(spark):
    """어긋나면 from_json 이 조용히 null 을 채운다 — 이게 이 테스트의 존재 이유다."""
    rows = parse(spark, [event()]).collect()
    assert len(rows) == 1
    row = rows[0].asDict()

    null_fields = [k for k, v in row.items() if v is None]
    assert not null_fields, f"스키마 불일치로 null 이 된 필드: {null_fields}"

    assert row["wiki"] == "enwiki"
    assert row["title"] == "Hurricane Milton"
    assert row["byte_delta"] == 100
    assert row["is_bot"] is False


def test_스키마_필드가_정규화_출력_키와_정확히_같다():
    """Spark 없이도 도는 검사. 한쪽에 필드를 추가하고 다른 쪽을 잊는 걸 막는다."""
    produced = set(json.loads(event()).keys())
    declared = {field.name for field in EDIT_EVENT_SCHEMA.fields}
    assert produced == declared, (
        f"프로듀서에만 있음: {produced - declared} / 스키마에만 있음: {declared - produced}"
    )


def test_event_ts_가_타임스탬프로_파싱된다(spark):
    """문자열로 남으면 window() 가 실패한다."""
    dtype = dict(parse(spark, [event()]).dtypes)["event_ts"]
    assert dtype == "timestamp"


def test_봇_편집은_집계에서_빠진다(spark):
    payloads = [
        event(user="Alice"),
        event(user="BotOne", bot=True),
        event(user="BotTwo", bot=True),
    ]
    kept = parse(spark, payloads).filter(
        ~F.coalesce(F.col("is_bot"), F.lit(False))
    )
    assert kept.count() == 1
    assert kept.first()["user"] == "Alice"


def test_문서별로_편집수와_편집자수를_센다(spark):
    payloads = [
        event(user="Alice", meta={"dt": "2026-09-08T00:10:00.000Z"}),
        event(user="Bob", meta={"dt": "2026-09-08T00:20:00.000Z"}),
        event(user="Alice", meta={"dt": "2026-09-08T00:30:00.000Z"}),
        event(title="Iran", user="Carol", meta={"dt": "2026-09-08T00:15:00.000Z"}),
    ]
    result = (
        parse(spark, payloads)
        .groupBy(F.window("event_ts", "1 hour"), "wiki", "title")
        .agg(
            F.count("*").alias("edit_count"),
            F.approx_count_distinct("user").alias("editor_count"),
            F.sum("byte_delta").alias("byte_delta_sum"),
        )
        .collect()
    )
    by_title = {r["title"]: r for r in result}

    assert by_title["Hurricane Milton"]["edit_count"] == 3
    assert by_title["Hurricane Milton"]["editor_count"] == 2  # Alice, Bob
    assert by_title["Hurricane Milton"]["byte_delta_sum"] == 300
    assert by_title["Iran"]["edit_count"] == 1


def test_다른_시간_윈도우는_따로_집계된다(spark):
    payloads = [
        event(meta={"dt": "2026-09-08T00:30:00.000Z"}),
        event(meta={"dt": "2026-09-08T03:30:00.000Z"}),
    ]
    windows = (
        parse(spark, payloads)
        .groupBy(F.window("event_ts", "1 hour"), "wiki", "title")
        .count()
        .collect()
    )
    assert len(windows) == 2
    assert all(row["count"] == 1 for row in windows)


def test_새_문서도_집계에_들어간다(spark):
    """type=new 는 length.old 가 없어 byte_delta 계산 경로가 다르다."""
    payload = event(type="new", length={"new": 500}, revision={"new": 1})
    row = parse(spark, [payload]).first()
    assert row["event_type"] == "new"
    assert row["byte_delta"] == 500
    assert row["rev_parent_id"] is None
