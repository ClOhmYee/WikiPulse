"""시점별 도입부 고정 검증 — V8 (WP-129 1번).

conftest 픽스처(conn)가 V1~V8 을 순서대로 적재한다.

여기 SQL 은 백엔드 `ClusterIntroRepository` 의 질의와 같은 모양이다. 백엔드 테스트는 DB 없이
도는 목 검사라(그 저장소의 관습) 실제 SQL 이 맞는지는 이 파일이 본다.
"""

from __future__ import annotations

import pytest

from conftest import q, x  # 공용 픽스처(conn·rollback)·헬퍼

pytest.importorskip("psycopg", reason="psycopg 미설치")
import psycopg  # noqa: E402

AS_OF = "2025-06-12T09:00:00Z"


def _page(conn, title: str) -> int:
    return q(conn, "INSERT INTO wiki_page (wiki, title) VALUES ('enwiki', %s) RETURNING id", title)[0][0]


def _intro(conn, page_id: int, rev_id: int, rev_ts: str, intro: str) -> None:
    x(conn,
      "INSERT INTO page_intro (page_id, rev_id, rev_ts, intro) VALUES (%s, %s, %s, %s)",
      page_id, rev_id, rev_ts, intro)


def _intro_as_of(conn, page_id: int, as_of: str = AS_OF):
    rows = q(conn,
             "SELECT intro FROM page_intro WHERE page_id = %s AND rev_ts <= %s "
             "ORDER BY rev_ts DESC LIMIT 1",
             page_id, as_of)
    return rows[0][0] if rows else None


def test_스냅샷_이하_마지막_revision을_고른다(conn):
    """🔴 계약의 핵심. 스냅샷 **뒤** 편집이 과거 이슈에 새면 그게 이번 결함이다."""
    pid = _page(conn, "Air India Flight 171")
    _intro(conn, pid, 1, "2025-06-12T08:58:02Z", "생성 직후")
    _intro(conn, pid, 2, "2025-06-12T08:59:30Z", "스냅샷 직전")
    _intro(conn, pid, 3, "2025-06-12T09:30:00Z", "스냅샷 이후 — 미래 정보")

    assert _intro_as_of(conn, pid) == "스냅샷 직전"


def test_그_시점_이전_revision이_없으면_행이_없다(conn):
    """없으면 없는 거다 — 현재 도입부로 메우는 건 조회가 아니라 폴백이고, 계약이 금지한다."""
    pid = _page(conn, "Later Article")
    _intro(conn, pid, 10, "2025-07-01T00:00:00Z", "나중에 생긴 문서")

    assert _intro_as_of(conn, pid) is None


def test_같은_revision을_다시_받으면_행이_안_는다(conn):
    """다른 스냅샷이 같은 revision 으로 귀결되는 일이 흔하다 — 본문만 갱신한다."""
    pid = _page(conn, "Iran")
    _intro(conn, pid, 77, "2025-06-10T00:00:00Z", "처음 받은 본문")
    x(conn,
      "INSERT INTO page_intro (page_id, rev_id, rev_ts, intro) VALUES (%s, %s, %s, %s) "
      "ON CONFLICT (page_id, rev_id) DO UPDATE SET intro = EXCLUDED.intro, fetched_at = now()",
      pid, 77, "2025-06-10T00:00:00Z", "다시 받은 본문")

    assert q(conn, "SELECT count(*) FROM page_intro WHERE page_id = %s", pid)[0][0] == 1
    assert _intro_as_of(conn, pid) == "다시 받은 본문"


def test_같은_revision_id가_다른_문서에는_또_들어간다(conn):
    """키가 (page_id, rev_id) 라 문서가 다르면 충돌하지 않는다."""
    a, b = _page(conn, "A"), _page(conn, "B")
    _intro(conn, a, 5, "2025-06-01T00:00:00Z", "a")
    _intro(conn, b, 5, "2025-06-01T00:00:00Z", "b")

    assert q(conn, "SELECT count(*) FROM page_intro")[0][0] == 2


def test_문서를_지우면_고정본도_지워진다(conn):
    pid = _page(conn, "Doomed")
    _intro(conn, pid, 1, "2025-06-01T00:00:00Z", "본문")
    x(conn, "DELETE FROM wiki_page WHERE id = %s", pid)

    assert q(conn, "SELECT count(*) FROM page_intro WHERE page_id = %s", pid)[0][0] == 0


def test_없는_문서에는_고정본을_못_넣는다(conn):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        _intro(conn, 999_999_999, 1, "2025-06-01T00:00:00Z", "본문")


def test_클러스터_시점_질의가_출처와_멤버순서를_같이_준다(conn):
    """`ClusterIntroRepository.context` 의 질의다.

    제목만으로는 어느 시점 도입부를 쓸지 알 수 없어 source·snapshot_ts 를 같이 읽는다 —
    이 결함의 원인이 바로 "제목만 읽고 현재 도입부를 가져온" 것이었다.
    """
    x(conn, "INSERT INTO issue_cluster (snapshot_ts, pulse_score, source) "
            "VALUES (%s, 1.0, 'replay')", AS_OF)
    cid = q(conn, "SELECT max(id) FROM issue_cluster")[0][0]
    high, low = _page(conn, "High"), _page(conn, "Low")
    x(conn, "INSERT INTO cluster_member (cluster_id, page_id, weight, spike_score) "
            "VALUES (%s, %s, 1.0, 9.0)", cid, high)
    x(conn, "INSERT INTO cluster_member (cluster_id, page_id, weight, spike_score) "
            "VALUES (%s, %s, 1.0, 2.0)", cid, low)

    rows = q(conn,
             "SELECT c.source, c.snapshot_ts, cm.page_id, wp.title "
             "  FROM issue_cluster c "
             "  JOIN cluster_member cm ON cm.cluster_id = c.id "
             "  JOIN wiki_page wp ON wp.id = cm.page_id "
             " WHERE c.id = %s "
             " ORDER BY cm.spike_score DESC NULLS LAST, cm.weight DESC", cid)

    assert [r[3] for r in rows] == ["High", "Low"]
    assert {r[0] for r in rows} == {"replay"}
