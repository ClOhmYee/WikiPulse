"""Kafka `wiki.edits` -> 문서별 편집 윈도우 집계 (Spark Structured Streaming)

    spark-submit --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.3 \
                 streaming/edit_windows.py

싱크는 두 가지다 (`SINK` 환경변수, 기본 `console`).
    SINK=console  집계 결과를 찍기만 한다. 여태 동작 그대로다.
    SINK=spike    판정까지 간다 — `page_baseline` 조회 -> `detect()` ->
                  `spike(source='live')` 적재. `DATABASE_URL` 이 필요하다.
                  연결은 `streaming/live_spike.py` (WP-100).

~~"이 잡이 하는 것은 집계까지다. 급증 판정과 클러스터링은 다음 스토리다"~~
    -> 급증 판정은 붙었다 (2026-09-15, WP-100). ~~클러스터링은 아직이다~~
    -> 클러스터링도 붙었다 (2026-09-16, WP-102): `cluster/driver.py --source live`
    가 `spike.source='live'` 만 읽어 `issue_cluster(source='live')` 를 만든다.
    ⚠️ 클러스터 생산은 이 스트리밍 잡 안에서 돌지 않는다 — `spike` 를 사이에 둔
    **별도 실행**이다. 이 잡은 여전히 `spike` 까지만 쓴다.
    근거: docs/requirements-v0.3.md §3.2 2~4번

윈도우 길이는 아직 확정 전이라 환경 변수로 뺐다. 명세 §10 Open Issue —
"급증 판정 수식 확정" 이 끝나면 기본값을 고정한다.
"""

from __future__ import annotations

import os
import sys

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

#: 싱크 선택. 기본은 여태와 같은 콘솔이다 — 기존 실행 방식을 바꾸지 않는다.
#: `SINK=spike` 면 판정까지 가서 `spike(source='live')` 에 적재한다
#: (`streaming/live_spike.py`). 그 경로는 `DATABASE_URL` 이 필요하다.
#: 그 외 값은 여태처럼 Spark 내장 포맷 이름으로 그대로 넘긴다(console·memory 등).
SINK_CONSOLE = "console"
SINK_SPIKE = "spike"

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


def ensure_project_root_on_path() -> None:
    """`data-pipeline/` 를 `sys.path` 에 올린다. spark-submit 으로 돌 때 필요하다.

    🔴 **spark-submit 은 스크립트가 있는 디렉터리를 sys.path 에 넣는다** — 작업
    디렉터리가 아니다. 그래서 `spark-submit streaming/edit_windows.py` 로 돌리면
    `/opt/app/streaming` 만 올라가고 `streaming.live_spike`·`spike.runtime` 이
    `ModuleNotFoundError` 로 죽는다 (2026-09-15 컨테이너에서 실측).

    콘솔 싱크는 이 파일 밖을 안 import 해서 여태 안 드러났다. LIVE 싱크를 붙이면서
    드러난 것이라 여기서 흡수한다 — 호출자가 PYTHONPATH 를 기억해야 하는 구조로
    두지 않는다. 이미 올라가 있으면 아무것도 하지 않는다(pytest·모듈 실행 경로).
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)


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

    aggregations = [
        F.count("*").alias("edit_count"),
        F.approx_count_distinct("user", EDITOR_COUNT_RSD).alias("editor_count"),
        F.sum("byte_delta").alias("byte_delta_sum"),
        F.max("event_ts").alias("last_edit_ts"),
    ]
    outputs = ["edit_count", "editor_count", "byte_delta_sum", "last_edit_ts"]
    # 시점 감사 증거 (V9, WP-129 2번). 판정에는 안 쓴다.
    # revision id 는 위키 전체에서 단조 증가하므로 최대값 하나면 "여기까지 봤다" 가 된다.
    # ⚠️ rev_id 가 없는 입력도 있다(옛 샤드·일부 테스트 대역). 없는 걸 만들지 않는다 —
    #    0 을 넣으면 "증거 없음" 과 "증거가 0" 이 구분되지 않는다.
    if "rev_id" in filtered.columns:
        aggregations.append(F.max("rev_id").alias("max_rev_id"))
        outputs.append("max_rev_id")

    return (
        filtered
        .groupBy(
            F.window("event_ts", window_size, slide_size),
            F.col("wiki"),
            F.col("title"),
        )
        .agg(*aggregations)
        .select(
            F.col("window.start").alias("window_start"),
            F.col("window.end").alias("window_end"),
            "wiki",
            "title",
            *outputs,
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

    writer = (
        aggregated.writeStream.outputMode("update")
        .option("checkpointLocation", env("CHECKPOINT_DIR", "/tmp/wikipulse-checkpoint"))
        .trigger(processingTime=env("TRIGGER_INTERVAL", "30 seconds"))
    )

    sink = env("SINK", SINK_CONSOLE)
    if sink == SINK_SPIKE:
        # ~~"PostgreSQL 적재는 데이터 모델(WP-35)이 확정된 뒤에"~~
        # -> V1 스키마와 SpikeRuntime(-94)이 서고 나서 연결했다 (2026-09-15, -100).
        dsn = env("DATABASE_URL", "")
        if not dsn:
            # 조용히 콘솔로 떨어지지 않는다 — 적재한 줄 알고 빈 테이블을 보게 된다.
            raise SystemExit(
                f"SINK={SINK_SPIKE} 에는 DATABASE_URL 이 필요하다. "
                "예: postgresql://wikipulse:wikipulse@postgres:5432/wikipulse"
            )
        ensure_project_root_on_path()
        from streaming.live_spike import make_spike_batch_writer
        query = writer.foreachBatch(make_spike_batch_writer(dsn)).start()
    else:
        query = (
            writer.format(sink)
            .option("truncate", "false")
            .option("numRows", env("CONSOLE_ROWS", "20"))
            .start()
        )
    query.awaitTermination()


if __name__ == "__main__":
    main()
