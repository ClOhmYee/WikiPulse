"""Clickstream 이웃 → 추가 씨드 멤버 → cluster_edge 관통 (WP-115).

진짜 PostgreSQL(pgserver)에 쓴다. `test_driver_neighbors.py` 는 게이트·월 선택까지만
보고, "실제로 `is_seed=true` 추가 씨드 행과 `cluster_edge` 행이 저장된다"·"두 번 돌려도 안
늘어난다"·"replay 가 live 를 안 건드린다" 는 실 DB 가 있어야 확인된다.

conftest.py 가 db/migrations 전체를 올린 커넥션을 준다. 테스트마다 롤백한다.
"""

from __future__ import annotations

import gzip
import json
from datetime import date, datetime, timedelta, timezone

import pytest

pytest.importorskip("psycopg")

from batch.page_creation import write_index
from cluster.driver import MonthlyNeighborSource, load_pages_by_title, run

UTC = timezone.utc

#: Milton 급증 한 시점. 2024-10-06 19:00 윈도우 → detected_at 20:00.
W1 = datetime(2024, 10, 6, 19, tzinfo=UTC)
SNAP1 = W1 + timedelta(hours=1)

SEED_TITLE = "Hurricane Milton"
#: 사건 직후 생긴 문서. 생성일 창을 통과해야 한다.
NEW_NEIGHBOR = "Hurricane Milton tornado outbreak"
#: 이동량은 훨씬 큰데 오래된 배경 문서. 창 밖이라 탈락해야 한다 (§11).
OLD_NEIGHBOR = "Tropical cyclone"
#: 사건 전(직전 월)에 이미 생긴 같은 사건 문서. `previous` 규칙에서 붙는 모양이다.
SEPT_NEIGHBOR = "Hurricane Helene"


def _page(conn, title: str, wiki: str = "enwiki") -> int:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO wiki_page (wiki, title) VALUES (%s, %s) RETURNING id",
                    (wiki, title))
        return cur.fetchone()[0]


def _spike(conn, page_id: int, window_start: datetime, *, source="replay",
           edit_count=10, spike_score=26.4575) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO spike (source, page_id, detected_at, window_start, edit_count,
                               edit_z, view_ratio, spike_score)
            VALUES (%s, %s, %s, %s, %s, NULL, NULL, %s)
            """,
            (source, page_id, window_start + timedelta(hours=1), window_start,
             edit_count, spike_score),
        )


def _all(conn, sql, *args):
    with conn.cursor() as cur:
        cur.execute(sql, args or None)
        return cur.fetchall()


def _count(conn, table: str) -> int:
    return _all(conn, f"SELECT count(*) FROM {table}")[0][0]


@pytest.fixture
def neighbor_source(tmp_path):
    """실제 적재본 형태 그대로 — `clickstream_ingest` 출력과 같은 JSONL.gz shard.

    근거 월은 **직전 완료 월(2024-09)** 이다. 스냅샷 당월(2024-10) 덤프는 월이 끝나야
    나오므로 운영 당시에는 없던 근거다 — `select_completed_month` 가 고르지 않고
    `snapshot._is_completed_clickstream_month` 가 한 번 더 막는다(명세 v0.3 §3.2 4번).

    세 이웃이 각각 다른 관문을 본다:
      SEPT_NEIGHBOR  생성 2024-09-20 — 스냅샷 이전 · 창 안  -> 추가 씨드로 들어온다
      OLD_NEIGHBOR   생성 2003-04-01 — 창 밖               -> 이동량이 21배여도 탈락
      NEW_NEIGHBOR   생성 2024-10-09 — **스냅샷 이후**      -> 시점 상한에 걸려 탈락
    """
    directory = tmp_path / "clickstream" / "enwiki" / "2024-09"
    directory.mkdir(parents=True)
    with gzip.open(directory / "part-00000.jsonl.gz", "wt", encoding="utf-8") as handle:
        for curr, n in ((SEPT_NEIGHBOR, 4200), (OLD_NEIGHBOR, 90000), (NEW_NEIGHBOR, 5000)):
            print(json.dumps({"prev": SEED_TITLE, "curr": curr, "n": n}), file=handle)
    (directory / "_manifest.json").write_text(
        json.dumps({"wiki": "enwiki", "month": "2024-09",
                    "shards": ["part-00000.jsonl.gz"]}), encoding="utf-8")
    write_index({SEPT_NEIGHBOR: datetime(2024, 9, 20, 7, 30, tzinfo=UTC),
                 OLD_NEIGHBOR: datetime(2003, 4, 1, tzinfo=UTC),
                 NEW_NEIGHBOR: datetime(2024, 10, 9, tzinfo=UTC)},
                tmp_path / "creation", shard_records=100)
    return MonthlyNeighborSource(tmp_path / "clickstream", tmp_path / "creation")


@pytest.fixture
def milton(conn):
    page_id = _page(conn, SEED_TITLE)
    _spike(conn, page_id, W1)
    return page_id


# --- 제목 → page_id ----------------------------------------------------------

def test_있는_문서는_그대로_해석한다(conn):
    page_id = _page(conn, "Iran")
    assert load_pages_by_title(conn, "enwiki", ["Iran"]) == {"Iran": page_id}


def test_없는_문서를_등록한다(conn):
    """🔴 등록을 안 하면 사건 직후 생긴 진짜 멤버가 조용히 전부 사라진다."""
    before = _count(conn, "wiki_page")
    found = load_pages_by_title(conn, "enwiki", [NEW_NEIGHBOR])
    assert set(found) == {NEW_NEIGHBOR}
    assert _count(conn, "wiki_page") == before + 1


def test_등록하지_않는_모드도_있다(conn):
    assert load_pages_by_title(
        conn, "enwiki", ["Nowhere"], register_missing=False) == {}
    assert _count(conn, "wiki_page") == 0


def test_같은_제목을_두_번_줘도_행이_안_는다(conn):
    load_pages_by_title(conn, "enwiki", [NEW_NEIGHBOR])
    first = _count(conn, "wiki_page")
    load_pages_by_title(conn, "enwiki", [NEW_NEIGHBOR])
    assert _count(conn, "wiki_page") == first


def test_다른_wiki_는_다른_문서다(conn):
    en = load_pages_by_title(conn, "enwiki", ["Iran"])["Iran"]
    ko = load_pages_by_title(conn, "kowiki", ["Iran"])["Iran"]
    assert en != ko


def test_빈_입력은_DB_를_안_친다(conn):
    assert load_pages_by_title(conn, "enwiki", []) == {}


# --- 관통 --------------------------------------------------------------------

def test_추가_씨드_멤버와_간선이_저장된다(conn, milton, neighbor_source):
    run(conn, "replay", snapshot_times=[SNAP1], neighbor_source=neighbor_source)

    # 🔴 `is_seed DESC` 로는 못 가른다 — 루트 씨드와 추가 씨드가 둘 다 true 다.
    members = _all(conn,
                   "SELECT p.title, m.is_seed, m.weight, m.completeness "
                   "FROM cluster_member m JOIN wiki_page p ON p.id = m.page_id "
                   "ORDER BY p.title")
    # 추가 씨드는 시점 지표를 안 재고 관계로만 딸려온다. weight 는 Clickstream 이동량.
    # `is_seed=true` 는 "사건 때문에 새로 생긴 문서" 라는 뜻이지 지표가 있다는 뜻이 아니다.
    assert members == [
        (SEPT_NEIGHBOR, True, 4200.0, "unavailable"),
        (SEED_TITLE, True, 1.0, "pending"),
    ]

    edges = _all(conn,
                 "SELECT kind, directed, weight, evidence_label, evidence_month "
                 "FROM cluster_edge")
    assert edges == [("clickstream", True, 4200.0, "Clickstream 2024-09", "2024-09")]


def test_스냅샷_이후_생성_문서는_안_들어온다(conn, milton, neighbor_source):
    """시점 상한(WP-118). 창 안이어도 `생성 시각 > snapshot_ts` 면 제외한다 —
    과거 지도에 나중에 생긴 문서를 소급하지 않는다."""
    run(conn, "replay", snapshot_times=[SNAP1], neighbor_source=neighbor_source)
    titles = {row[0] for row in _all(
        conn, "SELECT p.title FROM cluster_member m JOIN wiki_page p ON p.id = m.page_id")}
    assert NEW_NEIGHBOR not in titles


def test_이동량이_커도_창_밖이면_안_들어온다(conn, milton, neighbor_source):
    """n=90,000 짜리 배경 문서가 n=4,200 짜리 사건 문서보다 21배 크다 — §11 그대로."""
    run(conn, "replay", snapshot_times=[SNAP1], neighbor_source=neighbor_source)
    titles = {row[0] for row in _all(
        conn, "SELECT p.title FROM cluster_member m JOIN wiki_page p ON p.id = m.page_id")}
    assert OLD_NEIGHBOR not in titles


def test_같은_입력을_다시_돌려도_안_는다(conn, milton, neighbor_source):
    run(conn, "replay", snapshot_times=[SNAP1], neighbor_source=neighbor_source)
    before = (_count(conn, "issue_cluster"), _count(conn, "cluster_member"),
              _count(conn, "cluster_edge"), _count(conn, "cluster_snapshot"),
              _count(conn, "wiki_page"))

    run(conn, "replay", snapshot_times=[SNAP1], neighbor_source=neighbor_source)
    after = (_count(conn, "issue_cluster"), _count(conn, "cluster_member"),
             _count(conn, "cluster_edge"), _count(conn, "cluster_snapshot"),
             _count(conn, "wiki_page"))
    assert before == after


def test_replay_실행이_live_산출물을_안_건드린다(conn, neighbor_source):
    """🔴 -102 계약. 두 출처가 같은 detected_at 을 각각 가질 수 있다."""
    page_id = _page(conn, SEED_TITLE)
    _spike(conn, page_id, W1, source="replay")
    _spike(conn, page_id, W1, source="live")

    run(conn, "live", snapshot_times=[SNAP1], neighbor_source=neighbor_source)
    live_before = _count(conn, "issue_cluster")

    run(conn, "replay", snapshot_times=[SNAP1], neighbor_source=neighbor_source)

    sources = dict(_all(conn,
                        "SELECT source, count(*) FROM issue_cluster GROUP BY source"))
    assert sources == {"live": live_before, "replay": 1}
    # issue_key 가 출처를 포함해 시점 간 연결도 안 섞인다.
    keys = {row[0] for row in _all(conn, "SELECT issue_key FROM issue_cluster")}
    assert keys == {f"live:enwiki:{SEED_TITLE}", f"replay:enwiki:{SEED_TITLE}"}


def test_이웃을_안_주면_씨드_단독이다(conn, milton):
    """기존 운영(-109)이 이 변경으로 갑자기 달라지면 안 된다."""
    run(conn, "replay", snapshot_times=[SNAP1])
    assert _count(conn, "cluster_member") == 1
    assert _count(conn, "cluster_edge") == 0
