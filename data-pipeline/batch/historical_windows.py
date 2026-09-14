"""문서별 Historical Window 집계 — baseline 입력 데이터셋 (WP-58).

편집 덤프 적재본(WP-56)과 조회수 적재본(WP-57)을 읽어, baseline
(spike/baseline.py build_baseline)이 읽을 **문서 × 시간 윈도우** 데이터셋을 만든다.
지금 이 형태를 만드는 코드가 없어 baseline 배치가 통째로 no-op 이다.

산출 형태 (한 행)
    (wiki, title, window_start, hour_of_week, edit_count, views)
      window_start : 1시간 정각 UTC "YYYY-MM-DDTHH:00:00"
      hour_of_week : 0..167 (월 00시 UTC = 0). baseline 이 이 슬롯으로 평소를 잡는다
      edit_count   : 그 문서·그 시간의 봇 제외 편집 수
      views        : 그 문서·그 시간의 조회수 합(agent 가로질러). 조회 없으면 0

🔴 집계 계약은 스트리밍(streaming/edit_windows.py)과 한 벌이어야 한다 (§AC)
    - **윈도우 길이 = 1시간.** 스트리밍 WINDOW_SIZE 와 일치시킨다. 다르면 edit_z 가
      통째로 어긋나는데 에러 없이 숫자만 틀린다. baseline 은 168 슬롯(hour_of_week)이라
      1시간이 자연스러운 정합값이다.
    - **봇 필터 = is_bot 참인 편집 제외.** 스트리밍의 `~coalesce(is_bot, False)` 와 같다.
    - **문서 키 = (wiki, title).** -56·-57 과 같다. dump page_id 는 쓰지 않는다 —
      wiki_page.id 해석은 적재(WP-60) 책임.

왜 순수 파이썬인가 (Spark 아님)
    HDFS 2노드(WP-28)·Spark 2노드(WP-27)가 아직 없다. 형제 적재
    (-56·-57)와 같이 순수 파이썬으로 두어 인프라 없이 파싱·집계·테스트가 돌게 한다.
    parquet 출력과 "배치==스트리밍" 대조는 인프라가 서면 잇는다(아래 CLI·README).
    hour_of_week 정의는 spike/baseline.py 의 Spark 판과 반드시 같아야 한다(월=0, UTC).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime

#: 집계 윈도우(시간). 스트리밍 WINDOW_SIZE 와 맞춘다. baseline 168 슬롯의 입도.
WINDOW_HOURS = 1


@dataclass(frozen=True)
class WindowRow:
    """문서 × 1시간 윈도우. baseline build_baseline 의 입력 한 행."""
    wiki: str
    title: str
    window_start: str    # "YYYY-MM-DDTHH:00:00" (UTC)
    hour_of_week: int     # 0..167 (월 00시 = 0)
    edit_count: int
    views: int


def _parse_iso(ts: str) -> datetime:
    """ISO 타임스탬프를 datetime 으로. 'Z'·마이크로초·초 정밀도 모두 받는다."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00").replace(" ", "T"))


def floor_to_hour(ts: str) -> str:
    """타임스탬프를 그 시각의 정각으로 내린다 → "YYYY-MM-DDTHH:00:00"."""
    dt = _parse_iso(ts)
    return f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}T{dt.hour:02d}:00:00"


def hour_of_week(hour_ts: str) -> int:
    """정각 타임스탬프 → 0..167 (월요일 00시 UTC = 0).

    🔴 spike/baseline.py 의 Spark 판과 같은 정의여야 한다. Python weekday(): 월=0..일=6.
    """
    dt = _parse_iso(hour_ts)
    return dt.weekday() * 24 + dt.hour


def is_bot_edit(rec: dict) -> bool:
    """봇 편집이면 True. 스트리밍의 ~coalesce(is_bot, False) 와 같은 판정."""
    return bool(rec.get("is_bot"))


def aggregate_edits(
    edit_events: Iterable[dict], *, keep_bots: bool = False
) -> dict[tuple[str, str, str], int]:
    """edit_event 레코드를 (wiki, title, hour) → 편집 수 로 집계한다.

    봇은 기본 제외(keep_bots=True 면 유지 — 진단용). 시간은 event_ts 를 정각으로 내린다.
    """
    counts: dict[tuple[str, str, str], int] = {}
    for rec in edit_events:
        if not keep_bots and is_bot_edit(rec):
            continue
        key = (rec["wiki"], rec["title"], floor_to_hour(rec["event_ts"]))
        counts[key] = counts.get(key, 0) + 1
    return counts


def sum_views(
    pageviews: Iterable[dict], *, agents: set[str] | None = None
) -> dict[tuple[str, str, str], int]:
    """pageview 레코드를 (wiki, title, ts_hour) → 조회수 합 으로 집계한다.

    agents 를 주면 그 agent 만 합산한다(None 이면 전부). 적재는 agent 를 분리 저장하므로
    (WP-57) 어떤 조합을 baseline 에 쓸지는 여기·-60 에서 정한다.
    """
    totals: dict[tuple[str, str, str], int] = {}
    for rec in pageviews:
        if agents is not None and rec["agent"] not in agents:
            continue
        key = (rec["wiki"], rec["title"], rec["ts_hour"])
        totals[key] = totals.get(key, 0) + int(rec["views"])
    return totals


def join_windows(
    edit_counts: dict[tuple[str, str, str], int],
    view_totals: dict[tuple[str, str, str], int],
) -> Iterator[WindowRow]:
    """편집·조회 집계를 (wiki, title, hour) 기준 full outer join 한다.

    baseline 은 edit_z(편집)와 view_ewma(조회수)를 둘 다 잡으므로, 한쪽만 있는 윈도우도
    남긴다(없는 쪽은 0). 편집만 있는 시간·조회만 있는 시간이 모두 baseline 슬롯에 든다.
    """
    for key in edit_counts.keys() | view_totals.keys():
        wiki, title, window_start = key
        yield WindowRow(
            wiki=wiki,
            title=title,
            window_start=window_start,
            hour_of_week=hour_of_week(window_start),
            edit_count=edit_counts.get(key, 0),
            views=view_totals.get(key, 0),
        )


def build_windows(
    edit_events: Iterable[dict],
    pageviews: Iterable[dict],
    *,
    agents: set[str] | None = None,
    keep_bots: bool = False,
) -> list[WindowRow]:
    """edit_event·pageview 레코드에서 baseline 입력 행을 만든다. window_start 오름차순."""
    edits = aggregate_edits(edit_events, keep_bots=keep_bots)
    views = sum_views(pageviews, agents=agents)
    rows = list(join_windows(edits, views))
    rows.sort(key=lambda r: (r.wiki, r.title, r.window_start))
    return rows
