"""시간별 조회수 적재 SQL 검증 (WP-127).

`batch/pageview_hourly_ingest.UPSERT_VIEW_SQL` 과 같은 구문이다. data-pipeline 테스트는
Docker PostgreSQL 이 있어야 돌지만 이 파일은 pgserver 로 도므로, 적재 SQL 자체의 계약은
여기서 항상 확인된다.
"""

from __future__ import annotations

import pytest

from conftest import q, x  # 공용 픽스처(conn·rollback)·헬퍼

pytest.importorskip("psycopg", reason="psycopg 미설치")
import psycopg  # noqa: E402

UPSERT = """
INSERT INTO page_view_hourly (page_id, ts_hour, views)
VALUES (%s, %s, %s)
ON CONFLICT (page_id, ts_hour) DO UPDATE SET views = EXCLUDED.views
"""


def _page(conn, title: str) -> int:
    return q(conn, "INSERT INTO wiki_page (wiki, title) VALUES ('enwiki', %s) RETURNING id",
             title)[0][0]


def test_시간별_조회수를_적재한다(conn):
    pid = _page(conn, "Air India Flight 171")
    x(conn, UPSERT, pid, "2025-06-12T09:00:00Z", 24_669)

    assert q(conn, "SELECT views FROM page_view_hourly WHERE page_id = %s", pid)[0][0] == 24_669


def test_같은_시간을_다시_받으면_값만_갱신된다(conn):
    """덤프를 다시 받거나 후보 집합이 늘어 재적재하는 일이 잦다 — 행이 늘면 안 된다."""
    pid = _page(conn, "Air India Flight 171")
    x(conn, UPSERT, pid, "2025-06-12T09:00:00Z", 24_000)
    x(conn, UPSERT, pid, "2025-06-12T09:00:00Z", 24_669)

    rows = q(conn, "SELECT count(*), max(views) FROM page_view_hourly WHERE page_id = %s", pid)
    assert rows[0] == (1, 24_669)


def test_다른_시간은_각각_한_행이다(conn):
    pid = _page(conn, "Air India Flight 171")
    x(conn, UPSERT, pid, "2025-06-12T09:00:00Z", 24_669)
    x(conn, UPSERT, pid, "2025-06-12T23:00:00Z", 25_426)

    assert q(conn, "SELECT count(*) FROM page_view_hourly WHERE page_id = %s", pid)[0][0] == 2


def test_조회수_0도_저장된다(conn):
    """⚠️ "그 시간에 0회" 는 정상 관측이다. "원본 미도착" 은 행이 없는 것으로 표현한다 —
    둘을 같은 값으로 만들면 기준선이 조용히 내려간다 (WP-127)."""
    pid = _page(conn, "Quiet Page")
    x(conn, UPSERT, pid, "2025-06-12T03:00:00Z", 0)

    assert q(conn, "SELECT views FROM page_view_hourly WHERE page_id = %s", pid)[0][0] == 0


def test_없는_문서에는_못_넣는다(conn):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        x(conn, UPSERT, 999_999_999, "2025-06-12T09:00:00Z", 10)


def test_문서를_지우면_조회수도_지워진다(conn):
    pid = _page(conn, "Doomed")
    x(conn, UPSERT, pid, "2025-06-12T09:00:00Z", 10)
    x(conn, "DELETE FROM wiki_page WHERE id = %s", pid)

    assert q(conn, "SELECT count(*) FROM page_view_hourly WHERE page_id = %s", pid)[0][0] == 0
