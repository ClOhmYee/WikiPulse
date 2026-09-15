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

from pyspark.sql import DataFrame, SparkSession
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
#: 윈도우 길이. 🔴 배치 `batch.historical_windows.WINDOW_HOURS` 와 한 벌이다 —
#: 다르면 `edit_z` 가 에러 없이 어긋난다. 대조 테스트: `tests/test_stream_batch_parity.py`.
DEFAULT_WINDOW_SIZE = "1 hour"

#: 슬라이드 간격. ⚠️ 배치는 정각 tumbling 이라 슬라이드 개념이 없다. 두 경로를 대조할 때는
#: **정각에서 시작하는 윈도우만** 비교한다 — 슬라이드가 윈도우 길이를 나누므로 그런 윈도우가
#: 항상 존재하고, 그게 배치의 tumbling 윈도우와 같은 구간이다.
DEFAULT_SLIDE_SIZE = "5 minutes"

DEFAULT_WATERMARK = "10 minutes"

#: `approx_count_distinct` 의 상대 표준오차. ~~0.05 (Spark 기본)~~ → **0.01** (2026-09-15,
#: WP-89). 기본값이 편집자 하한을 뒤집었다 — 아래 실측.
#:
#: 🔴 **이 값이 편집자 하한 게이트(detector.MIN_DISTINCT_EDITORS=2)를 뒤집는다.**
#: 실덤프 200,000 events(enwiki 2025-06, 윈도우 118,521)로 배치 정확값과 대조한 결과
#: (2026-09-15, WP-83):
#:
#:     rsd=0.05 (기본)  불일치 21건 — 전부 과소 계수 {2→1: 13, 3→2: 4, 4→3: 1, 5→4: 3}
#:                      그중 13건이 게이트를 뒤집는다(editor≥2 윈도우 5,427 중 0.240%)
#:     rsd=0.01         불일치 0건
#:     정확 count_distinct  불일치 0건
#:
#: 2→1 은 **진짜 급증을 떨어뜨린다**(미탐). 편집자 수는 애초에 한 자릿수라 HLL 의
#: 이득이 거의 없는 구간이다.
#:
#: 정확 `count_distinct` 도 0건이지만 안 골랐다 — 윈도우마다 편집자 집합을 통째로 들고
#: 있어야 해서 스트리밍 상태가 커지는데, `rsd=0.01` 이 이미 0건이라 그 대가를 치를 이유가
#: 없다. `rsd=0.005` 는 0.01 과 결과가 같고 메모리만 더 쓴다.
#: ⚠️ 실규모 상태 크기는 Spark 2노드(WP-27)가 서기 전엔 못 잰다 — 그때 재확인한다.
#:
#: ⚠️ ~~"편집자 1~10명 구간에서 두 값이 일치함을 실측했다(불일치 0건)"~~
#: (`batch/historical_windows.py` · `spike/README.md`, 2026-09-15 -85) → **표본을 키우니
#: 틀렸다.** 작은 표본에서는 HLL 희소 표현이 정확해 안 드러난다.
#:
EDITOR_COUNT_RSD = 0.01

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


def aggregate_edit_windows(
    events: DataFrame,
    *,
    window_size: str = DEFAULT_WINDOW_SIZE,
    slide_size: str = DEFAULT_SLIDE_SIZE,
    watermark: str = DEFAULT_WATERMARK,
) -> DataFrame:
    """파싱된 edit_event DataFrame → 문서 × 윈도우 집계.

    Kafka 읽기와 분리해 둔 이유는 **배치 경로(batch/historical_windows.py)와 값이
    같은지 대조**하기 위해서다 (WP-83). 스트리밍 쿼리를 띄우지 않고 같은
    변환을 배치 DataFrame 에 걸 수 있어야 대조 테스트가 성립한다.

    🔴 이 함수의 필터·집계는 배치 판과 한 벌이다. 한쪽을 고치면 다른 쪽도 고친다 —
    갈리면 `edit_z` 가 에러 없이 어긋난다.

    watermark 는 스트리밍에서만 건다. 배치 DataFrame 에 걸면 의미가 없다.
    """
    # 노이즈 제거. 지금은 봇만 거른다.
    # 1인 반복 편집·되돌리기 필터는 급증 판정 스토리에서 붙인다 (WP-38).
    # 봇 편집이 적지 않다 — 2026-09-08 표본에서 enwiki 41건 중 11건이 봇이었다.
    filtered = events.filter(~F.coalesce(F.col("is_bot"), F.lit(False)))

    if filtered.isStreaming:
        # 늦게 온 이벤트를 언제까지 받아줄지. 이걸 안 걸면 상태가 무한히 쌓인다.
        filtered = filtered.withWatermark("event_ts", watermark)

    return (
        filtered
        .groupBy(
            F.window("event_ts", window_size, slide_size),
            F.col("wiki"),
            F.col("title"),
        )
        .agg(
            F.count("*").alias("edit_count"),
            F.approx_count_distinct("user", EDITOR_COUNT_RSD).alias("editor_count"),
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


def build_stream(spark: SparkSession):
    bootstrap = env("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
    topic = env("KAFKA_TOPIC", "wiki.edits")

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

    return aggregate_edit_windows(
        events,
        window_size=env("WINDOW_SIZE", DEFAULT_WINDOW_SIZE),
        slide_size=env("SLIDE_SIZE", DEFAULT_SLIDE_SIZE),
        watermark=env("WATERMARK", DEFAULT_WATERMARK),
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
