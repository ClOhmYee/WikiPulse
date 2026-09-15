"""문서별 Historical Window 집계 — baseline 입력 데이터셋 (WP-58).

편집 덤프 적재본(WP-56)과 조회수 적재본(WP-57)을 읽어, baseline
(spike/baseline.py build_baseline)이 읽을 **문서 × 시간 윈도우** 데이터셋을 만든다.
지금 이 형태를 만드는 코드가 없어 baseline 배치가 통째로 no-op 이다.

산출 형태 (한 행)
    (wiki, title, window_start, slot_index, edit_count, editor_count, views)
      window_start : 1시간 정각 UTC "YYYY-MM-DDTHH:00:00"
      slot_index   : 0..3 (UTC 시 // 6). baseline 이 이 슬롯으로 평소를 잡는다
      edit_count   : 그 문서·그 시간의 봇 제외 편집 수
      editor_count : 그 윈도우의 서로 다른 편집자 수. 급증 판정의 편집자 하한
                     (detector.MIN_DISTINCT_EDITORS, WP-85)이 이 값을 본다.
                     🔴 스트리밍은 approx_count_distinct(근사), 여기는 정확값이라
                     **두 값이 갈린다.** ~~편집자 1~10명 구간에서 일치함을 실측(불일치 0건)~~
                     → 표본을 200,000 events 로 키우니 **21건 불일치**(전부 과소 계수,
                     2→1 이 13건)였고 그 13건이 편집자 하한을 뒤집었다
                     (2026-09-15, WP-83). 작은 표본에서는 HLL 희소 표현이
                     정확해 안 드러난다. → rsd=0.01 로 확정해 불일치 0건이 됐다
                     (2026-09-15, WP-89). streaming.EDITOR_COUNT_RSD 주석 참고.
      views        : 그 문서·그 시간의 조회수 합(agent 가로질러). 조회 없으면 0

🔴 집계 계약은 스트리밍(streaming/edit_windows.py)과 한 벌이어야 한다 (§AC)
    - **윈도우 길이 = 1시간.** 스트리밍 WINDOW_SIZE 와 일치시킨다. 다르면 edit_z 가
      통째로 어긋나는데 에러 없이 숫자만 틀린다. baseline 은 4 슬롯(slot_index)이라
      1시간이 자연스러운 정합값이다(슬롯 폭 6시간과 별개다).
    - **봇 필터 = is_bot 참인 편집 제외.** 스트리밍의 `~coalesce(is_bot, False)` 와 같다.
    - **문서 키 = (wiki, title), title 은 canonical 공백형.** -56·-57 과 같다.
      dump page_id 는 쓰지 않는다 — wiki_page.id 해석은 적재(WP-60) 책임.

🔴 제목은 **읽는 지점에서** canonical 로 맞춘다 (WP-92)
    ~~샤드 title 을 그대로 키로 썼다~~ → 샤드 세대가 둘이라 그러면 안 된다.
    WP-79 부터 normalize_dump·pageview 가 공백형을 내지만, 그 전에 만든 -56
    편집 샤드는 밑줄형이다. 세대가 섞이면 join_windows 의 (wiki, title, hour) 가
    **한 건도 안 맞아** 같은 문서·같은 시각이 views=0 행과 edit_count=0 행 둘로 쪼개진다.
    view_ewma 가 전부 비고, 조회수 단독 발동(WP-90)이 통째로 죽는다 —
    **에러는 안 나고 행 수만 는다.**
    canonical_title 은 멱등이라 신세대 샤드에는 아무 영향이 없다.
    db/README.md 가 정한 규칙 그대로다: 집계가 끝난 뒤가 아니라 읽는 지점에서 맞춘다.

왜 순수 파이썬인가 (Spark 아님)
    HDFS 2노드(WP-28)·Spark 2노드(WP-27)가 아직 없다. 형제 적재
    (-56·-57)와 같이 순수 파이썬으로 두어 인프라 없이 파싱·집계·테스트가 돌게 한다.
    parquet 출력과 "배치==스트리밍" 대조는 인프라가 서면 잇는다(아래 CLI·README).
    slot_index 정의는 spike/baseline.py 의 Spark 판과 반드시 같아야 한다(UTC 시 // SLOT_HOURS).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime

from producer.normalize import canonical_title

#: 집계 윈도우(시간). 스트리밍 WINDOW_SIZE 와 맞춘다.
#: ⚠️ 슬롯 폭(SLOT_HOURS)과 다른 값이다 — 윈도우는 "얼마나 자주 집계하나", 슬롯은
#: "기준선을 어떤 단위로 묶나". -84 도 윈도우는 1시간 그대로 두고 슬롯만 바꿨다.
WINDOW_HOURS = 1

#: 기준선 슬롯 폭(시간). 하루가 24/SLOT_HOURS 개 슬롯으로 나뉜다.
#: ~~요일×시간 168~~ → 시간 24 (WP-84) → **6시간 4슬롯** (2026-09-15, WP-88).
#:
#: 왜 또 넓혔나 — 24 슬롯도 여전히 얇았다. 실덤프 전수 측정(2025-06·2024-10):
#:     슬롯당 sample_days>=7 도달률   1h 1.5% / 3h 5.4% / 6h 13.0% / 일 58.1%
#:     문서 중 1개라도 통과           1h 4.8% / 3h 13.7% / 6h 25.2% / 일 58.1%
#: 월 편집 수 구간별로는 20~49편집 0.8% · 100~299편집 39.9% · 300~999편집 83.3% —
#: 즉 24 슬롯의 z 경로는 **월 300편집 이상 문서 전용**이었다. 두 달 값이 1pp 이내로 일치.
#:
#: 왜 일 단위(1슬롯)까지 안 갔나 — 하루를 통으로 묶으면 시간대 패턴을 전부 버린다.
#: 6시간이면 새벽·오전·오후·저녁 네 구간이 남아 일주기 모양을 유지한다.
#:
#: 무엇을 잃나 (같은 관측에 1h·6h 기준선을 각각 물려 실측, 2025-06 월 100편집 이상 965문서)
#:     판정 대상 2,134 윈도우 중 z 경로 가능: 1h 482 (23%) -> 6h 1,726 (81%)
#:     둘 다 z 가능한 479 윈도우에서 임계 판정 **일치 469 (97.9%)**
#:     불일치 10건 — 1h만 급증 7 · 6h만 급증 3
#:     z 차이(6h-1h) 중앙값 +0.07 · 평균 -0.10 · 범위 -11.53 ~ +1.69
#: 얻는 쪽(1,244 윈도우가 z 경로로 진입)이 잃는 쪽(겹치는 구간에서 2.1% 불일치)보다 크다.
SLOT_HOURS = 6


@dataclass(frozen=True)
class WindowRow:
    """문서 × 1시간 윈도우. baseline build_baseline 의 입력 한 행."""
    wiki: str
    title: str
    window_start: str    # "YYYY-MM-DDTHH:00:00" (UTC)
    slot_index: int       # 0..3 (UTC 시 // SLOT_HOURS)
    edit_count: int
    editor_count: int
    views: int


def _parse_iso(ts: str) -> datetime:
    """ISO 타임스탬프를 datetime 으로. 'Z'·마이크로초·초 정밀도 모두 받는다."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00").replace(" ", "T"))


def floor_to_hour(ts: str) -> str:
    """타임스탬프를 그 시각의 정각으로 내린다 → "YYYY-MM-DDTHH:00:00"."""
    dt = _parse_iso(ts)
    return f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}T{dt.hour:02d}:00:00"


def slot_index(hour_ts: str) -> int:
    """정각 타임스탬프 → 0..3 (UTC 시 // SLOT_HOURS).

    🔴 spike/baseline.py 의 Spark 판과 같은 정의여야 한다.

    ~~요일×시간(0..167)~~ → 시간(0..23) (WP-84) → **6시간 4슬롯**
    (2026-09-15, WP-88). 넓힌 근거·비용은 SLOT_HOURS 주석에 있다.
    """
    return _parse_iso(hour_ts).hour // SLOT_HOURS


def is_bot_edit(rec: dict) -> bool:
    """봇 편집이면 True. 스트리밍의 ~coalesce(is_bot, False) 와 같은 판정."""
    return bool(rec.get("is_bot"))


def aggregate_edits(
    edit_events: Iterable[dict], *, keep_bots: bool = False
) -> dict[tuple[str, str, str], tuple[int, int]]:
    """edit_event 레코드를 (wiki, title, hour) → (편집 수, 편집자 수) 로 집계한다.

    봇은 기본 제외(keep_bots=True 면 유지 — 진단용). 시간은 event_ts 를 정각으로 내린다.
    편집자 수를 함께 세는 이유는 한 사람의 연속 편집을 급증에서 빼기 위해서다
    (WP-85) — 스트리밍이 이미 같은 값을 집계하므로 배치도 낸다.
    """
    counts: dict[tuple[str, str, str], int] = {}
    editors: dict[tuple[str, str, str], set[str]] = {}
    for rec in edit_events:
        if not keep_bots and is_bot_edit(rec):
            continue
        key = (rec["wiki"], canonical_title(rec["title"]),
               floor_to_hour(rec["event_ts"]))
        counts[key] = counts.get(key, 0) + 1
        user = rec.get("user")
        if user:
            editors.setdefault(key, set()).add(user)
    return {k: (n, len(editors.get(k, ()))) for k, n in counts.items()}


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
        key = (rec["wiki"], canonical_title(rec["title"]), rec["ts_hour"])
        totals[key] = totals.get(key, 0) + int(rec["views"])
    return totals


def join_windows(
    edit_counts: dict[tuple[str, str, str], tuple[int, int]],
    view_totals: dict[tuple[str, str, str], int],
) -> Iterator[WindowRow]:
    """편집·조회 집계를 (wiki, title, hour) 기준 full outer join 한다.

    baseline 은 edit_z(편집)와 view_ewma(조회수)를 둘 다 잡으므로, 한쪽만 있는 윈도우도
    남긴다(없는 쪽은 0). 편집만 있는 시간·조회만 있는 시간이 모두 baseline 슬롯에 든다.
    """
    for key in edit_counts.keys() | view_totals.keys():
        wiki, title, window_start = key
        edits, editors = edit_counts.get(key, (0, 0))
        yield WindowRow(
            wiki=wiki,
            title=title,
            window_start=window_start,
            slot_index=slot_index(window_start),
            edit_count=edits,
            editor_count=editors,
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
