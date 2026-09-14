"""28일 기준선 산출 (Spark 배치). page_baseline 테이블을 채운다.

    cd data-pipeline && PYTHONPATH=. spark-submit spike/baseline.py

명세 §3.2 4번. 문서 × 요일·시간대(0~167) 로 나눠 EWMA 를 굴린다.

왜 동시간대로 나누나
    위키 편집·조회는 요일·시간대를 크게 탄다. 하나의 평균으로 뭉치면 평일
    낮의 정상 트래픽이 주말 새벽 기준으로는 급증처럼 보인다. 168개 슬롯으로
    나눠 "같은 시간대의 평소" 와 비교한다.

입력·키 (WP-60)
    입력은 Historical Window 산출물(WP-58): (wiki, title, window_start,
    hour_of_week, edit_count, views). 문서 키는 **(wiki, title)** 이다 — 파이프라인
    전체가 그렇고, wiki_page.id 해석은 적재 시점(baseline_sink.py)에 한다.

⚠️ 이 Spark 판은 로컬에서 검증되지 않았다
    PySpark 3.5 워커가 3.12+ 에서 죽어(tests/conftest.py) 개발 PC 에서 돌릴 수 없고,
    Spark 2노드(WP-27)·HDFS(-28)도 아직 없다. 실동작이 검증된 경로는
    같은 수식의 순수 파이썬 판(baseline_rows.py + baseline_sink.py)이다.
    🔴 두 판이 갈리면 기준선이 조용히 달라진다 — 가중 정의는 ewma.py 한 곳에서만 온다.
"""

from __future__ import annotations

import os

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

# ⚠️ 절대 임포트다. spark-submit 은 이 파일을 **스크립트로** 실행해서 패키지 상대
# 임포트(`from .ewma import ...`)가 깨진다. 저장소 루트를 PYTHONPATH 에 두고 돌린다
# (아래 실행 예). 형제 모듈(baseline_rows·baseline_sink)은 `python -m` 으로 도니 상대 임포트다.
from spike.baseline_rows import BASELINE_WINDOW_DAYS
from spike.ewma import DEFAULT_HALFLIFE_DAYS


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def hour_of_week(ts_col):
    """타임스탬프 -> 0..167 (월요일 00시 UTC = 0)."""
    # Spark dayofweek: 1=일요일 .. 7=토요일. 월=0 으로 맞춘다.
    dow = (F.dayofweek(ts_col) + 5) % 7  # 월=0 .. 일=6
    return dow * 24 + F.hour(ts_col)


GROUP_KEYS = ["wiki", "title", "hour_of_week"]


def build_baseline(edit_windows, as_of, halflife_days=DEFAULT_HALFLIFE_DAYS,
                   window_days=BASELINE_WINDOW_DAYS):
    """문서 × 요일·시간대 편집 EWMA·표준편차. baseline_rows.build_rows 의 Spark 판.

    입력: (wiki, title, window_start, edit_count, views) — WP-58 산출물.
    as_of: 기준선 창의 끝(날짜 문자열 "YYYY-MM-DD"). 창은 (as_of-28일, as_of].

    가중 정의는 ewma.py 와 같다: weight = 0.5 ** (경과일 / 반감기).
    분산은 2-pass(평균을 join 해 되돌림)로 낸다 — sum(wv²)/sum(w) − mean² 1-pass 가
    더 싸지만 큰 값에서 소거 오차가 나고, 순수 판(ewma.ewma_mean_std)이 2-pass 라
    값이 갈린다. 셔플 한 번을 더 쓰더라도 두 판을 같게 둔다.
    """
    day = F.to_date("window_start")
    age_days = F.datediff(F.to_date(F.lit(as_of)), day)

    scoped = (
        edit_windows
        .withColumn("hour_of_week", hour_of_week(F.col("window_start")))
        .withColumn("_day", day)
        .withColumn("_age", age_days)
        # 28일 경계. 안 걸면 기준선이 소스 전체로 번져 "평소"가 아니게 된다.
        .filter((F.col("_age") >= 0) & (F.col("_age") < window_days))
        .withColumn("_w", F.pow(F.lit(0.5), F.col("_age") / F.lit(float(halflife_days))))
    )

    # 1-pass: 가중 평균·표본일수. 조회수는 결측을 뺀 가중합이라 분모가 따로다.
    means = scoped.groupBy(*GROUP_KEYS).agg(
        (F.sum(F.col("_w") * F.col("edit_count")) / F.sum("_w")).alias("edit_ewma"),
        (F.sum(F.when(F.col("views").isNotNull(), F.col("_w") * F.col("views")))
         / F.sum(F.when(F.col("views").isNotNull(), F.col("_w")))).alias("view_ewma"),
        F.countDistinct("_day").alias("sample_days"),
    )

    # 2-pass: 위 평균을 되돌려 가중 모집단 분산 -> 표준편차.
    variance = (
        scoped.join(means.select(*GROUP_KEYS, "edit_ewma"), GROUP_KEYS)
        .groupBy(*GROUP_KEYS)
        .agg((F.sum(F.col("_w") * F.pow(F.col("edit_count") - F.col("edit_ewma"), 2))
              / F.sum("_w")).alias("_var"))
    )

    return (
        means.join(variance, GROUP_KEYS)
        .withColumn("edit_stddev", F.sqrt("_var"))
        .select(*GROUP_KEYS, "edit_ewma", "edit_stddev", "view_ewma", "sample_days")
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

    # 창의 끝. 안 주면 데이터에서 가장 최근 날짜를 쓴다(리플레이는 그 시점을 명시할 것).
    as_of = env("BASELINE_AS_OF", "")
    if not as_of:
        as_of = str(windows.select(F.max(F.to_date("window_start"))).first()[0])

    baseline = build_baseline(
        windows, as_of, halflife_days=float(env("EWMA_HALFLIFE_DAYS",
                                                str(DEFAULT_HALFLIFE_DAYS))))

    # ⚠️ page_baseline 적재는 이 경로로 하지 않는다. (wiki, title) → wiki_page.id
    # 해석과 upsert 가 필요해서 baseline_sink.py 가 맡는다. 여기 SINK 는 진단용이다.
    baseline.write.mode("overwrite").format(env("SINK", "console")).save()
    spark.stop()


if __name__ == "__main__":
    main()
