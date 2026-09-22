"""CORE 정본 경로 DB 왕복 (WP-186). 진짜 PostgreSQL(pgserver).

`spike` + `page_asof_links`(V11) → `cluster.driver.run` → `issue_cluster` 까지가
실제 스키마·제약을 통과하는지, 두 번 돌려도 안 늘어나는지 본다.

`test_snapshot_core.py` 의 순수 검사는 계약 변환까지만 본다. "V11 캐시를 실제로 읽는가"·
"멱등한가"·"백엔드 질의가 읽는 형태인가" 는 실 DB 가 있어야 확인된다.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("psycopg")

from cluster.driver import load_root_links, load_seeds_from_spike, run

UTC = timezone.utc
W1 = datetime(2026, 8, 25, 19, tzinfo=UTC)
SNAP1 = W1 + timedelta(hours=1)


def _page(conn, title, wiki="enwiki") -> int:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO wiki_page (wiki, title) VALUES (%s, %s) RETURNING id",
                    (wiki, title))
        return cur.fetchone()[0]


def _spike(conn, page_id, *, spike_score, views, max_rev_id,
           window_start=W1, source="replay") -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO spike (source, page_id, detected_at, window_start, edit_count,
                               views, spike_score, max_rev_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (source, page_id, window_start + timedelta(hours=1), window_start,
             1, views, spike_score, max_rev_id),
        )


def _links(conn, rev_id, title, targets, *, error=None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO page_asof_links (rev_id, wiki, title, links, link_count, error)"
            " VALUES (%s, 'enwiki', %s, %s, %s, %s)",
            (rev_id, title, json.dumps(sorted(targets)), len(targets), error))


def _all(conn, sql, *args):
    with conn.cursor() as cur:
        cur.execute(sql, args or None)
        return cur.fetchall()


def _one(conn, sql, *args):
    return _all(conn, sql, *args)[0]


@pytest.fixture
def dolly(conn):
    """Dolly 축소판 — 3 root 가 한 사건, 1 root 는 무관."""
    ids = {}
    spec = [
        ("Dolly Parton", 9.0, 50_000, 9001, ["Dollywood", "Stella Parton"]),
        ("Dollywood", 4.0, 17_000, 9002, []),
        ("Stella Parton", 3.0, 3_000, 9003, []),
        ("Unrelated Person", 6.0, 900, 9004, []),
    ]
    for title, score, views, rev, targets in spec:
        ids[title] = _page(conn, title)
        _spike(conn, ids[title], spike_score=score, views=views, max_rev_id=rev)
        _links(conn, rev, title, targets)
    return ids


# --- 캐시 읽기 ----------------------------------------------------------------

def test_load_root_links_reads_v11_cache(conn, dolly):
    seeds = load_seeds_from_spike(conn, SNAP1, "replay")
    links = load_root_links(conn, seeds)
    assert links[dolly["Dolly Parton"]] == {"Dollywood", "Stella Parton"}
    assert links[dolly["Dollywood"]] == set()


def test_load_root_links_skips_failed_and_missing_rows(conn):
    """실패로 기록된 행과 아예 없는 행은 둘 다 링크 없음이다 — 폴백하지 않는다."""
    failed = _page(conn, "Failed Fetch")
    absent = _page(conn, "Never Tried")
    _spike(conn, failed, spike_score=5.0, views=100, max_rev_id=8001)
    _spike(conn, absent, spike_score=5.0, views=100, max_rev_id=8002)
    _links(conn, 8001, "Failed Fetch", [], error="http 500")

    seeds = load_seeds_from_spike(conn, SNAP1, "replay")
    assert load_root_links(conn, seeds) == {}


def test_load_root_links_without_fetcher_makes_no_request(conn):
    """🔴 기본은 캐시만. 리플레이 재계산이 실수로 수만 건을 받지 않게 한다."""
    page = _page(conn, "Uncached")
    _spike(conn, page, spike_score=5.0, views=100, max_rev_id=7001)
    seeds = load_seeds_from_spike(conn, SNAP1, "replay")
    warnings = []
    assert load_root_links(conn, seeds, log=warnings.append) == {}
    assert any("캐시 미보유" in w for w in warnings)


def test_load_root_links_fetches_and_caches_when_enabled(conn):
    page = _page(conn, "Fetch Me")
    _spike(conn, page, spike_score=5.0, views=100, max_rev_id=7002)
    seeds = load_seeds_from_spike(conn, SNAP1, "replay")

    class Fetcher:
        def fetch_many(self, rev_ids, log=None):
            return {rev: ("Fetch Me", ["Somewhere Else"], None) for rev in rev_ids}

    assert load_root_links(conn, seeds, fetcher=Fetcher())[page] == {"Somewhere Else"}
    # 캐시에 남아 다음 실행은 요청 없이 같은 값을 준다.
    assert load_root_links(conn, seeds) == {page: {"Somewhere Else"}}
    assert _one(conn, "SELECT link_count FROM page_asof_links WHERE rev_id = 7002")[0] == 1


# --- 전체 왕복 ----------------------------------------------------------------

def test_core_grouping_lands_in_issue_cluster(conn, dolly):
    run(conn, "replay", snapshot_times=[SNAP1])

    rows = _all(conn,
                "SELECT label, pulse_score, hot, issue_key,"
                "       (SELECT count(*) FROM cluster_member m WHERE m.cluster_id = c.id)"
                "  FROM issue_cluster c WHERE c.source = 'replay'"
                " ORDER BY pulse_score DESC")
    assert rows == [
        ("Dolly Parton", 9.0, True, "replay:enwiki:Dolly Parton", 3),
        ("Unrelated Person", 6.0, True, "replay:enwiki:Unrelated Person", 1),
    ]
    assert _one(conn, "SELECT cluster_count FROM cluster_snapshot"
                      " WHERE source = 'replay'")[0] == 2


def test_members_are_roots_only_with_metric_windows(conn, dolly):
    """🔴 CORE 정본은 root 만 쓴다 — 모든 노드에 metric window 가 있다.

    프론트 계약(`contract.js` 의 `metric window`)이 노드마다 두 값을 요구한다.
    2026-09-22 preview 에서 non-root 멤버 때문에 5,120 클러스터가 렌더에서 탈락했다.
    """
    run(conn, "replay", snapshot_times=[SNAP1])
    rows = _all(conn,
                "SELECT is_seed, spike_score, views, window_start, window_end,"
                "       completeness FROM cluster_member")
    assert len(rows) == 4
    for is_seed, spike_score, views, start, end, completeness in rows:
        assert is_seed is True
        assert spike_score is not None and views is not None
        assert start is not None and end is not None and start < end
        assert completeness == "complete"


def test_no_edges_are_written_in_core_path(conn, dolly):
    """direct-link 근거 간선은 아직 저장하지 않는다 — `cluster_edge.kind` 가
    `clickstream|wikidata` 로 제한돼 있고, 프론트 계약 변경은 후속 MR 로 분리했다."""
    run(conn, "replay", snapshot_times=[SNAP1])
    assert _one(conn, "SELECT count(*) FROM cluster_edge")[0] == 0


def test_rerun_is_idempotent(conn, dolly):
    run(conn, "replay", snapshot_times=[SNAP1])
    before = _all(conn, "SELECT issue_key, label, pulse_score FROM issue_cluster"
                        " ORDER BY issue_key")
    run(conn, "replay", snapshot_times=[SNAP1])

    assert _one(conn, "SELECT count(*) FROM issue_cluster")[0] == 2
    assert _one(conn, "SELECT count(*) FROM cluster_member")[0] == 4
    assert _one(conn, "SELECT count(*) FROM cluster_snapshot")[0] == 1
    assert _all(conn, "SELECT issue_key, label, pulse_score FROM issue_cluster"
                      " ORDER BY issue_key") == before


def test_no_root_grouping_falls_back_to_one_cluster_per_root(conn, dolly):
    run(conn, "replay", snapshot_times=[SNAP1], root_grouping=False)
    assert _one(conn, "SELECT count(*) FROM issue_cluster")[0] == 4


def test_live_and_replay_share_the_same_contract(conn):
    """같은 코드 경로다 — 분기 없이 `max_rev_id` 앵커 하나를 쓴다."""
    for source, rev_base in (("replay", 6100), ("live", 6200)):
        a = _page(conn, f"{source} Alpha")
        b = _page(conn, f"{source} Bravo")
        _spike(conn, a, spike_score=8.0, views=900, max_rev_id=rev_base,
               source=source)
        _spike(conn, b, spike_score=2.0, views=90, max_rev_id=rev_base + 1,
               source=source)
        _links(conn, rev_base, f"{source} Alpha", [f"{source.capitalize()} Bravo"])
        _links(conn, rev_base + 1, f"{source} Bravo", [])
        run(conn, source, snapshot_times=[SNAP1])

    rows = _all(conn, "SELECT source, count(*) FROM issue_cluster GROUP BY 1 ORDER BY 1")
    assert rows == [("live", 1), ("replay", 1)]
    # 두 출처가 서로의 스냅샷에 섞이지 않는다.
    assert _one(conn, "SELECT count(*) FROM cluster_member m"
                      " JOIN issue_cluster c ON c.id = m.cluster_id"
                      " JOIN spike s ON s.page_id = m.page_id"
                      "   AND s.detected_at = c.snapshot_ts AND s.source = c.source")[0] == 4
