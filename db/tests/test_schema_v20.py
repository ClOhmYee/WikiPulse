"""문서 표시용 한국어 제목 — V20.

conftest 픽스처(conn)가 V1~V14 와 V20 을 버전 순서대로 적재한다.
⚠️ V15~V19 가 비어 있는 것은 의도한 간격이다 — 이유는 마이그레이션 파일 머리말에 있다.

여기서 보는 것은 세 가지다.
  1. 세 상태(미조회 / 조회했고 없음 / 확보)가 실제로 구분되는가 — 음성 캐시의 전부다.
  2. 워커 대상 질의(`PageTitleRepository.findPending`)가 **cluster_member 에 편입된
     enwiki 문서만** 집는가. 전체 wiki_page 를 집으면 조회수 덤프가 만든 수백만 행을
     위키미디어에 물어보게 된다.
  3. 읽기 질의(`PulseMapRepository.findNodes` / `IssueQueryRepository.findMembers`)가
     title 과 title_ko 를 **둘 다** 내리는가 — 영문을 대체하는 게 아니라 더하는 것이다.

백엔드 테스트는 DB 없이 도는 목 검사라(그 저장소의 관습) 실제 SQL 이 맞는지는 이 파일이 본다.
"""

from __future__ import annotations

import pytest

from conftest import q, x  # 공용 픽스처(conn·rollback)·헬퍼

pytest.importorskip("psycopg", reason="psycopg 미설치")
import psycopg  # noqa: E402

SNAPSHOT = "2026-09-20T00:00:00Z"


def _page(conn, title: str, wiki: str = "enwiki") -> int:
    return q(conn, "INSERT INTO wiki_page (wiki, title) VALUES (%s, %s) RETURNING id",
             wiki, title)[0][0]


def _cluster(conn, source: str = "live") -> int:
    x(conn, "INSERT INTO issue_cluster (snapshot_ts, pulse_score, source) VALUES (%s, 1.0, %s)",
      SNAPSHOT, source)
    return q(conn, "SELECT max(id) FROM issue_cluster")[0][0]


def _member(conn, cluster_id: int, page_id: int, *, is_seed: bool = False,
            weight: float = 1.0) -> None:
    x(conn, "INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed) "
            "VALUES (%s, %s, %s, %s)", cluster_id, page_id, weight, is_seed)


#: 워커 대상 질의. 🔴 wiki_page 전수가 아니라 cluster_member 에서 출발한다.
PENDING_SQL = """
SELECT DISTINCT p.id, p.title
  FROM cluster_member cm
  JOIN wiki_page p ON p.id = cm.page_id
 WHERE p.wiki = %s AND p.title_ko_checked_at IS NULL
 ORDER BY p.id
 LIMIT %s
"""

#: 조회 결과 기록. ko 가 없어도(miss) checked_at 을 찍는다 — 그게 음성 캐시다.
RECORD_SQL = """
UPDATE wiki_page
   SET title_ko = %s, title_ko_checked_at = now()
 WHERE id = %s AND wiki = %s
"""


def test_새_컬럼은_기본이_미조회_상태다(conn):
    pid = _page(conn, "Hurricane Milton")
    row = q(conn, "SELECT title_ko, title_ko_checked_at FROM wiki_page WHERE id = %s", pid)[0]
    assert row == (None, None)


def test_세_상태가_구분된다(conn):
    """🔴 음성 캐시의 핵심. 이게 안 갈리면 ko 없는 문서를 매 주기 다시 물어본다."""
    never = _page(conn, "Never Checked")
    absent = _page(conn, "No Korean Article")
    present = _page(conn, "Strait of Hormuz")

    x(conn, RECORD_SQL, None, absent, "enwiki")
    x(conn, RECORD_SQL, "호르무즈 해협", present, "enwiki")

    state = dict(q(conn,
                   "SELECT title, (title_ko_checked_at IS NOT NULL) FROM wiki_page "
                   "WHERE id = ANY(%s)", [never, absent, present]))
    assert state == {
        "Never Checked": False,       # 아직 안 물어봄 → 워커 대상
        "No Korean Article": True,    # 물어봤고 없음 → 다시 안 물어봄
        "Strait of Hormuz": True,     # 확보
    }
    assert q(conn, "SELECT title_ko FROM wiki_page WHERE id = %s", absent)[0][0] is None
    assert q(conn, "SELECT title_ko FROM wiki_page WHERE id = %s", present)[0][0] == "호르무즈 해협"


def test_조회했고_없음은_다시_대상이_되지_않는다(conn):
    cid = _cluster(conn)
    absent, never = _page(conn, "A"), _page(conn, "B")
    _member(conn, cid, absent)
    _member(conn, cid, never)
    x(conn, RECORD_SQL, None, absent, "enwiki")

    assert [r[1] for r in q(conn, PENDING_SQL, "enwiki", 100)] == ["B"]


def test_대상은_클러스터에_편입된_문서뿐이다(conn):
    """조회수 덤프가 만든 wiki_page 행은 수백만이다 — 거길 훑으면 안 된다."""
    cid = _cluster(conn)
    member = _page(conn, "In Cluster")
    _member(conn, cid, member)
    _page(conn, "Only In Pageview Dump")     # cluster_member 없음

    assert [r[1] for r in q(conn, PENDING_SQL, "enwiki", 100)] == ["In Cluster"]


def test_대상은_enwiki_로_한정된다(conn):
    cid = _cluster(conn)
    en, ko = _page(conn, "Iran"), _page(conn, "Iran", wiki="kowiki")
    _member(conn, cid, en)
    _member(conn, cid, ko)

    rows = q(conn, PENDING_SQL, "enwiki", 100)
    assert [r[0] for r in rows] == [en]


def test_여러_스냅샷에_걸친_문서는_한_번만_나온다(conn):
    """DISTINCT 가 없으면 같은 문서를 스냅샷 수만큼 조회한다."""
    page = _page(conn, "Iran")
    for source in ("live", "replay"):
        _member(conn, _cluster(conn, source), page)

    assert len(q(conn, PENDING_SQL, "enwiki", 100)) == 1


def test_LIVE와_replay_를_가리지_않는다(conn):
    """같은 enrichment 가 두 출처에 다 걸려야 한다(계약)."""
    live_page, replay_page = _page(conn, "Live Only"), _page(conn, "Replay Only")
    _member(conn, _cluster(conn, "live"), live_page)
    _member(conn, _cluster(conn, "replay"), replay_page)

    assert {r[1] for r in q(conn, PENDING_SQL, "enwiki", 100)} == {"Live Only", "Replay Only"}


def test_빈_제목은_저장되지_않는다(conn):
    """빈 문자열이 들어가면 화면에 빈 제목이 뜬다 — NULL 이어야 폴백이 돈다."""
    for blank in ("", "   "):
        # CheckViolation 이 트랜잭션을 끊으므로 매 회 새로 만든다(롤백이 문서까지 지운다).
        pid = _page(conn, "Blank Test")
        with pytest.raises(psycopg.errors.CheckViolation):
            x(conn, RECORD_SQL, blank, pid, "enwiki")
        conn.rollback()


def test_제목만_있고_조회시각이_없으면_거부된다(conn):
    pid = _page(conn, "Unchecked But Titled")
    with pytest.raises(psycopg.errors.CheckViolation):
        x(conn, "UPDATE wiki_page SET title_ko = %s WHERE id = %s", "제목", pid)


def test_영문_제목은_그대로다(conn):
    """🔴 이 변경의 금지선. title 은 자연키이자 링크·조인 키다."""
    pid = _page(conn, "Hurricane Milton")
    x(conn, RECORD_SQL, "허리케인 밀턴", pid, "enwiki")

    assert q(conn, "SELECT title FROM wiki_page WHERE id = %s", pid)[0][0] == "Hurricane Milton"


def test_펄스맵_노드_질의가_영문과_한국어를_함께_준다(conn):
    """`PulseMapRepository.findNodes`. ko 없는 노드는 NULL 로 내려가 화면이 영문으로 떨어진다."""
    cid = _cluster(conn)
    root, neighbour = _page(conn, "Hurricane Milton"), _page(conn, "Generac")
    _member(conn, cid, root, is_seed=True, weight=2.0)
    _member(conn, cid, neighbour, weight=1.0)
    x(conn, RECORD_SQL, "허리케인 밀턴", root, "enwiki")
    x(conn, RECORD_SQL, None, neighbour, "enwiki")

    rows = q(conn, """
        SELECT p.title, p.title_ko
          FROM cluster_member cm
          JOIN issue_cluster c ON c.id = cm.cluster_id
          JOIN wiki_page p ON p.id = cm.page_id
         WHERE c.snapshot_ts = %s AND c.source = 'live' AND c.status <> 'DISCARDED'
         ORDER BY c.id ASC, cm.is_seed DESC, cm.weight DESC
        """, SNAPSHOT)

    # is_seed DESC 라 0번이 root/lead — 클러스터 표시 제목이 여기서 나온다.
    assert rows == [("Hurricane Milton", "허리케인 밀턴"), ("Generac", None)]


def test_이슈_상세_멤버_질의가_영문과_한국어를_함께_준다(conn):
    """`IssueQueryRepository.findMembers`. 펄스맵과 같은 어휘여야 두 화면이 안 갈린다."""
    cid = _cluster(conn)
    pid = _page(conn, "Strait of Hormuz")
    _member(conn, cid, pid, is_seed=True)
    x(conn, RECORD_SQL, "호르무즈 해협", pid, "enwiki")

    rows = q(conn, """
        SELECT p.wiki, p.title, p.title_ko
          FROM cluster_member cm
          JOIN wiki_page p ON p.id = cm.page_id
         WHERE cm.cluster_id = %s
         ORDER BY cm.is_seed DESC, cm.weight DESC
        """, cid)

    assert rows == [("enwiki", "Strait of Hormuz", "호르무즈 해협")]
