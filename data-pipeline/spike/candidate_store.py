"""후보 대기 보관소 — `spike_candidate` 읽기·쓰기 (WP-128).

2단계 계약(WP-126)의 판정은 셋이다: 확정 / 폐기 / **후보 대기**. 확정은 `spike`,
폐기는 버림, 대기가 여기다. 조회수는 항상 나중에 오므로(시간별 덤프가 윈도우 끝 기준 약
1시간 뒤, 2026-09-18 실측) 대기를 들고 있지 않으면 LIVE 는 영영 확정을 못 낸다.

🔴 **여기 남아 있는 행은 "아직 판정 중" 뿐이다.** 확정되면 `spike` 로 옮기고 지우고,
폐기되면 그냥 지운다. 안 지우면 후보가 무한히 쌓이고, 쌓인 것을 매번 다시 판정한다.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta

from .runtime import PageWindow
from .spike_sink import require_source, require_utc

#: 대기가 이 시간을 넘으면 버린다. 시간별 덤프가 약 2시간 뒤에 나오므로, 하루가 넘도록
#: 조회수가 없었다면 그 시간 파일은 이미 나왔고 이 문서가 그 안에 없었던 것이다
#: (삭제·이동된 문서, 또는 후보 필터 밖). ⚠️ 이 값을 늘리면 만료가 아니라 적체가 된다.
DEFAULT_EXPIRE_HOURS = 36

UPSERT_CANDIDATE_SQL = """
INSERT INTO spike_candidate
    (source, page_id, window_start, window_end, edit_count, editor_count,
     max_rev_id, last_edit_ts)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (source, page_id, window_start) DO UPDATE SET
    window_end   = EXCLUDED.window_end,
    edit_count   = EXCLUDED.edit_count,
    editor_count = EXCLUDED.editor_count,
    max_rev_id   = EXCLUDED.max_rev_id,
    last_edit_ts = EXCLUDED.last_edit_ts
"""

DELETE_CANDIDATE_SQL = """
DELETE FROM spike_candidate
 WHERE source = %s AND page_id = %s AND window_start = %s
"""

#: 조회수가 **이미 들어온** 대기만 가져온다. 아직 없는 것은 다음 실행에서 본다.
#: `page_view_hourly` 는 (page_id, ts_hour) 가 키라 윈도우 시작 정각과 1:1 로 붙는다.
#: 🔴 정각 윈도우만 붙는다 — 아래 `due()` 독스트링 참고.
#:
#: 🔴 **`JOIN page_view_hourly` 하나로는 안 된다** (WP-199). 위키미디어 덤프는
#:    조회수 0 인 문서를 **아예 싣지 않는다.** 그래서 행이 없는 것이 두 가지를 뜻한다:
#:      (1) 그 시간 원본이 아직 안 왔다     → 대기 유지가 맞다
#:      (2) 원본은 왔는데 그 문서가 0회였다 → 폐기가 맞다
#:    옛 SQL 은 (1)로만 해석해 0회 문서가 영영 대기로 남았고, 재판정이 가장 오래된
#:    시간부터 도는 구조라 **큐가 맨 앞에서 막혔다.** 2026-09-22 에 0회 문서 500건이
#:    뒤의 53,982건을 굶겼다.
#:
#:    그래서 적재 원장(`page_view_hourly_ingest`, V14)을 같이 본다. 그 시간이 원장에
#:    있으면 도착한 것이고, 행이 없으면 **조회수 0** 으로 판정한다.
#:
#: ⚠️ `COALESCE(v.views, 0)` 의 0 은 추측이 아니라 **관측**이다 — 덤프에 없다는 것이
#:    0회라는 뜻이다. 원장에 없는 시간은 애초에 이 질의에 안 걸리므로 0 이 지어내는
#:    값이 되는 경우는 없다.
SELECT_DUE_SQL = """
SELECT c.source, c.page_id, p.wiki, p.title,
       c.window_start, c.window_end, c.edit_count, c.editor_count,
       c.max_rev_id, c.last_edit_ts, COALESCE(v.views, 0) AS views,
       v.mobile_views AS mobile_views
  FROM spike_candidate c
  JOIN wiki_page p ON p.id = c.page_id
  JOIN page_view_hourly_ingest g
       ON g.wiki = p.wiki AND g.ts_hour = c.window_start
  LEFT JOIN page_view_hourly v
       ON v.page_id = c.page_id AND v.ts_hour = c.window_start
 WHERE c.source = %s
 ORDER BY c.window_start
 LIMIT %s
"""

#: 🔴 **만료 기준은 벽시계 단독이 아니다** (WP-202). 위 상수 주석의 전제
#:    ("하루가 넘도록 조회수가 없었다면 그 시간 파일은 이미 나왔다")는 **상류가 돌고
#:    있을 때만 참이다.** 멈추면 파일이 안 나온 것인데 "안 들어있었다" 로 읽고 버린다.
#:
#:    2026-09-21 에 위키미디어 조회수 집계가 통째로 멈췄고(WP-200) 후보
#:    54,043건이 판정도 못 한 채 만료될 참이었다. 8월 선례는 복구까지 4일이었다.
#:
#:    그래서 적재 원장(V14)으로 전제를 직접 검사한다 — **상류가 이 후보의 시간을
#:    지나갔을 때만** 버린다.
#:
#:      상류 정지        원장이 안 늘어 아무것도 안 버린다. 쌓이지만 그게 사실이다
#:      그 시간만 결손   뒤 시간이 들어와 원장이 넘어가므로 36시간 뒤 정상 만료
#:      상류 복귀        원장 행 하나만 들어와도 그보다 오래된 후보 전부가 다시
#:                       만료 대상이 된다 (`>=` 라서). 백로그가 저절로 풀린다
#:
#: ⚠️ **원장이 비면 아무것도 안 버린다.** 배포 직후가 그렇다. 첫 적재 한 번으로
#:    해소되지만, 상류가 오래 멈춰 있으면 그동안 무한정 쌓인다. 지금은 "판정 가능한
#:    걸 버리는 것보다 쌓이는 게 낫다" 로 둔다 — 상한이 필요하면 별건이다.
EXPIRE_SQL = """
DELETE FROM spike_candidate c
 USING wiki_page p
 WHERE p.id = c.page_id
   AND c.source = %s
   AND c.first_seen_at < %s
   AND EXISTS (SELECT 1
                 FROM page_view_hourly_ingest g
                WHERE g.wiki = p.wiki
                  AND g.ts_hour >= c.window_start)
"""

BUMP_RECHECK_SQL = """
UPDATE spike_candidate SET recheck_count = recheck_count + 1
 WHERE source = %s AND page_id = %s AND window_start = %s
"""


@dataclass(frozen=True)
class DueCandidate:
    """조회수가 도착한 대기 한 건. 재판정 입력.

    `source`·`page_id` 를 같이 들고 다니는 이유는 재판정 뒤 이 행을 **지워야** 하기
    때문이다 — 제목으로 다시 찾으면 그 사이 문서가 이동했을 때 엉뚱한 행을 지운다.
    """
    source: str
    page_id: int
    window: PageWindow
    views: int

    @property
    def key(self) -> tuple[str, int, datetime]:
        return (self.source, self.page_id, self.window.window_start)


class CandidateStore:
    """`spike_candidate` 한 출처(source)의 보관소. 커밋은 호출자 책임이다."""

    def __init__(self, conn, source: str = "live") -> None:
        self._conn = conn
        self._source = require_source(source)
        self._page_ids: dict[tuple[str, str], int] = {}

    @property
    def source(self) -> str:
        return self._source

    def page_id(self, wiki: str, title: str) -> int:
        """`(wiki, title)` → `wiki_page.id`. 없으면 만든다 (`SpikeSink.page_id` 와 같은 규칙).

        싱크 없이 보관만 하는 실행(진단·드라이런)에서 런타임이 이걸 쓴다.
        """
        from .baseline_sink import resolve_page_ids

        key = (wiki, title)
        if key not in self._page_ids:
            with self._conn.cursor() as cur:
                self._page_ids.update(resolve_page_ids(cur, [key]))
        return self._page_ids[key]

    def save(self, page_id: int, window: PageWindow) -> None:
        """후보 대기를 보관한다. 같은 윈도우가 다시 오면 편집 수만 갱신된다.

        ⚠️ 판정하지 않는다 — 대기라는 판정이 이미 난 뒤에 불린다.
        """
        with self._conn.cursor() as cur:
            cur.execute(UPSERT_CANDIDATE_SQL, (
                self._source, page_id,
                require_utc(window.window_start, "window_start"),
                require_utc(window.window_end, "window_end"),
                window.edit_count, window.editor_count,
                window.max_rev_id,
                None if window.last_edit_ts is None
                else require_utc(window.last_edit_ts, "last_edit_ts"),
            ))

    def drop(self, page_id: int, window_start: datetime) -> None:
        """대기를 지운다. 확정(spike 로 옮김)·폐기 둘 다 여기로 끝난다."""
        with self._conn.cursor() as cur:
            cur.execute(DELETE_CANDIDATE_SQL,
                        (self._source, page_id, require_utc(window_start, "window_start")))

    def bump(self, page_id: int, window_start: datetime) -> None:
        """재판정 시도 횟수를 올린다. 조회수가 계속 안 오는 문서를 찾는 진단값이다."""
        with self._conn.cursor() as cur:
            cur.execute(BUMP_RECHECK_SQL,
                        (self._source, page_id, require_utc(window_start, "window_start")))

    def due(self, limit: int = 1_000) -> Iterator[DueCandidate]:
        """조회수 원본이 **이미 도착한** 시간의 대기를 오래된 것부터 준다.

        🔴 "조회수 행이 있는" 이 아니라 "그 시간 원본이 도착한" 이다
        (WP-199). 덤프가 0회 문서를 안 실어서 둘이 다르다 — 원본은 왔는데
        그 문서만 행이 없으면 `views=0` 으로 준다. 적재 원장(V14)이 그 구분을 준다.

        🔴 **정각 윈도우만 붙는다.** 조회수는 시간 버킷(`page_view_hourly.ts_hour`)이라
        윈도우 시작이 정각이어야 1:1 로 대응한다. LIVE 기본 슬라이드는 5분이라 한 시간에
        12개 윈도우가 나오는데, 그중 정각 하나만 조회수를 받는다. 나머지 11개는 여기에
        영영 안 걸리고 만료로 사라진다 — 조회수를 쪼개 배분하면 그건 **없는 정밀도를
        지어내는 것**이다.

        ⚠️ 그래서 LIVE 를 확정까지 돌리려면 `SLIDE_SIZE` 를 `WINDOW_SIZE` 와 같게 줘서
        정각 tumbling 으로 흘리는 게 맞다 (`streaming/live_spike.py` 모듈 독스트링).
        """
        with self._conn.cursor() as cur:
            cur.execute(SELECT_DUE_SQL, (self._source, limit))
            for row in cur.fetchall():
                (source, page_id, wiki, title, window_start, window_end,
                 edit_count, editor_count, max_rev_id, last_edit_ts, views,
                 mobile_views) = row
                yield DueCandidate(
                    source=source,
                    page_id=page_id,
                    window=PageWindow(
                        wiki=wiki, title=title,
                        window_start=window_start, window_end=window_end,
                        edit_count=edit_count, editor_count=editor_count,
                        views=views, mobile_views=mobile_views,
                        max_rev_id=max_rev_id, last_edit_ts=last_edit_ts,
                    ),
                    views=views,
                )

    def expire(self, *, now: datetime, hours: int = DEFAULT_EXPIRE_HOURS) -> int:
        """오래된 대기를 버린다. 반환: 지운 행 수.

        조회수가 영영 안 오는 문서가 있다(삭제·이동, 또는 후보 필터 밖). 안 버리면
        매 실행에서 같은 행을 다시 조회한다.

        🔴 **시간만으로는 안 버린다** (WP-202). 상류가 그 시간을 지나간 증거
        (적재 원장 V14)가 같이 있어야 한다 — 상류가 멈춘 것과 그 문서가 없었던 것은
        다른 사실이다. 근거는 `EXPIRE_SQL` 주석.
        """
        cutoff = require_utc(now, "now") - timedelta(hours=hours)
        with self._conn.cursor() as cur:
            cur.execute(EXPIRE_SQL, (self._source, cutoff))
            return cur.rowcount

    def count(self) -> int:
        """보관 중인 대기 수. 로그·측정용."""
        with self._conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM spike_candidate WHERE source = %s",
                        (self._source,))
            return cur.fetchone()[0]
