"""28일 기준선 산출 (Spark 배치). page_baseline 테이블을 채운다.

    spark-submit spike/baseline.py

명세 §3.2 4번. 문서 × 요일·시간대(0~167) 로 나눠 EWMA 를 굴린다.

왜 동시간대로 나누나
    위키 편집·조회는 요일·시간대를 크게 탄다. 하나의 평균으로 뭉치면 평일
    낮의 정상 트래픽이 주말 새벽 기준으로는 급증처럼 보인다. 168개 슬롯으로
    나눠 "같은 시간대의 평소" 와 비교한다.

이 잡은 골격이다
    실제 EWMA 갱신 로직과 스케줄은 baseline 데이터 소스(Pageviews 덤프·
    mediawiki_history)가 HDFS 에 적재된 뒤 붙인다. 지금은 스키마와 집계
    형태만 잡아둔다. 판정 수식(detector.py)이 이 테이블을 읽는다.
"""

from __future__ import annotations

import os

from pyspark.sql import SparkSession
from pyspark.sql import functions as F


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def hour_of_week(ts_col):
    """타임스탬프 -> 0..167 (월요일 00시 UTC = 0)."""
    # Spark dayofweek: 1=일요일 .. 7=토요일. 월=0 으로 맞춘다.
    dow = (F.dayofweek(ts_col) + 5) % 7  # 월=0 .. 일=6
    return dow * 24 + F.hour(ts_col)


def build_baseline(edit_windows):
    """문서 × 요일·시간대 편집 EWMA·표준편차.

    입력: (page_id, window_start, edit_count, views) 형태의 과거 28일.
    실제로는 여기에 지수가중을 넣지만, 골격에서는 평균·표준편차로 둔다 —
    EWMA 가중치는 데이터가 붙은 뒤 튜닝한다.
    """
    return (
        edit_windows
        .withColumn("hour_of_week", hour_of_week(F.col("window_start")))
        .groupBy("page_id", "hour_of_week")
        .agg(
            F.avg("edit_count").alias("edit_ewma"),
            F.stddev_pop("edit_count").alias("edit_stddev"),
            F.avg("views").alias("view_ewma"),
            F.countDistinct(F.to_date("window_start")).alias("sample_days"),
        )
    )


def main() -> None:
    spark = (
        SparkSession.builder.appName("wikipulse-baseline")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel(env("SPARK_LOG_LEVEL", "WARN"))

    # 소스는 HDFS 의 과거 집계. 경로가 붙기 전엔 no-op 이라 안내만 찍는다.
    source = env("BASELINE_SOURCE", "")
    if not source:
        print("BASELINE_SOURCE 미지정 — 기준선 소스(HDFS 경로)가 아직 없다.")
        print("스키마·집계 형태는 build_baseline() 참고. 데이터 적재 후 연결.")
        spark.stop()
        return

    windows = spark.read.parquet(source)
    baseline = build_baseline(windows)
    baseline.write.mode("overwrite").format(env("SINK", "console")).save()
    spark.stop()


if __name__ == "__main__":
    main()
