"""이슈 상세 members 질의의 시점 계약 (WP-129 5번).

`IssueQueryRepository.findMembers` 와 같은 SQL 이다. 백엔드 테스트는 DB 없이 도는 웹
레이어 검사뿐이라(그 저장소의 관습) 이 질의가 실제로 무엇을 읽는지는 여기서 본다.

🔴 이 파일이 고정하는 건 하나다: **과거 스냅샷을 열었을 때, 그 뒤에 들어온 원시 행이
응답을 바꾸지 않는다.** 여태 상세는 `page_edit_window`·`page_view_hourly` 의 최신 한 행을
끌어와서, 2025-06-12 09시 이슈에 오늘 조회수가 붙었다. 값이 그럴듯해서 화면만 봐서는
틀린 줄 모른다.
"""

from __future__ import annotations

import pytest

from conftest import q, x  # 공용 픽스처(conn·rollback)·헬퍼

pytest.importorskip("psycopg", reason="psycopg 미설치")

SNAPSHOT = "2025-06-12T09:00:00Z"
LATER = "2026-09-18T00:00:00Z"

#: 백엔드 IssueQueryRepository.findMembers 와 같은 질의.
MEMBERS_SQL = """
SELECT p.title, cm.edit_count, cm.views, cm.completeness
  FROM cluster_member cm
  JOIN wiki_page p ON p.id = cm.page_id
 WHERE cm.cluster_id = %s
 ORDER BY cm.is_seed DESC, cm.weight DESC
"""


def _page(conn, title: str) -> int:
    return q(conn, "INSERT INTO wiki_page (wiki, title) VALUES ('enwiki', %s) RETURNING id",
             title)[0][0]


def _cluster(conn, snapshot_ts: str = SNAPSHOT, source: str = "replay") -> int:
    x(conn, "INSERT INTO issue_cluster (snapshot_ts, pulse_score, source) VALUES (%s, 1.0, %s)",
      snapshot_ts, source)
    return q(conn, "SELECT max(id) FROM issue_cluster")[0][0]


def _member(conn, cid: int, page_id: int, *, edit_count=None, views=None,
            completeness="complete", is_seed=True, weight=1.0) -> None:
    x(conn,
      "INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed, edit_count, "
      "views, completeness) VALUES (%s, %s, %s, %s, %s, %s, %s)",
      cid, page_id, weight, is_seed, edit_count, views, completeness)


def test_판정_당시_값을_읽는다(conn):
    pid = _page(conn, "Air India Flight 171")
    cid = _cluster(conn)
    _member(conn, cid, pid, edit_count=126, views=24_669)

    assert q(conn, MEMBERS_SQL, cid) == [("Air India Flight 171", 126, 24_669, "complete")]


def test_나중에_들어온_원시_행이_과거_응답을_안_바꾼다(conn):
    """🔴 이 결함의 회귀 방지다.

    같은 문서의 편집·조회수가 1년 뒤에 더 쌓여도 2025-06-12 스냅샷의 응답은 그대로여야
    한다. 옛 질의는 `page_edit_window`·`page_view_hourly` 의 **최신** 한 행을 끌어왔다.
    """
    pid = _page(conn, "Air India Flight 171")
    cid = _cluster(conn)
    _member(conn, cid, pid, edit_count=126, views=24_669)
    before = q(conn, MEMBERS_SQL, cid)

    # 스냅샷 한참 뒤의 원시 행. 옛 질의라면 이 값들이 응답에 실렸다.
    x(conn, "INSERT INTO page_edit_window (page_id, window_start, window_end, edit_count, "
            "editor_count) VALUES (%s, %s, %s, 9999, 50)", pid, LATER, "2026-09-18T01:00:00Z")
    x(conn, "INSERT INTO page_view_hourly (page_id, ts_hour, views) VALUES (%s, %s, 888888)",
      pid, LATER)

    assert q(conn, MEMBERS_SQL, cid) == before


def test_값이_없으면_null이고_completeness가_이유를_말한다(conn):
    """⚠️ null 을 최신 원시 행으로 메우지 않는다. 대신 상태를 같이 준다 (명세 §5.2).

    `pending`(입력 대기)과 `unavailable`(원본 없음)은 화면에서 다르게 말해야 한다 —
    둘 다 빈칸으로 보이면 사용자는 서비스가 고장 난 줄 안다.
    """
    waiting, gone = _page(conn, "Waiting"), _page(conn, "No Source")
    cid = _cluster(conn)
    _member(conn, cid, waiting, completeness="pending", weight=2.0)
    _member(conn, cid, gone, completeness="unavailable", weight=1.0)

    assert q(conn, MEMBERS_SQL, cid) == [
        ("Waiting", None, None, "pending"),
        ("No Source", None, None, "unavailable"),
    ]


def test_같은_문서의_두_스냅샷이_각자_값을_갖는다(conn):
    """이슈 하나를 시점별로 훑을 때 수치가 시점마다 달라야 한다.

    옛 질의는 두 스냅샷이 **같은** 최신 값을 냈다 — 시간이 흘러도 그래프가 평평했다.
    """
    pid = _page(conn, "Air India Flight 171")
    early = _cluster(conn, "2025-06-12T09:00:00Z")
    late = _cluster(conn, "2025-06-12T23:00:00Z")
    _member(conn, early, pid, edit_count=126, views=24_669)
    _member(conn, late, pid, edit_count=22, views=25_426)

    assert q(conn, MEMBERS_SQL, early)[0][1:3] == (126, 24_669)
    assert q(conn, MEMBERS_SQL, late)[0][1:3] == (22, 25_426)


def test_정렬은_씨드_먼저_그다음_가중치(conn):
    cid = _cluster(conn)
    seed = _page(conn, "Seed")
    heavy, light = _page(conn, "Heavy"), _page(conn, "Light")
    _member(conn, cid, light, is_seed=False, weight=1.0)
    _member(conn, cid, heavy, is_seed=False, weight=9.0)
    _member(conn, cid, seed, is_seed=True, weight=0.1)

    assert [r[0] for r in q(conn, MEMBERS_SQL, cid)] == ["Seed", "Heavy", "Light"]
