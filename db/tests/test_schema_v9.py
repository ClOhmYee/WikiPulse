"""감지 결과의 시점 증거 검증 — V9 (WP-129 2번).

conftest 픽스처(conn)가 V1~V9 를 순서대로 적재한다.

여기서 보는 건 "규칙이 지켜졌는지 확인할 수 있는가" 다. 판정 로직은 data-pipeline 몫이고,
이 파일은 감사 질의가 실제로 성립하는지만 본다.
"""

from __future__ import annotations

import pytest

from conftest import q, x  # 공용 픽스처(conn·rollback)·헬퍼

pytest.importorskip("psycopg", reason="psycopg 미설치")

SNAPSHOT = "2025-06-12T09:00:00Z"


def _page(conn, title: str) -> int:
    return q(conn, "INSERT INTO wiki_page (wiki, title) VALUES ('enwiki', %s) RETURNING id",
             title)[0][0]


def _spike(conn, page_id: int, *, window_start: str, window_end: str,
           max_rev_id=None, last_edit_ts=None, source="replay") -> None:
    x(conn,
      "INSERT INTO spike (source, page_id, detected_at, window_start, edit_count, "
      "spike_score, max_rev_id, last_edit_ts) "
      "VALUES (%s, %s, %s, %s, 12, 5.5, %s, %s)",
      source, page_id, window_end, window_start, max_rev_id, last_edit_ts)


def test_증거를_같이_저장한다(conn):
    pid = _page(conn, "Air India Flight 171")
    _spike(conn, pid, window_start="2025-06-12T08:00:00Z", window_end="2025-06-12T09:00:00Z",
           max_rev_id=1_295_306_391, last_edit_ts="2025-06-12T08:58:23Z")

    row = q(conn, "SELECT max_rev_id, last_edit_ts <= window_start + interval '1 hour' "
                  "FROM spike WHERE page_id = %s", pid)[0]
    assert row == (1_295_306_391, True)


def test_revision_id는_BIGINT다(conn):
    """enwiki revision id 는 이미 12억대다 — INTEGER(21억 상한)로 잡으면 곧 넘친다."""
    pid = _page(conn, "Big Rev")
    _spike(conn, pid, window_start="2025-06-12T08:00:00Z", window_end="2025-06-12T09:00:00Z",
           max_rev_id=9_223_372_036_854_775_806)

    assert q(conn, "SELECT max_rev_id FROM spike WHERE page_id = %s",
             pid)[0][0] == 9_223_372_036_854_775_806


def test_증거_없는_옛_행도_그대로_들어간다(conn):
    """V9 이전 행은 NULL 이다. ⚠️ 통과가 아니라 **감사 보류** 로 읽는다."""
    pid = _page(conn, "Old Row")
    _spike(conn, pid, window_start="2025-06-12T08:00:00Z", window_end="2025-06-12T09:00:00Z")

    assert q(conn, "SELECT max_rev_id, last_edit_ts FROM spike WHERE page_id = %s",
             pid)[0] == (None, None)


def test_증거_없는_행을_찾는_감사_질의(conn):
    """이 질의가 부분 인덱스(spike_missing_revision_idx)가 있는 이유다."""
    have, missing = _page(conn, "Have"), _page(conn, "Missing")
    _spike(conn, have, window_start="2025-06-12T08:00:00Z",
           window_end="2025-06-12T09:00:00Z", max_rev_id=100)
    _spike(conn, missing, window_start="2025-06-12T08:00:00Z",
           window_end="2025-06-12T09:00:00Z")

    rows = q(conn, "SELECT p.title FROM spike s JOIN wiki_page p ON p.id = s.page_id "
                   "WHERE s.max_rev_id IS NULL")
    assert [r[0] for r in rows] == ["Missing"]


def test_스냅샷_뒤_편집이_섞인_행을_찾아낸다(conn):
    """🔴 이 질의에 걸리는 행이 있으면 시점 계약이 깨진 것이다 (명세 v0.3).

    리플레이 spike 는 `last_edit_ts <= window_end <= snapshot_ts` 여야 한다.
    증거가 없으면 이 검사 자체가 성립하지 않는다 — 그게 이 마이그레이션 이전 상태였다.
    """
    clean, dirty = _page(conn, "Clean"), _page(conn, "Dirty")
    _spike(conn, clean, window_start="2025-06-12T08:00:00Z",
           window_end="2025-06-12T09:00:00Z", last_edit_ts="2025-06-12T08:58:23Z")
    # 윈도우 끝보다 뒤의 편집이 섞인 행. 파이프라인은 PageWindow 에서 막지만,
    # 다른 경로(수동 적재·옛 산출물)로 들어올 수 있어 DB 쪽에서도 찾아낼 수 있어야 한다.
    _spike(conn, dirty, window_start="2025-06-12T08:00:00Z",
           window_end="2025-06-12T09:00:00Z", last_edit_ts="2025-06-12T10:30:00Z")

    rows = q(conn,
             "SELECT p.title FROM spike s JOIN wiki_page p ON p.id = s.page_id "
             " WHERE s.source = 'replay' AND s.last_edit_ts IS NOT NULL "
             "   AND (s.last_edit_ts > s.detected_at OR s.detected_at > %s)", SNAPSHOT)
    assert [r[0] for r in rows] == ["Dirty"]


def test_재적재하면_증거가_갱신된다(conn):
    """UPSERT 경로(spike_sink) 와 같은 구문. 옛 NULL 행이 다시 적재되면 채워져야 한다."""
    pid = _page(conn, "Refill")
    _spike(conn, pid, window_start="2025-06-12T08:00:00Z", window_end="2025-06-12T09:00:00Z")
    x(conn,
      "INSERT INTO spike (source, page_id, detected_at, window_start, edit_count, "
      "spike_score, max_rev_id, last_edit_ts) "
      "VALUES ('replay', %s, '2025-06-12T09:00:00Z', '2025-06-12T08:00:00Z', 12, 5.5, "
      "%s, %s) "
      "ON CONFLICT (source, page_id, window_start) DO UPDATE SET "
      "  max_rev_id = EXCLUDED.max_rev_id, last_edit_ts = EXCLUDED.last_edit_ts",
      pid, 777, "2025-06-12T08:58:23Z")

    assert q(conn, "SELECT count(*), max(max_rev_id) FROM spike WHERE page_id = %s",
             pid)[0] == (1, 777)
