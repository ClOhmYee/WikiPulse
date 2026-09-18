"""스냅샷 저장 왕복 검증 (WP-75). 진짜 PostgreSQL(pgserver)에 쓴다.

build_snapshot 출력을 persist_snapshot 으로 저장하고 다시 읽어, 스키마 제약을
통과하고 계약대로 저장되는지 본다. 멱등(재계산 호환)도 확인한다.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

pytest.importorskip("psycopg")

from cluster.snapshot import Neighbor, Seed, WikidataRelation, build_snapshot
from cluster.writer import persist_snapshot

UTC = timezone.utc


def _dt(y, m, d, h=0):
    return datetime(y, m, d, h, tzinfo=UTC)


def _page(conn, title: str) -> int:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO wiki_page (wiki, title) VALUES ('enwiki', %s) RETURNING id",
                    (title,))
        return cur.fetchone()[0]


def _one(conn, sql, *args):
    with conn.cursor() as cur:
        cur.execute(sql, args or None)
        return cur.fetchone()


def _all(conn, sql, *args):
    with conn.cursor() as cur:
        cur.execute(sql, args or None)
        return cur.fetchall()


@pytest.fixture
def hormuz(conn):
    """§11 Hormuz 축약: 씨드 + 사건 이웃(창 안) + 배경 이웃(창 밖)."""
    seed_id = _page(conn, "Strait of Hormuz")
    event_id = _page(conn, "2025 Iran threat of Strait of Hormuz closure")
    bg_id = _page(conn, "Choke point")

    seed = Seed(
        page_id=seed_id, wiki="enwiki", title="Strait of Hormuz",
        event_date=date(2025, 6, 12), spike_score=9.7,
        window_start=_dt(2025, 6, 12), window_end=_dt(2025, 6, 12, 4),
        edit_count=47, views=91000, completeness="complete",
    )
    neighbors = {seed_id: [
        Neighbor(page_id=event_id, wiki="enwiki",
                 title="2025 Iran threat of Strait of Hormuz closure",
                 clickstream_n=383, clickstream_month="2025-05", created_at=datetime(2025, 6, 23, tzinfo=UTC)),
        Neighbor(page_id=bg_id, wiki="enwiki", title="Choke point",
                 clickstream_n=11778, clickstream_month="2025-05", created_at=datetime(2009, 1, 1, tzinfo=UTC)),
    ]}
    wikidata = {seed_id: [
        WikidataRelation(target_page_id=event_id, label="P361 부분",
                         observed_at=_dt(2026, 9, 11)),
    ]}
    return seed_id, event_id, bg_id, seed, neighbors, wikidata


def test_스냅샷_저장_왕복(conn, hormuz):
    seed_id, event_id, bg_id, seed, neighbors, wikidata = hormuz
    snap = build_snapshot(_dt(2025, 6, 12, 5), "live", [seed], neighbors, wikidata)
    persist_snapshot(conn, snap)

    # 클러스터 한 개, 계약 필드
    row = _one(conn,
               "SELECT issue_key, hot, category, status, pulse_score, first_detected_at "
               "FROM issue_cluster WHERE source = 'live'")
    assert row[0] == "live:enwiki:Strait of Hormuz"
    assert row[1] is True                       # spike 9.7 >= HOT 임계
    assert row[2] == "other"
    assert row[3] == "DETECTED"
    assert row[4] == 9.7

    cid = _one(conn, "SELECT id FROM issue_cluster WHERE source = 'live'")[0]

    # 멤버: 루트 씨드 + 사건 이웃(추가 씨드)만. 배경 문서는 창 밖이라 빠진다.
    members = _all(conn,
                   "SELECT page_id, is_seed, weight, size_score, completeness "
                   "FROM cluster_member WHERE cluster_id = %s ORDER BY page_id", cid)
    ids = {m[0] for m in members}
    assert ids == {seed_id, event_id}
    assert bg_id not in ids
    # 🔴 둘 다 `is_seed=true` 다 (명세 v0.3 §3.2 4번, -115). 루트 씨드와 추가 씨드는
    #    `is_seed` 로 갈리지 않고 지표 유무로 갈린다 — `is_seed=false` 자리는 -77 몫이다.
    assert all(m[1] is True for m in members)
    seed_row = next(m for m in members if m[0] == seed_id)
    assert seed_row[3] is not None and 0 < seed_row[3] < 1      # size_score 0~1
    nb_row = next(m for m in members if m[0] == event_id)
    assert nb_row[2] == 383.0                    # weight = clickstream n
    assert nb_row[3] is None                     # 추가 씨드는 급증 점수가 없다
    assert nb_row[4] == "unavailable"

    # 간선: clickstream(방향·월) + wikidata(점선·관측시각)
    edges = _all(conn,
                 "SELECT kind, directed, evidence_month, evidence_observed_at "
                 "FROM cluster_edge WHERE cluster_id = %s ORDER BY kind", cid)
    kinds = {e[0] for e in edges}
    assert kinds == {"clickstream", "wikidata"}
    cs = next(e for e in edges if e[0] == "clickstream")
    assert cs[1] is True and cs[2] == "2025-05"
    wd = next(e for e in edges if e[0] == "wikidata")
    assert wd[1] is False and wd[3] is not None

    # 스냅샷 레지스트리
    snap_row = _one(conn,
                    "SELECT cluster_count, score_version, new_window_hours "
                    "FROM cluster_snapshot WHERE source = 'live'")
    assert snap_row == (1, "v1", 24.0)


def test_재계산은_멱등이다(conn, hormuz):
    """같은 (source, snapshot_ts) 를 두 번 저장해도 중복이 안 쌓인다(리플레이 호환)."""
    _, _, _, seed, neighbors, wikidata = hormuz
    snap = build_snapshot(_dt(2025, 6, 12, 5), "replay", [seed], neighbors, wikidata)
    persist_snapshot(conn, snap)
    persist_snapshot(conn, snap)                 # 재계산

    assert _one(conn, "SELECT count(*) FROM issue_cluster WHERE source = 'replay'")[0] == 1
    assert _one(conn, "SELECT count(*) FROM cluster_snapshot WHERE source = 'replay'")[0] == 1
    # 멤버 2, 간선 2 (중복 없음)
    assert _one(conn, "SELECT count(*) FROM cluster_member")[0] == 2
    assert _one(conn, "SELECT count(*) FROM cluster_edge")[0] == 2


def test_빈_스냅샷도_완료로_등록된다(conn):
    """클러스터 0개여도 cluster_snapshot 에 남아 미저장 시점과 구분된다(계약)."""
    snap = build_snapshot(_dt(2025, 6, 20), "live", [], {})
    persist_snapshot(conn, snap)
    row = _one(conn,
               "SELECT cluster_count FROM cluster_snapshot "
               "WHERE source = 'live' AND snapshot_ts = %s", _dt(2025, 6, 20))
    assert row == (0,)
    assert _one(conn, "SELECT count(*) FROM issue_cluster")[0] == 0


def test_재계산이_이전_클러스터를_지운다(conn, hormuz):
    """이웃이 줄어든 재계산이 예전 멤버를 남기지 않는다."""
    _, _, _, seed, neighbors, wikidata = hormuz
    full = build_snapshot(_dt(2025, 6, 12, 5), "replay", [seed], neighbors, wikidata)
    persist_snapshot(conn, full)
    # 이웃·관계 없이 재계산 — 씨드만 남아야 한다
    shrunk = build_snapshot(_dt(2025, 6, 12, 5), "replay", [seed], {})
    persist_snapshot(conn, shrunk)
    assert _one(conn, "SELECT count(*) FROM cluster_member")[0] == 1
    assert _one(conn, "SELECT count(*) FROM cluster_edge")[0] == 0
