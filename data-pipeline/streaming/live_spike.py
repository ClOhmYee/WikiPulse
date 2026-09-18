"""Spark 마이크로배치 윈도우 -> SpikeRuntime -> `spike(source='live')` (WP-100).

    from streaming.live_spike import make_spike_batch_writer
    query = aggregated.writeStream.foreachBatch(make_spike_batch_writer(dsn)).start()

여태 `streaming/edit_windows.py` 는 집계까지만 하고 콘솔로 찍었다. `SpikeRuntime`
(WP-94)은 리플레이 CLI 만 불렀다. 이 모듈이 그 사이를 잇는다 — LIVE 윈도우가
`page_baseline` 을 읽고 `detect()` 를 거쳐 실제 `spike` 행이 된다.

🔴 **타임스탬프는 epoch 초로 건넨다. Spark 의 datetime 을 그대로 쓰지 않는다.**
    PySpark 는 `TimestampType` 을 파이썬으로 내보낼 때 `datetime.fromtimestamp()` 를
    쓴다 — **드라이버 로컬 시간대의 naive datetime** 이 나온다.
    `spark.sql.session.timeZone=UTC` 를 걸어도 이 변환에는 반영되지 않는다.
    KST 장비에서 실측했다 (2026-09-15):

        UTC 2024-10-06T19:00:00  ->  datetime.datetime(2024, 10, 7, 4, 0)   tzinfo=None
        같은 값의 unix_timestamp ->  1728241200  ->  2024-10-06T19:00:00+00:00

    9시간 밀린 값에 tzinfo 만 없다. `require_utc` 가 naive 를 막아 주니 지금은
    **터지는** 쪽이지만, 거기서 `.replace(tzinfo=utc)` 로 "고치면" 그 순간부터
    9시간 어긋난 `window_start` 가 조용히 쌓인다 (`spike/spike_sink.py` 🔴 와 같은 함정).
    그래서 경계에서 아예 epoch 초(시간대 개념이 없는 순간값)로 바꿔 건넨다.
    `F.unix_timestamp` 는 세션 시간대 설정에도 의존하지 않는다 — `date_format` 은 의존한다.

⚠️ **조회수(views)는 LIVE 편집 스트림에 없다. 0 으로 꾸미지 않는다.**
    `wiki.edits` 는 recentchange 이벤트라 조회수 필드가 아예 없다. `PageWindow.views`
    계약상 `None` 이 "미수집" 이고, `detect()` 는 그때 편집만으로 1차 판정한다
    (`spike/detector.py` 112행). 0 을 넣으면 "진짜 조회수 0회" 와 구분되지 않는다.
    Pageviews API 연결은 별도 경로다(WP-127·-128).

    🔴 **그래서 지금 LIVE 는 확정을 하나도 못 낸다** (2026-09-18, WP-126).
        2단계 관문이 조회수를 최종 관문으로 두면서, 조회수 없는 윈도우는 확정도 폐기도
        아닌 **후보 대기**가 됐다. `spike` 는 확정만 담으므로 LIVE 적재가 0 이다.
        버그가 아니라 계약이고, `other/pageviews` 를 붙이는 -128 까지의 상태다.
        `to_runtime_frame` 은 `views` 컬럼이 붙은 프레임을 그때 그대로 받는다.

⚠️ **슬라이딩 윈도우라 한 문서가 한 시간에 여러 행을 낸다.**
    `DEFAULT_SLIDE_SIZE` 가 5분이라 1시간 윈도우가 5분마다 하나씩 겹쳐 나온다.
    급증한 문서는 `window_start` 가 다른 spike 행을 최대 12개까지 만든다 — 키가
    `(source, page_id, window_start)` 라 중복이 아니라 **서로 다른 행**이다.
    집계 계약(슬라이드 폭)은 `edit_windows.aggregate_edit_windows` 의 것이고 배치
    경로와 한 벌이라 여기서 바꾸지 않는다. 정각 tumbling 만 원하면 실행 시
    `SLIDE_SIZE` 를 `WINDOW_SIZE` 와 같게 준다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from spike.runtime import PageWindow, RuntimeSummary, SpikeRuntime

if TYPE_CHECKING:                       # 타입 힌트 전용 — 런타임에 import 하지 않는다
    from pyspark.sql import DataFrame

# 🔴 **pyspark 를 모듈 최상단에서 import 하지 않는다.**
#     이 파일의 순수 로직(`page_window_from_row`·출처 계약)은 Spark 없이 돌고, 그걸
#     검사하는 `tests/test_live_spike.py` 도 그래야 한다. 최상단에서 import 하면
#     pyspark 가 없는 환경(팀 기본 venv)에서 **그 디렉터리 수집이 통째로 깨진다** —
#     2026-09-15 에 실제로 그렇게 만들었다가 `tests` 21 passed 가 수집 오류로 바뀌었다.
#     psycopg 를 DB 경로에서만 import 하는 것과 같은 규칙이다.

log = logging.getLogger("live_spike")

#: 이 경로가 내는 유일한 라벨. 리플레이 CLI 는 "replay" 를 쓴다.
LIVE_SOURCE = "live"


def to_runtime_frame(windows: DataFrame) -> DataFrame:
    """집계 결과를 드라이버로 내리기 좋은 형태로. 타임스탬프를 epoch 초로 바꾼다.

    🔴 `aggregate_edit_windows` 의 출력을 **고치지 않는다.** 그 함수는 배치 경로와
    대조되는 계약이라(`tests/test_stream_batch_parity.py`) 건드리면 대조가 깨진다.
    변환은 싱크 쪽인 여기서만 한다.

    판정에 안 쓰는 컬럼(`byte_delta_sum`·`last_edit_ts`)은 여기서 떨군다 —
    드라이버로 내리는 양을 줄인다.
    """
    from pyspark.sql import functions as F     # Spark 를 실제로 쓰는 지점에서만

    columns = [
        F.col("wiki"),
        F.col("title"),
        F.unix_timestamp(F.col("window_start")).alias("window_start_epoch"),
        F.unix_timestamp(F.col("window_end")).alias("window_end_epoch"),
        F.col("edit_count"),
        F.col("editor_count"),
    ]
    # 조회수는 **있으면** 싣는다. 편집 스트림에는 없다(모듈 독스트링 ⚠️) — 이 분기는
    # 조회수를 붙인 프레임을 흘릴 때를 위한 이음매다(WP-128).
    # 없는 걸 0 으로 꾸미지 않으려고 컬럼 자체를 안 만든다.
    if "views" in windows.columns:
        columns.append(F.col("views"))
    return windows.select(*columns)


def _utc(epoch_seconds: int) -> datetime:
    return datetime.fromtimestamp(int(epoch_seconds), tz=timezone.utc)


def page_window_from_row(row) -> PageWindow:
    """`to_runtime_frame` 한 행 -> `PageWindow`.

    - `window_end` 는 **실제 값**을 쓴다. `window_start + 1h` 로 다시 계산하지 않는다 —
      윈도우 길이는 `WINDOW_SIZE` 환경변수라 `WINDOW_HOURS` 상수와 갈릴 수 있고,
      갈리면 `detected_at` 이 에러 없이 어긋난다 (`spike/runtime.py` PageWindow 🔴).
    - 제목 canonical 변환은 `PageWindow.__post_init__` 이 한다(멱등). 여기서 또 하지 않는다.
    - `views` 는 프레임에 있을 때만 싣는다. 편집 스트림에는 없어서 보통 `None` =
      미수집이다 (모듈 독스트링 ⚠️). 🔴 **없는 걸 0 으로 바꾸지 않는다** — 0 은
      "진짜 0회 조회" 로 읽혀 폐기(REJECTED)가 되고, 폐기는 다시 판정하지 않는다.
    """
    # Row 는 tuple 이라 `in` 이 값을 본다 — 키는 `__fields__` 로 확인한다.
    # 이 함수는 dict 로도 불린다(`tests/test_live_spike.py`)라 둘 다 받는다.
    fields = getattr(row, "__fields__", None) or row
    views = row["views"] if "views" in fields else None
    return PageWindow(
        wiki=row["wiki"],
        title=row["title"],
        window_start=_utc(row["window_start_epoch"]),
        window_end=_utc(row["window_end_epoch"]),
        edit_count=int(row["edit_count"]),
        editor_count=int(row["editor_count"] or 0),
        views=None if views is None else int(views),
    )


def process_batch(conn, batch_df: DataFrame, batch_id: int) -> RuntimeSummary:
    """마이크로배치 하나를 판정해 `spike(source='live')` 로 적재한다.

    🔴 **`toLocalIterator()` 를 쓴다 — `collect()` 가 아니다.**
        `collect()` 는 배치 전체를 드라이버 힙에 한 번에 올린다. 재시작 직후처럼 밀린
        구간을 따라잡을 때 이게 OOM 의 자리다. `toLocalIterator` 는 파티션 하나씩
        가져와 메모리가 파티션 크기로 묶인다. 인위적인 행 수 상한은 두지 않았다 —
        상한으로 자르면 급증이 **조용히 유실**된다. 입력량은 이미 상류에서
        `maxOffsetsPerTrigger` 로 묶여 있다.

    🔴 **`foreachPartition` 이 아니라 드라이버에서 돈다.**
        1. 배포된 Spark 이미지(`apache/spark:3.5.3-python3`)에 psycopg 가 없고,
           compose 의 spark 서비스는 `streaming/` 만 마운트한다. executor 에서 DB 를
           쓰려면 2노드 워커 전부에 드라이버와 코드를 깔아야 하는데 그건 -27 영역이다.
        2. `SpikeRuntime` 은 커넥션 하나와 기준선 캐시를 들고 있다. executor 로
           흩으면 파티션마다 커넥션과 캐시가 따로 생겨 왕복이 오히려 는다.
        3. 판정까지 오는 양이 작다 — enwiki 초당 2건이고, 그중 급증은 더 적다.
        executor 분산이 필요해질 만큼 커지면 그때 다시 잰다.

    ⚠️ **커넥션은 배치당 하나다. 행마다 만들지 않는다.**
        커넥션은 호출자(`make_spike_batch_writer`)가 배치 경계에서 연다. 한 배치가
        한 트랜잭션이라, 재처리되면 통째로 다시 커밋된다 — 멱등 단위와 일치한다.

    기준선 캐시는 `iter_process` 가 배치 시작에서 비운다(`spike/runtime.py` 🔴).
    여기서 `SpikeRuntime` 을 배치마다 새로 만드는 것도 같은 효과지만, 캐시 수명 규칙을
    두 곳에 두지 않으려고 런타임 쪽 규칙에 맡긴다.
    """
    from spike.baseline_repository import BaselineRepository
    from spike.spike_sink import SpikeSink

    runtime = SpikeRuntime(BaselineRepository(conn), SpikeSink(conn, source=LIVE_SOURCE))
    rows = to_runtime_frame(batch_df).toLocalIterator()
    summary = RuntimeSummary.of(
        runtime.iter_process(page_window_from_row(row) for row in rows)
    )
    conn.commit()
    log.info("batch %s | %s", batch_id, summary.format())
    return summary


def make_spike_batch_writer(dsn: str):
    """`writeStream.foreachBatch(...)` 에 넣을 함수를 만든다.

    커넥션을 배치마다 열고 닫는다. 장수명 커넥션 하나를 재사용하면 왕복은 줄지만,
    몇 시간 놀던 커넥션이 방화벽·서버 타임아웃에 끊긴 걸 다음 배치에서야 알게 된다.
    30초 트리거면 분당 2회라 접속 비용이 문제 되는 구간이 아니다.
    """
    import psycopg     # LIVE DB 싱크에서만 필요 — 콘솔 싱크는 드라이버 없이도 돈다

    def write_batch(batch_df: DataFrame, batch_id: int) -> None:
        with psycopg.connect(dsn) as conn:
            process_batch(conn, batch_df, batch_id)

    return write_batch
