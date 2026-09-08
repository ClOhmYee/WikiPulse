"""Kafka `wiki.edits` -> 문서별 편집 윈도우 집계 (Spark Structured Streaming)

    spark-submit --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.3 \
                 streaming/edit_windows.py

이 잡이 하는 것은 집계까지다. 급증 판정과 클러스터링은 다음 스토리다.
    - 급증 판정 수식(z-score 임계·조회수 2차 판정)  -> WP-38
    - 클러스터링(Clickstream + Wikidata)            -> 미등록
    근거: docs/requirements-v0.1.md §3.2 2~4번

윈도우 길이는 아직 확정 전이라 환경 변수로 뺐다. 명세 §10 Open Issue —
"급증 판정 수식 확정" 이 끝나면 기본값을 고정한다.
"""

from __future__ import annotations

import os

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    BooleanType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
)

# producer/normalize.py 가 내보내는 edit_event 형태와 1:1로 맞춘다.
# 한쪽을 고치면 다른 쪽도 고쳐야 한다.
EDIT_EVENT_SCHEMA = StructType(
    [
        StructField("wiki", StringType()),
        StructField("domain", StringType()),
        StructField("title", StringType()),
        StructField("event_type", StringType()),
        StructField("rev_id", LongType()),
        StructField("rev_parent_id", LongType()),
        StructField("byte_delta", IntegerType()),
        StructField("new_length", IntegerType()),
        StructField("user", StringType()),
        StructField("is_bot", BooleanType()),
        StructField("is_minor", BooleanType()),
        StructField("event_ts", StringType()),
        StructField("event_ts_ms", LongType()),
        StructField("source", StringType()),
        StructField("meta_id", StringType()),
    ]
)


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def build_stream(spark: SparkSession):
    bootstrap = env("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
    topic = env("KAFKA_TOPIC", "wiki.edits")

    window_size = env("WINDOW_SIZE", "1 hour")
    slide_size = env("SLIDE_SIZE", "5 minutes")
    watermark = env("WATERMARK", "10 minutes")

    raw = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", bootstrap)
        .option("subscribe", topic)
        .option("startingOffsets", env("STARTING_OFFSETS", "latest"))
        # 한 마이크로배치가 너무 커지지 않게. 재시작 후 밀린 구간을 따라잡을 때
        # 이게 없으면 첫 배치가 토픽 전체를 한 번에 읽으려 든다.
        .option("maxOffsetsPerTrigger", env("MAX_OFFSETS_PER_TRIGGER", "50000"))
        .load()
    )

    events = (
        raw.select(F.from_json(F.col("value").cast("string"), EDIT_EVENT_SCHEMA).alias("e"))
        .select("e.*")
        .withColumn("event_ts", F.to_timestamp("event_ts"))
    )

    # 노이즈 제거. 지금은 봇만 거른다.
    # 1인 반복 편집·되돌리기 필터는 급증 판정 스토리에서 붙인다 (WP-38).
    # 봇 편집이 적지 않다 — 2026-09-08 표본에서 enwiki 41건 중 11건이 봇이었다.
    filtered = events.filter(~F.coalesce(F.col("is_bot"), F.lit(False)))

    return (
        filtered
        # 늦게 온 이벤트를 언제까지 받아줄지. 이걸 안 걸면 상태가 무한히 쌓인다.
        .withWatermark("event_ts", watermark)
        .groupBy(
            F.window("event_ts", window_size, slide_size),
            F.col("wiki"),
            F.col("title"),
        )
        .agg(
            F.count("*").alias("edit_count"),
            F.approx_count_distinct("user").alias("editor_count"),
            F.sum("byte_delta").alias("byte_delta_sum"),
            F.max("event_ts").alias("last_edit_ts"),
        )
        .select(
            F.col("window.start").alias("window_start"),
            F.col("window.end").alias("window_end"),
            "wiki",
            "title",
            "edit_count",
            "editor_count",
            "byte_delta_sum",
            "last_edit_ts",
        )
    )


def main() -> None:
    spark = (
        SparkSession.builder.appName("wikipulse-edit-windows")
        .config("spark.sql.session.timeZone", "UTC")
        # 셔플 파티션 기본값 200 은 이 규모(초당 2건)에 과하다.
        # 작은 파티션이 200개면 태스크 기동 비용이 계산 비용을 넘는다.
        .config("spark.sql.shuffle.partitions", env("SHUFFLE_PARTITIONS", "8"))
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel(env("SPARK_LOG_LEVEL", "WARN"))

    aggregated = build_stream(spark)

    # 싱크는 지금 콘솔이다. PostgreSQL 적재는 데이터 모델(WP-35)이
    # 확정된 뒤에 붙인다. 지금 스키마를 넣으면 두 번 고치게 된다.
    query = (
        aggregated.writeStream.outputMode("update")
        .format(env("SINK", "console"))
        .option("truncate", "false")
        .option("numRows", env("CONSOLE_ROWS", "20"))
        .option("checkpointLocation", env("CHECKPOINT_DIR", "/tmp/wikipulse-checkpoint"))
        .trigger(processingTime=env("TRIGGER_INTERVAL", "30 seconds"))
        .start()
    )
    query.awaitTermination()


if __name__ == "__main__":
    main()
