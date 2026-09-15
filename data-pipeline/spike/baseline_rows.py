"""28일 기준선 행 산출 — 순수 로직 (WP-60).

Historical Window 산출물(WP-58)을 읽어 `page_baseline` 한 행에 해당하는
값을 만든다. 가중 방식·반감기는 ewma.py(WP-59)가 정한 것을 그대로 쓴다 —
🔴 여기서 가중치를 새로 정하지 않는다.

산출 형태 (page_baseline 컬럼과 1:1)
    (wiki, title, slot_index, edit_ewma, edit_stddev, view_ewma, view_stddev, sample_days)
    page_id 는 여기 없다 — (wiki, title) → wiki_page.id 해석은 적재 시점
    (baseline_sink.py) 책임이다. 덤프 page_id 를 쓰지 않는 -56·-57·-58 과 같은 키다.

28일 경계
    ⚠️ 골격에는 기간 필터가 없어 소스 전체를 집계했다. 여기서 `as_of` 기준
    **[as_of-28일, as_of]** 안의 관측만 쓴다. 경계를 안 걸면 기준선이 계절 전체로
    번져 "평소"가 아니게 된다.

sample_days
    그 슬롯에 실제로 관측이 있었던 **고유 날짜 수** (슬롯이 6시간이라 하루에 여러 윈도우가 같은 슬롯에 들어간다 — 그래도 하루로 센다). detector 의 is_thin(<7)이
    이 값으로 얇은 baseline 을 신규 문서 경로로 보낸다. 관측 자체가 없는 날은 세지
    않는다 — 0 편집을 채워 넣으면 표본이 두꺼워 보여 오탐이 난다.

왜 순수 파이썬인가
    Spark 판(baseline.py)은 같은 수식을 컬럼 연산으로 돌린다. 로컬에서 PySpark
    워커가 못 뜨는 환경(3.12+)에서도 계산 규칙을 테스트로 고정해 두려고 분리했다.
    두 판이 갈리면 기준선이 조용히 달라지므로 수식은 ewma.py 한 곳에서만 온다.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from .ewma import DEFAULT_HALFLIFE_DAYS, Observation, ewma_mean_std

#: 기준선 창 길이(일). 명세 §3.2 2번 "28일 기준선".
BASELINE_WINDOW_DAYS = 28


@dataclass(frozen=True)
class BaselineRow:
    """page_baseline 한 행. page_id 는 적재 시점에 붙는다."""
    wiki: str
    title: str
    #: 0..3 (UTC 시 // batch.historical_windows.SLOT_HOURS). 🔴 폭은 거기서만 온다.
    slot_index: int
    edit_ewma: float
    edit_stddev: float | None
    view_ewma: float | None
    #: 조회수 가중 표준편차. 관측이 하나뿐이면 0, 조회수가 아예 없으면 None.
    #: 🔴 조회수 z 를 내는 유일한 입력이다 — 없으면 detector 가 조회수 단독 발동을 못 한다
    #: (WP-90). 여태 view_ewma 만 내서 VIEW_Z_THRESHOLD 가 죽어 있었다.
    view_stddev: float | None
    sample_days: int


def _day(window_start: str) -> date:
    """window_start "YYYY-MM-DDTHH:00:00" 에서 날짜만."""
    return date.fromisoformat(window_start[:10])


def latest_day(rows: Iterable[dict]) -> date | None:
    """관측 중 가장 최근 날짜. as_of 를 안 주면 이 값을 창의 끝으로 쓴다."""
    days = [_day(row["window_start"]) for row in rows]
    return max(days) if days else None


def build_rows(
    windows: Iterable[dict],
    *,
    as_of: date | None = None,
    halflife_days: float = DEFAULT_HALFLIFE_DAYS,
    window_days: int = BASELINE_WINDOW_DAYS,
) -> list[BaselineRow]:
    """Historical Window 행들에서 기준선 행을 만든다.

    windows: -58 산출물 레코드 (wiki, title, window_start, slot_index, edit_count, views)
    as_of  : 창의 끝(포함). None 이면 관측 중 가장 최근 날짜.

    [as_of-window_days, as_of] 밖의 관측은 버린다. 창 안에 관측이 하나도 없는
    슬롯은 행을 내지 않는다 — 기준선 없음과 기준선 0 은 다른 뜻이다(detector 가
    baseline None 을 신규 문서로 본다).
    """
    rows = list(windows)
    if as_of is None:
        as_of = latest_day(rows)
    if as_of is None:
        return []

    oldest = as_of.toordinal() - window_days

    # (wiki, title, slot_index) -> [(관측일, 편집수, 조회수)]
    slots: dict[tuple[str, str, int], list[tuple[date, float, float | None]]] = defaultdict(list)
    for row in rows:
        day = _day(row["window_start"])
        if not (oldest < day.toordinal() <= as_of.toordinal()):
            continue          # 28일 창 밖
        views = row.get("views")
        slots[(row["wiki"], row["title"], int(row["slot_index"]))].append(
            (day, float(row["edit_count"]), None if views is None else float(views))
        )

    out: list[BaselineRow] = []
    for (wiki, title, slot), observed in sorted(slots.items()):
        edits = [Observation((as_of - day).days, count) for day, count, _ in observed]
        edit_ewma, edit_stddev = ewma_mean_std(edits, halflife_days)

        # 조회수는 결측일 수 있다(조회 적재가 그 구간에 없을 때). 있는 것만 가중한다.
        seen_views = [
            Observation((as_of - day).days, views)
            for day, _, views in observed if views is not None
        ]
        view_ewma, view_stddev = (
            ewma_mean_std(seen_views, halflife_days) if seen_views else (None, None))

        out.append(BaselineRow(
            wiki=wiki,
            title=title,
            slot_index=slot,
            edit_ewma=edit_ewma,
            edit_stddev=edit_stddev,
            view_ewma=view_ewma,
            view_stddev=view_stddev,
            # 관측이 있었던 고유 날짜 수. 같은 날 여러 행이면 하루로 센다.
            sample_days=len({day for day, _, _ in observed}),
        ))
    return out
