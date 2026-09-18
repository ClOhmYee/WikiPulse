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

#: 조회수가 들어온 대기만 고른다. 🔴 `ts_hour = window_start` 라 **정각 윈도우만** 붙는다.
SELECT_DUE = """
SELECT p.title, c.edit_count, v.views
  FROM spike_candidate c
  JOIN wiki_page p ON p.id = c.page_id
  JOIN page_view_hourly v ON v.page_id = c.page_id AND v.ts_hour = c.window_start
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


def test_조회수가_도착한_대기만_고른다(conn):
    """🔴 재판정 대상 선별이다. 조회수가 없는 대기는 안 걸려야 다음 실행에서 다시 본다."""
    ready, waiting = _page(conn, "Ready"), _page(conn, "Waiting")
    _candidate(conn, ready)
    _candidate(conn, waiting)
    _views(conn, ready, WINDOW_START, 24_669)

    assert q(conn, SELECT_DUE, "live") == [("Ready", 12, 24_669)]


def test_조회수_0도_도착한_것이다(conn):
    """⚠️ 행이 있으면 그 시간 조회수를 실제로 받은 것이다 — 0 은 관측이고, 폐기로 끝난다.

    "원본 미도착" 은 행이 **없는** 것으로 표현한다 (WP-127).
    """
    pid = _page(conn, "Quiet")
    _candidate(conn, pid)
    _views(conn, pid, WINDOW_START, 0)

    assert q(conn, SELECT_DUE, "live") == [("Quiet", 12, 0)]


def test_정각이_아닌_윈도우는_조회수와_안_붙는다(conn):
    """🔴 조회수는 시간 버킷이라 정각 윈도우만 1:1 로 대응한다.

    슬라이딩(5분) 윈도우는 여기 안 걸리고 만료로 사라진다. 조회수를 쪼개 배분하면
    없는 정밀도를 지어내는 것이라 안 한다 — 확정까지 돌리려면 정각 tumbling 으로 흘린다.
    """
    pid = _page(conn, "Sliding")
    _candidate(conn, pid, start="2025-06-12T09:05:00Z", end="2025-06-12T10:05:00Z")
    _views(conn, pid, WINDOW_START, 24_669)

    assert q(conn, SELECT_DUE, "live") == []


def test_만료는_first_seen_at_기준이다(conn):
    pid = _page(conn, "Stale")
    _candidate(conn, pid)
    x(conn, "UPDATE spike_candidate SET first_seen_at = now() - interval '48 hours' "
            "WHERE page_id = %s", pid)

    x(conn, "DELETE FROM spike_candidate WHERE source = %s AND first_seen_at < %s",
      "live", "2026-09-18T00:00:00Z")
    assert q(conn, "SELECT count(*) FROM spike_candidate WHERE page_id = %s", pid)[0][0] == 0


def test_문서를_지우면_대기도_지워진다(conn):
    pid = _page(conn, "Doomed")
    _candidate(conn, pid)
    x(conn, "DELETE FROM wiki_page WHERE id = %s", pid)

    assert q(conn, "SELECT count(*) FROM spike_candidate WHERE page_id = %s", pid)[0][0] == 0


def test_없는_문서에는_대기를_못_넣는다(conn):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        _candidate(conn, 999_999_999)
