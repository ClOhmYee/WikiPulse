"""조회수만으로 1단계를 통과하는 후보를 만든다 (WP-210). **기본 꺼짐.**

왜 필요한가
    `detector.passes_first_gate(..., view_only_gate=True)` 만으로는 아무것도 안 바뀐다.
    지금 후보(`spike_candidate`)는 전부 편집 스트림이 만들고 그 행은 이미
    `edit_count >= 1` 이라, OR 의 오른쪽 가지가 발동할 일이 없기 때문이다.
    **편집이 없는 문서를 후보로 만들어 주는 것이 이 모듈이다.**

    2026-08-19 Moderna–Merck Phase 3 가 그 예다. 문서 5개가 60배까지 급등했는데 당일
    편집이 0건이라 편집 스트림에 아예 안 뜬다.

무엇을 통과시키나 (봇 필터)
    `views >= MIN_ABSOLUTE_VIEWS` **AND** `mobile_ratio >= MIN_MOBILE_RATIO`.
    🔴 두 번째가 없으면 `Roblox` 2026-08-10(하루 478만·674배)이 그대로 들어온다 —
    데스크톱 단일 채널 크롤러였다(모바일 0.1%, 평소 60%). 근거는 detector 의 상수 주석과
    `ai/spec-evidence/gate-review/RESULT.md`.

🔴 max_rev_id 가 없다
    편집이 없으니 앵커가 없고, `cluster/driver.py` 는 앵커 없는 root 를 CORE 에서 뺀다
    (`asof_links` 는 현재 판으로 폴백하지 않는다). 즉 이 경로로 들어온 이슈는 **singleton
    으로 남는다.** 해소하려면 앵커를 "`snapshot_ts` 이하 최신 revision" 으로 보강해야
    한다 — WP-210 인수조건 5번, 이 모듈 범위 밖이다.

⚠️ 전수 집계를 두 번 읽는 이유
    한 시간 파일은 enwiki ns0 만 약 236만 행이다(2026-09-21 15:00Z 실측). 전부 dict 에
    담으면 `live-cycle` 컨테이너 상한(1g)에 위험하다. 그래서:

        1패스  행 하나라도 SAFE_ROW_FLOOR 이상인 제목만 모은다 (실측 17,426개)
        2패스  그 제목만 정확히 합산한다

    🔴 **1패스 문턱은 추측이 아니라 산수다.** 한 wiki 의 project 는 `en`·`en.m` 둘뿐이라
    (`WIKI_TO_PROJECTS`), 합이 100 이상이면 **둘 중 하나는 반드시 50 이상**이다. 그래서
    50 미만인 행만 버리면 통과 대상은 하나도 안 샌다. project 수가 늘면 이 값도 같이
    내려가야 해서 상수로 박지 않고 계산한다.

    gzip 두 번 해제는 약 1초다(45MB 기준 실측) — 메모리와 바꿀 만하다.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from batch.pageview_hourly import (
    PageviewHourly,
    aggregate,
    parse_row,
    projects_for,
)

from .candidate_store import CandidateStore
from .detector import MIN_ABSOLUTE_VIEWS, MIN_MOBILE_RATIO
from .runtime import PageWindow, parse_window_start

log = logging.getLogger(__name__)


def safe_row_floor(wiki: str) -> int:
    """1패스에서 버려도 되는 행의 상한. 합 `MIN_ABSOLUTE_VIEWS` 를 project 수로 나눈 올림.

    project 가 둘(`en`·`en.m`)이면 50 이다 — 합이 100 이상인 문서는 둘 중 하나가 반드시
    50 이상이므로 통과 대상이 새지 않는다.
    """
    projects = len(projects_for(wiki))
    return -(-MIN_ABSOLUTE_VIEWS // projects)   # 올림 나눗셈


def scan_titles(lines: Iterable[str], wiki: str) -> frozenset[str]:
    """1패스 — 행 하나라도 `safe_row_floor` 이상인 canonical 제목."""
    projects = projects_for(wiki)
    floor = safe_row_floor(wiki)
    keep: set[str] = set()
    for line in lines:
        if not line.strip():
            continue
        parsed = parse_row(line, projects)
        if parsed is None:
            continue
        title, views, _is_mobile = parsed
        if views >= floor:
            keep.add(title)
    return frozenset(keep)


#: 🔴 **`Main Page` 를 뺀다.** 한 시간에 38만 조회(모바일 28.5%)라 봇 필터로는 안 걸리고
#: 매 시간 1위로 들어온다 (2026-09-21 15:00Z 실측). 편집 경로에서는 문제가 된 적이 없다 —
#: 대문은 편집 스트림의 후보로 안 올라오기 때문이다. 조회수로 문을 여는 순간 드러났다.
#: ⚠️ canonical 공백형으로 비교한다 (`Main_Page` 아님, WP-79).
EXCLUDED_TITLES = frozenset({"Main Page"})


def passes(row: PageviewHourly) -> bool:
    """봇이 아닌 조회수 급등인가. detector 의 상수를 그대로 쓴다 — 두 곳에 두면 갈린다."""
    if row.title in EXCLUDED_TITLES:
        return False
    ratio = row.mobile_ratio
    return (ratio is not None
            and row.views >= MIN_ABSOLUTE_VIEWS
            and ratio >= MIN_MOBILE_RATIO)


def select(rows: Iterable[PageviewHourly]) -> Iterator[PageviewHourly]:
    """통과한 행만. 순서는 입력 그대로다."""
    return (row for row in rows if passes(row))


@dataclass
class HarvestSummary:
    scanned_titles: int = 0     # 1패스가 남긴 제목 수
    passed: int = 0             # 두 조건을 통과한 문서 수
    bot_rejected: int = 0       # 조회수는 넘었는데 모바일 비중에서 떨어진 수
    saved: int = 0              # 실제로 후보로 저장한 수

    def format(self) -> str:
        return (f"조회수 후보: 훑음 {self.scanned_titles:,} · 통과 {self.passed:,} "
                f"(봇 제외 {self.bot_rejected:,}) · 저장 {self.saved:,}")


def harvest(
    conn, dump: Path, ts_hour: str, wiki: str, *,
    source: str = "live", dry_run: bool = False,
) -> HarvestSummary:
    """한 시간 덤프에서 조회수 후보를 만들어 `spike_candidate` 에 넣는다.

    ⚠️ **`ingest_hour` 뒤에 부른다.** 적재 원장(`page_view_hourly_ingest`, V14)에 그
    시간이 있어야 재판정이 이 후보들을 집는다 — 원장이 없으면 "원본 미도착" 으로 읽혀
    영영 대기에 남는다.

    ⚠️ 여기서 `page_view_hourly` 를 따로 쓰지 않는다. 재판정이 조회수를 그 테이블에서
    읽으므로 **`ingest_hour` 가 이 문서들의 행도 이미 적재했어야** 한다. 호출자가
    `titles` 에 통과분을 포함시키지 못하는 구조라, 지금은 이 함수가 직접 넣는다.
    """
    from batch.pageview_hourly_ingest import load_to_db, read_lines

    summary = HarvestSummary()
    titles = scan_titles(read_lines(dump), wiki)
    summary.scanned_titles = len(titles)
    if not titles:
        return summary

    rows = list(aggregate(read_lines(dump), wiki, ts_hour, titles=titles))
    hits = []
    for row in rows:
        if row.views < MIN_ABSOLUTE_VIEWS:
            continue
        if passes(row):
            hits.append(row)
        else:
            # 조회수는 넘었는데 모바일에서 떨어진 것 — 세어 두면 봇 비율이 보인다.
            summary.bot_rejected += 1
    summary.passed = len(hits)

    if dry_run or not hits:
        log.info("[조회수 후보] %s %s", ts_hour, summary.format())
        return summary

    # 재판정이 읽을 조회수 행을 먼저 넣는다 — 후보만 있고 조회수가 없으면 대기로 남는다.
    load_to_db(conn, hits)

    store = CandidateStore(conn, source=source)
    window_start = parse_window_start(ts_hour)
    for row in hits:
        page_id = store.page_id(wiki, row.title)
        store.save(page_id, PageWindow(
            wiki=wiki, title=row.title, window_start=window_start,
            # 🔴 편집이 없어서 들어온 후보다. 0 은 결측이 아니라 관측이다.
            edit_count=0, editor_count=0,
            views=row.views, mobile_views=row.mobile_views,
            # 🔴 앵커가 없다 — 모듈 독스트링의 CORE singleton 주의.
            max_rev_id=None, last_edit_ts=None,
        ))
        summary.saved += 1
    conn.commit()
    log.info("[조회수 후보] %s %s", ts_hour, summary.format())
    return summary
