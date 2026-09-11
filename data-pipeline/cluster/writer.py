"""스냅샷을 PostgreSQL 에 저장 (WP-75).

psycopg 연결을 받아 한 스냅샷(build_snapshot 출력)을 issue_cluster·cluster_member·
cluster_edge·cluster_snapshot 에 쓴다.

멱등하다 — 같은 (source, snapshot_ts) 를 다시 저장하면 기존 것을 지우고 새로 넣는다.
리플레이 배치가 과거 시점을 재계산해도 중복이 쌓이지 않는다(재계산 호환). cluster_count=0
인 스냅샷도 cluster_snapshot 에 등록해 "완료된 빈 스냅샷"을 미저장 시점과 구분한다.

한 스냅샷 저장은 한 트랜잭션이다 — 부분 저장이 남으면 화면이 깨진 그래프를 그린다.
"""

from __future__ import annotations

from .snapshot import Cluster, Snapshot


def _delete_existing(cur, snapshot_ts, source) -> None:
    """이 (source, snapshot_ts) 의 기존 산출물을 지운다. 멤버·간선은 CASCADE."""
    cur.execute(
        "DELETE FROM issue_cluster WHERE snapshot_ts = %s AND source = %s",
        (snapshot_ts, source),
    )
    cur.execute(
        "DELETE FROM cluster_snapshot WHERE snapshot_ts = %s AND source = %s",
        (snapshot_ts, source),
    )


def _insert_cluster(cur, snapshot: Snapshot, cluster: Cluster) -> int:
    cur.execute(
        """
        INSERT INTO issue_cluster
            (snapshot_ts, source, label, pulse_score, status,
             issue_key, first_detected_at, hot, category)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            snapshot.snapshot_ts, snapshot.source, cluster.label,
            cluster.pulse_score, cluster.status, cluster.issue_key,
            cluster.first_detected_at, cluster.hot, cluster.category,
        ),
    )
    return cur.fetchone()[0]


def _insert_members(cur, cluster_id: int, cluster: Cluster) -> None:
    for m in cluster.members:
        cur.execute(
            """
            INSERT INTO cluster_member
                (cluster_id, page_id, weight, is_seed, edit_count, views,
                 edit_baseline, view_baseline, spike_score, size_score,
                 completeness, window_start, window_end)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                cluster_id, m.page_id, m.weight, m.is_seed, m.edit_count, m.views,
                m.edit_baseline, m.view_baseline, m.spike_score, m.size_score,
                m.completeness, m.window_start, m.window_end,
            ),
        )


def _insert_edges(cur, cluster_id: int, cluster: Cluster) -> None:
    for e in cluster.edges:
        cur.execute(
            """
            INSERT INTO cluster_edge
                (cluster_id, source_page_id, target_page_id, kind, directed,
                 weight, evidence_label, evidence_month, evidence_observed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                cluster_id, e.source_page_id, e.target_page_id, e.kind, e.directed,
                e.weight, e.evidence_label, e.evidence_month, e.evidence_observed_at,
            ),
        )


def _register_snapshot(cur, snapshot: Snapshot) -> None:
    cur.execute(
        """
        INSERT INTO cluster_snapshot
            (snapshot_ts, source, cluster_count, score_version, new_window_hours)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            snapshot.snapshot_ts, snapshot.source, snapshot.cluster_count,
            snapshot.score_version, snapshot.new_window_hours,
        ),
    )


def persist_snapshot(conn, snapshot: Snapshot) -> None:
    """한 스냅샷을 통째로 저장한다. 멱등·트랜잭션.

    호출자는 conn.commit() 을 책임진다 — 여러 스냅샷을 한 배치로 커밋하거나
    테스트에서 롤백할 수 있게 여기서는 커밋하지 않는다.
    """
    with conn.cursor() as cur:
        _delete_existing(cur, snapshot.snapshot_ts, snapshot.source)
        for cluster in snapshot.clusters:
            cluster_id = _insert_cluster(cur, snapshot, cluster)
            _insert_members(cur, cluster_id, cluster)
            _insert_edges(cur, cluster_id, cluster)
        _register_snapshot(cur, snapshot)
