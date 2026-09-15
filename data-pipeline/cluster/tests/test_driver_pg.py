"""spike → 스냅샷 → PostgreSQL 왕복 (WP-99). 진짜 PostgreSQL(pgserver)에 쓴다.

`test_driver_seeds.py` 의 대역 검사는 매핑 계약까지만 본다. "실제 spike 행을 읽어
issue_cluster 까지 들어간다"·"두 번 돌려도 안 늘어난다"·"백엔드 질의가 읽는 형태다" 는
실 DB 가 있어야 확인된다 — 그래서 파일을 나눴다(`test_writer.py` 와 같은 이유).

conftest.py 가 db/migrations 전체를 올린 커넥션을 준다. 테스트마다 롤백한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("psycopg")

from cluster.driver import load_snapshot_times, run

UTC = timezone.utc
W1 = datetime(2024, 10, 6, 19, tzinfo=UTC)
W2 = datetime(2024, 10, 7, 13, tzinfo=UTC)


def _page(conn, title: str, wiki: str = "enwiki") -> int:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO wiki_page (wiki, title) VALUES (%s, %s) RETURNING id",
                    (wiki, title))
        return cur.fetchone()[0]


def _spike(conn, page_id: int, window_start: datetime, *, edit_count=10,
           edit_z=None, view_ratio=None, spike_score=26.4575) -> None:
    """WP-94 런타임이 쓰는 형태 그대로. detected_at = 윈도우 끝."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO spike (page_id, detected_at, window_start, edit_count,
                               edit_z, view_ratio, spike_score)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (page_id, window_start + timedelta(hours=1), window_start,
             edit_count, edit_z, view_ratio, spike_score),
        )


def _all(conn, sql, *args):
    with conn.cursor() as cur:
        cur.execute(sql, args or None)
        return cur.fetchall()


def _one(conn, sql, *args):
    rows = _all(conn, sql, *args)
    return rows[0] if rows else None


@pytest.fixture
def milton(conn):
    """Milton 한 문서에 두 시점의 급증. 실제 -94 산출물과 같은 형태."""
    page_id = _page(conn, "Hurricane Milton")
    _spike(conn, page_id, W1, edit_count=10, spike_score=26.4575)          # 신규 문서 경로
    _spike(conn, page_id, W2, edit_count=23, edit_z=3.767, spike_score=1.562)   # z 경로
    return page_id


# ---------------------------------------------------------------- 관통

def test_spike가_issue_cluster까지_관통한다(conn, milton):
    times = load_snapshot_times(conn)
    assert times == [W1 + timedelta(hours=1), W2 + timedelta(hours=1)]   # 오름차순

    run(conn, "replay", snapshot_times=times)

    clusters = _all(conn,
                    "SELECT snapshot_ts, source, issue_key, pulse_score, status, "
                    "category, hot, first_detected_at FROM issue_cluster "
                    "ORDER BY snapshot_ts")
    assert len(clusters) == 2
    assert [c[1] for c in clusters] == ["replay", "replay"]
    assert {c[2] for c in clusters} == {"replay:enwiki:Hurricane Milton"}
    assert [c[4] for c in clusters] == ["DETECTED", "DETECTED"]
    # 두 시점 모두 최초 감지는 가장 이른 시각을 가리킨다.
    assert {c[7] for c in clusters} == {W1 + timedelta(hours=1)}


def test_멤버는_씨드_한_건이고_간선은_없다(conn, milton):
    run(conn, "replay", snapshot_times=load_snapshot_times(conn))

    members = _all(conn,
                   "SELECT cm.page_id, cm.is_seed, cm.weight, cm.completeness, "
                   "cm.edit_count, cm.spike_score, cm.size_score, "
                   "cm.window_start, cm.window_end "
                   "FROM cluster_member cm JOIN issue_cluster c ON c.id = cm.cluster_id "
                   "ORDER BY c.snapshot_ts")
    assert len(members) == 2
    assert all(m[0] == milton and m[1] is True and m[2] == 1.0 for m in members)
    assert members[0][7] == W1 and members[0][8] == W1 + timedelta(hours=1)

    # Clickstream 적재본이 없으니 간선도 없다 — 억지로 만들지 않는다.
    assert _one(conn, "SELECT count(*) FROM cluster_edge")[0] == 0


def test_cluster_snapshot이_시점마다_등록된다(conn, milton):
    run(conn, "replay", snapshot_times=load_snapshot_times(conn))
    rows = _all(conn, "SELECT snapshot_ts, source, cluster_count, score_version, "
                      "new_window_hours FROM cluster_snapshot ORDER BY snapshot_ts")
    assert len(rows) == 2
    assert [r[2] for r in rows] == [1, 1]
    assert {r[1] for r in rows} == {"replay"}
    assert all(r[3] for r in rows)          # score_version 이 비어 있지 않다


# ---------------------------------------------------------------- 멱등

def test_두_번_돌려도_안_늘어난다(conn, milton):
    times = load_snapshot_times(conn)
    run(conn, "replay", snapshot_times=times)
    before = (_one(conn, "SELECT count(*) FROM issue_cluster")[0],
              _one(conn, "SELECT count(*) FROM cluster_member")[0],
              _one(conn, "SELECT count(*) FROM cluster_snapshot")[0])
    assert before == (2, 2, 2)

    run(conn, "replay", snapshot_times=times)          # 재실행
    after = (_one(conn, "SELECT count(*) FROM issue_cluster")[0],
             _one(conn, "SELECT count(*) FROM cluster_member")[0],
             _one(conn, "SELECT count(*) FROM cluster_snapshot")[0])
    assert after == before                              # writer 의 (source, ts) 단위 멱등


def test_재실행해도_issue_key와_최초감지가_안_변한다(conn, milton):
    times = load_snapshot_times(conn)
    run(conn, "replay", snapshot_times=times)
    first = _all(conn, "SELECT issue_key, first_detected_at FROM issue_cluster "
                       "ORDER BY snapshot_ts")
    run(conn, "replay", snapshot_times=times)
    assert _all(conn, "SELECT issue_key, first_detected_at FROM issue_cluster "
                      "ORDER BY snapshot_ts") == first


def test_dry_run은_아무것도_안_쓴다(conn, milton):
    run(conn, "replay", snapshot_times=load_snapshot_times(conn), dry_run=True)
    assert _one(conn, "SELECT count(*) FROM issue_cluster")[0] == 0
    assert _one(conn, "SELECT count(*) FROM cluster_snapshot")[0] == 0


# ---------------------------------------------------------------- 백엔드가 읽는 형태

def test_백엔드_카드_질의가_이_행을_읽는다(conn, milton):
    """IssueClusterRepository.findCards 와 같은 조건으로 뽑아본다(백엔드 무수정 확인)."""
    times = load_snapshot_times(conn)
    run(conn, "replay", snapshot_times=times)

    row = _one(conn, """
        SELECT c.id, c.label, c.pulse_score, c.status, c.source, c.snapshot_ts,
               (SELECT count(*) FROM cluster_member cm WHERE cm.cluster_id = c.id),
               (SELECT count(*) FROM cluster_stock cs
                 WHERE cs.cluster_id = c.id AND cs.verified)
          FROM issue_cluster c
         WHERE c.snapshot_ts = %s AND c.status IN ('DETECTED','VERIFYING','CONFIRMED')
           AND c.source = 'replay'
         ORDER BY c.pulse_score DESC, c.id ASC
        """, times[0])
    assert row is not None
    assert row[3] == "DETECTED" and row[4] == "replay"
    assert row[6] == 1        # memberCount
    assert row[7] == 0        # stockCount — LLM 검증(WP-68) 전이라 0이 정상


def test_replay_spike가_live로_저장되지_않는다(conn, milton):
    """🔴 spike 에 provenance 컬럼이 없다 — 거짓 라벨링을 실 DB 에서도 막는다."""
    times = load_snapshot_times(conn)
    with pytest.raises(ValueError, match="provenance|replay"):
        run(conn, "live", snapshot_times=times)

    assert _one(conn, "SELECT count(*) FROM issue_cluster WHERE source = 'live'")[0] == 0
    assert _one(conn, "SELECT count(*) FROM cluster_snapshot WHERE source = 'live'")[0] == 0

    run(conn, "replay", snapshot_times=times)
    assert _one(conn, "SELECT count(*) FROM issue_cluster WHERE source = 'live'")[0] == 0
    assert _one(conn, "SELECT count(*) FROM issue_cluster WHERE source = 'replay'")[0] == 2


def test_빈_시점도_완료로_등록된다(conn):
    """씨드가 없는 시점을 명시하면 cluster_count=0 스냅샷이 남는다."""
    ts = datetime(2024, 10, 9, 5, tzinfo=UTC)
    run(conn, "replay", snapshot_times=[ts])
    assert _one(conn, "SELECT cluster_count FROM cluster_snapshot "
                      "WHERE snapshot_ts = %s AND source = 'replay'", ts)[0] == 0
    assert _one(conn, "SELECT count(*) FROM issue_cluster")[0] == 0
