"""후보 대기 보관 SQL 검증 — V10 (WP-128).

`spike/candidate_store.py` 의 질의와 같은 구문이다. data-pipeline 쪽 실 DB 테스트는 Docker
PostgreSQL 이 있어야 돌지만 이 파일은 pgserver 로 돌아서, 보관·조인·삭제 계약은 항상 확인된다.
"""

from __future__ import annotations

import pytest

from conftest import q, x  # 공용 픽스처(conn·rollback)·헬퍼

pytest.importorskip("psycopg", reason="psycopg 미설치")
import psycopg  # noqa: E402

WINDOW_START = "2025-06-12T09:00:00Z"
WINDOW_END = "2025-06-12T10:00:00Z"

#: 원본이 아직 안 온 다음 시간. ⚠️ -199 이후로는 "조회수 행이 없다" 만으로는 대기가
#: 안 된다 — 그 시간이 적재 원장에 없어야 대기다. 그래서 대기 쪽 표본은 원장에 없는
#: 시간에 둔다.
LATER_START = "2025-06-12T10:00:00Z"
LATER_END = "2025-06-12T11:00:00Z"

UPSERT = """
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

#: 조회수 원본이 **도착한 시간**의 대기를 고른다. 🔴 `ts_hour = window_start` 라
#: **정각 윈도우만** 붙는다.
#:
#: 🔴 기준은 `page_view_hourly` 행이 아니라 **적재 원장**(`page_view_hourly_ingest`,
#:    V14)이다 (WP-199). 덤프가 조회수 0 인 문서를 안 실어서, 행이 없는 것이
#:    "미도착" 과 "0회" 를 동시에 뜻하기 때문이다. 원장이 둘을 가른다.
SELECT_DUE = """
SELECT p.title, c.edit_count, COALESCE(v.views, 0) AS views
  FROM spike_candidate c
  JOIN wiki_page p ON p.id = c.page_id
  JOIN page_view_hourly_ingest g
       ON g.wiki = p.wiki AND g.ts_hour = c.window_start
  LEFT JOIN page_view_hourly v
       ON v.page_id = c.page_id AND v.ts_hour = c.window_start
 WHERE c.source = %s
 ORDER BY c.window_start
"""


def _page(conn, title: str) -> int:
    return q(conn, "INSERT INTO wiki_page (wiki, title) VALUES ('enwiki', %s) RETURNING id",
             title)[0][0]


def _candidate(conn, page_id: int, *, source="live", start=WINDOW_START, end=WINDOW_END,
               edits=12, editors=3, max_rev_id=None, last_edit_ts=None) -> None:
    x(conn, UPSERT, source, page_id, start, end, edits, editors, max_rev_id, last_edit_ts)


def _views(conn, page_id: int, ts_hour: str, views: int) -> None:
    x(conn, "INSERT INTO page_view_hourly (page_id, ts_hour, views) VALUES (%s, %s, %s)",
      page_id, ts_hour, views)


def _ingested(conn, ts_hour: str = WINDOW_START, *, wiki="enwiki", rows: int = 1) -> None:
    """그 시간 조회수 원본이 도착했다고 원장에 적는다 (V14).

    🔴 `_views` 와 별개다. 원본은 왔는데 그 문서가 0회면 `page_view_hourly` 에 행이
    없고 원장에만 있다 — 그게 이 표를 만든 이유다 (WP-199).
    """
    x(conn, "INSERT INTO page_view_hourly_ingest (wiki, ts_hour, rows) VALUES (%s, %s, %s)",
      wiki, ts_hour, rows)


def test_대기를_보관한다(conn):
    pid = _page(conn, "Air India Flight 171")
    _candidate(conn, pid, max_rev_id=1_295_306_391, last_edit_ts="2025-06-12T09:58:23Z")

    row = q(conn, "SELECT edit_count, editor_count, max_rev_id, recheck_count "
                  "FROM spike_candidate WHERE page_id = %s", pid)[0]
    assert row == (12, 3, 1_295_306_391, 0)


def test_같은_윈도우가_다시_와도_행이_안_는다(conn):
    """스트리밍은 같은 윈도우를 더 큰 집계로 다시 준다(update 모드). 행은 하나여야 한다."""
    pid = _page(conn, "Air India Flight 171")
    _candidate(conn, pid, edits=12)
    _candidate(conn, pid, edits=40)

    assert q(conn, "SELECT count(*), max(edit_count) FROM spike_candidate "
                   "WHERE page_id = %s", pid)[0] == (1, 40)


def test_출처가_다르면_다른_행이다(conn):
    """리플레이와 LIVE 가 같은 윈도우를 각자 대기로 들 수 있다 — spike 와 같은 키 규칙(V5)."""
    pid = _page(conn, "Air India Flight 171")
    _candidate(conn, pid, source="live")
    _candidate(conn, pid, source="replay")

    assert q(conn, "SELECT count(*) FROM spike_candidate WHERE page_id = %s", pid)[0][0] == 2


def test_정해진_출처만_받는다(conn):
    pid = _page(conn, "Air India Flight 171")
    with pytest.raises(psycopg.errors.CheckViolation):
        _candidate(conn, pid, source="canary")


def test_원본이_도착한_시간의_대기만_고른다(conn):
    """🔴 재판정 대상 선별이다. 원본이 안 온 시간은 안 걸려야 다음 실행에서 다시 본다."""
    ready, waiting = _page(conn, "Ready"), _page(conn, "Waiting")
    _candidate(conn, ready)
    _candidate(conn, waiting, start=LATER_START, end=LATER_END)
    _ingested(conn, WINDOW_START)
    _views(conn, ready, WINDOW_START, 24_669)

    assert q(conn, SELECT_DUE, "live") == [("Ready", 12, 24_669)]


def test_원본은_왔는데_조회수_행이_없으면_0회다(conn):
    """🔴 이 파일의 핵심이다 (WP-199). 덤프가 **0회 문서를 안 싣는다.**

    그래서 `page_view_hourly` 행이 없는 것이 "미도착" 과 "0회" 둘 다를 뜻한다. 옛
    SQL 은 `JOIN page_view_hourly` 라 전자로만 해석했고, 0회 문서가 영영 대기로 남아
    **재판정 큐가 맨 앞에서 막혔다** — 2026-09-22 에 500건이 뒤의 53,982건을 굶겼다.

    원장에 그 시간이 있으면 도착한 것이므로 `views=0` 으로 내려 폐기까지 간다.
    """
    pid = _page(conn, "Quiet")
    _candidate(conn, pid)
    _ingested(conn, WINDOW_START)  # 원본은 왔다. 이 문서만 덤프에 없다.

    assert q(conn, SELECT_DUE, "live") == [("Quiet", 12, 0)]


def test_원장에_없는_시간은_미도착이라_대기로_남는다(conn):
    """⚠️ 위 규칙의 반대쪽이다. 여기서 0 으로 내리면 **안 온 걸 0회로 오판**한다.

    상류 지연은 흔하다 — 2026-09-21 에 위키미디어 집계가 통째로 멈춰 18시간 안 왔다
    (WP-200). 그 동안 후보는 폐기가 아니라 대기여야 한다.
    """
    pid = _page(conn, "NotArrivedYet")
    _candidate(conn, pid)

    assert q(conn, SELECT_DUE, "live") == []


def test_원장은_wiki_별로_본다(conn):
    """⚠️ 원장 키가 `(wiki, ts_hour)` 다. 다른 wiki 적재를 도착으로 읽으면 안 된다."""
    pid = _page(conn, "English page")  # `_page` 는 enwiki 로 넣는다
    _candidate(conn, pid)
    _ingested(conn, WINDOW_START, wiki="kowiki")

    assert q(conn, SELECT_DUE, "live") == []


def test_원장_행_수가_0이어도_도착이다(conn):
    """🔴 `rows > 0` 을 도착 조건으로 쓰면 안 된다.

    LIVE 적재는 대기 목록의 문서만 선택적으로 받는다(전수는 시간당 149만 행이라 못
    한다). 그 시간 후보가 전부 0회면 쓴 행이 0개가 되는데, 그건 미적재가 아니다.
    """
    pid = _page(conn, "All zero hour")
    _candidate(conn, pid)
    _ingested(conn, WINDOW_START, rows=0)

    assert q(conn, SELECT_DUE, "live") == [("All zero hour", 12, 0)]


def test_정각이_아닌_윈도우는_조회수와_안_붙는다(conn):
    """🔴 조회수는 시간 버킷이라 정각 윈도우만 1:1 로 대응한다.

    슬라이딩(5분) 윈도우는 여기 안 걸리고 만료로 사라진다. 조회수를 쪼개 배분하면
    없는 정밀도를 지어내는 것이라 안 한다 — 확정까지 돌리려면 정각 tumbling 으로 흘린다.

    ⚠️ 원장 조인도 같은 `ts_hour = window_start` 를 쓰므로 -199 이후에도 그대로다.
    """
    pid = _page(conn, "Sliding")
    _candidate(conn, pid, start="2025-06-12T09:05:00Z", end="2025-06-12T10:05:00Z")
    _ingested(conn, WINDOW_START)
    _views(conn, pid, WINDOW_START, 24_669)

    assert q(conn, SELECT_DUE, "live") == []


def test_만료는_first_seen_at_기준이다(conn):
    """오래된 대기는 `first_seen_at` 으로 만료된다.

    🔴 **경계는 `now()` 기준 상대값이어야 한다.** ~~`first_seen_at < '2026-09-18T00:00:00Z'`~~
    처럼 날짜를 박으면 **그 날짜가 지나는 순간 조용히 깨진다** — 심은 행은 `now()-48h` 라
    같이 움직이는데 경계만 고정이라, `now()-48h` 가 경계를 넘어서면 삭제가 안 되고
    `assert 1 == 0` 으로 터진다. 실제로 **2026-09-20 00:00 UTC 부터** 깨져서 develop
    파이프라인이 실패했다(WP-151).

    ⚠️ 이 테스트가 develop 배포를 막는다 — `test:db` 가 실패하면 deploy 스테이지가
    통째로 skip 된다. 날짜를 박은 대가가 "테스트 하나 빨감" 이 아니라 "배포 중단" 이다.
    """
    pid = _page(conn, "Stale")
    _candidate(conn, pid)
    x(conn, "UPDATE spike_candidate SET first_seen_at = now() - interval '48 hours' "
            "WHERE page_id = %s", pid)

    # 48시간 된 행을 24시간 경계로 지운다 — 둘 다 now() 기준이라 언제 돌려도 같다.
    x(conn, "DELETE FROM spike_candidate WHERE source = %s "
            "AND first_seen_at < now() - interval '24 hours'", "live")
    assert q(conn, "SELECT count(*) FROM spike_candidate WHERE page_id = %s", pid)[0][0] == 0


def test_만료_경계_안쪽은_남는다(conn):
    """🔴 위 테스트의 짝 — 경계가 실제로 걸러내는지 확인한다.

    삭제만 검사하면 `DELETE` 가 전부 지워도 통과한다. 경계 안쪽(최근) 행이 살아남는 것까지
    봐야 "경계로 걸렀다" 가 된다.
    """
    pid = _page(conn, "Fresh")
    _candidate(conn, pid)
    x(conn, "UPDATE spike_candidate SET first_seen_at = now() - interval '1 hour' "
            "WHERE page_id = %s", pid)

    x(conn, "DELETE FROM spike_candidate WHERE source = %s "
            "AND first_seen_at < now() - interval '24 hours'", "live")
    assert q(conn, "SELECT count(*) FROM spike_candidate WHERE page_id = %s", pid)[0][0] == 1


def test_문서를_지우면_대기도_지워진다(conn):
    pid = _page(conn, "Doomed")
    _candidate(conn, pid)
    x(conn, "DELETE FROM wiki_page WHERE id = %s", pid)

    assert q(conn, "SELECT count(*) FROM spike_candidate WHERE page_id = %s", pid)[0][0] == 0


def test_없는_문서에는_대기를_못_넣는다(conn):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        _candidate(conn, 999_999_999)


# ── 적재 원장 (V14, WP-199) ──────────────────────────────────────────

#: `batch/pageview_hourly_ingest.py:RECORD_INGEST_SQL` 과 같은 구문이다.
RECORD_INGEST = """
INSERT INTO page_view_hourly_ingest (wiki, ts_hour, rows, ingested_at)
VALUES (%s, %s, %s, now())
ON CONFLICT (wiki, ts_hour) DO UPDATE
   SET rows = EXCLUDED.rows, ingested_at = EXCLUDED.ingested_at
"""


def test_같은_시간을_다시_적재해도_행이_안_는다(conn):
    """재적재는 흔하다 — 캐시 재사용·수동 보정·재시작. 행 수만 갱신된다."""
    x(conn, RECORD_INGEST, "enwiki", WINDOW_START, 1_200)
    x(conn, RECORD_INGEST, "enwiki", WINDOW_START, 1_431)

    assert q(conn, "SELECT wiki, rows FROM page_view_hourly_ingest") == [("enwiki", 1_431)]


def test_원장은_wiki와_시간_쌍이_키다(conn):
    """다른 wiki·다른 시간은 각자 도착한다. 하나를 다른 쪽 근거로 쓰면 안 된다."""
    x(conn, RECORD_INGEST, "enwiki", WINDOW_START, 1_200)
    x(conn, RECORD_INGEST, "kowiki", WINDOW_START, 12)
    x(conn, RECORD_INGEST, "enwiki", LATER_START, 1_300)

    assert q(conn, "SELECT count(*) FROM page_view_hourly_ingest") == [(3,)]


def test_행_수는_음수가_못_된다(conn):
    """⚠️ 음수는 계산 실수의 신호다. 조용히 들어가면 "0행 적재" 와 구분이 안 된다."""
    with pytest.raises(psycopg.errors.CheckViolation):
        x(conn, RECORD_INGEST, "enwiki", WINDOW_START, -1)
