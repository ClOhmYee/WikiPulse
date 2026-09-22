"""스냅샷을 PostgreSQL 에 저장 (WP-75).

psycopg 연결을 받아 한 스냅샷(build_snapshot 출력)을 issue_cluster·cluster_member·
cluster_edge·cluster_snapshot 에 쓴다.

멱등하다 — 같은 (source, snapshot_ts) 를 다시 저장하면 기존 것을 지우고 새로 넣는다.
리플레이 배치가 과거 시점을 재계산해도 중복이 쌓이지 않는다(재계산 호환). cluster_count=0
인 스냅샷도 cluster_snapshot 에 등록해 "완료된 빈 스냅샷"을 미저장 시점과 구분한다.

한 스냅샷 저장은 한 트랜잭션이다 — 부분 저장이 남으면 화면이 깨진 그래프를 그린다.

🔴 **재저장은 downstream 을 CASCADE 로 함께 지운다** (WP-161 에서 가드 추가).
    `DELETE FROM issue_cluster` 하나가 `issue_report`·`cluster_stock`·
    `cluster_org_mention`·`issue_summary_attempt`·`comment_thread` 까지 끌고 간다.
    그 데이터는 GATEWAY 크레딧과 GDELT 호출로 만든 것이라 **다시 만들려면 돈과 시간이 든다.**
    그래서 downstream 이 하나라도 있으면 기본은 **중단**이고, 호출자가 명시적으로
    `allow_downstream_delete=True` 를 줘야 진행한다. `--dry-run` 은 삭제 예정 규모만
    세고 아무것도 쓰지 않는다.
"""

from __future__ import annotations

from .snapshot import Cluster, Snapshot

#: `issue_cluster` 삭제가 CASCADE 로 함께 지우는 테이블 중 **재생성에 비용이 드는 것**.
#: V1·V2·develop V11 의 FK 를 전수 확인해 골랐다.
#: ⚠️ `notification` 은 ON DELETE SET NULL 이라 지워지지 않는다 — 넣지 않는다.
#: ⚠️ `cluster_member`·`cluster_edge` 도 CASCADE 지만 **이 스냅샷의 산출물 자체**라
#:    바로 다시 만들어진다. 가드가 지키는 것은 파이프라인이 되돌려 주지 않는 것들이다.
CASCADE_TABLES = (
    "issue_report",
    "cluster_stock",
    "cluster_org_mention",
    "issue_summary_attempt",
    "comment_thread",
)


class DownstreamDataWouldBeDeleted(RuntimeError):
    """재저장이 downstream 을 지우려 한다. 명시적 허용 없이는 진행하지 않는다."""

    def __init__(self, snapshot_ts, source, counts: dict[str, int]):
        self.snapshot_ts = snapshot_ts
        self.source = source
        self.counts = counts
        detail = ", ".join(f"{t} {n:,}" for t, n in sorted(counts.items()) if n)
        super().__init__(
            f"{source} {snapshot_ts.isoformat()} 재저장이 downstream 을 지운다: {detail}. "
            "GATEWAY·GDELT 호출로 만든 데이터라 재생성에 비용이 든다. 지워도 된다면 "
            "allow_downstream_delete=True (CLI: --allow-downstream-delete) 를 명시한다."
        )


def _existing_tables(cur, names) -> list[str]:
    """이름 중 실제로 존재하는 테이블만. 마이그레이션 단계가 다른 DB 에서도 돌아야 한다.

    ⚠️ 없는 테이블을 조회하면 트랜잭션이 통째로 죽는다 — 가드가 저장을 막는 게 아니라
    저장 자체를 깨뜨린다. 그래서 먼저 카탈로그를 본다. (`issue_summary_attempt` 는
    develop V11 이고, 그 이전 DB 에는 없다.)
    """
    cur.execute(
        "SELECT table_name FROM information_schema.tables"
        " WHERE table_schema = current_schema() AND table_name = ANY(%s)",
        (list(names),))
    return sorted(row[0] for row in cur.fetchall())


def downstream_counts(conn, snapshot_ts, source) -> dict[str, int]:
    """이 (source, snapshot_ts) 를 지울 때 CASCADE 로 함께 사라질 행 수.

    0 인 테이블도 키로 돌려준다 — "조회했고 없었다" 와 "조회조차 안 했다" 는 다르다.
    """
    counts: dict[str, int] = {}
    with conn.cursor() as cur:
        for table in _existing_tables(cur, CASCADE_TABLES):
            cur.execute(
                f"SELECT count(*) FROM {table} d"        # noqa: S608 — 카탈로그에서 온 이름
                " JOIN issue_cluster c ON c.id = d.cluster_id"
                " WHERE c.snapshot_ts = %s AND c.source = %s",
                (snapshot_ts, source))
            counts[table] = cur.fetchone()[0]
    return counts


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


def persist_snapshot(conn, snapshot: Snapshot, *,
                     allow_downstream_delete: bool = False) -> None:
    """한 스냅샷을 통째로 저장한다. 멱등·트랜잭션.

    호출자는 conn.commit() 을 책임진다 — 여러 스냅샷을 한 배치로 커밋하거나
    테스트에서 롤백할 수 있게 여기서는 커밋하지 않는다.

    🔴 **downstream 이 있으면 기본은 중단이다** (WP-161). 기존 스냅샷을 지우는
    순간 그 클러스터에 붙은 요약·종목 후보·GDELT 기관명·토론이 CASCADE 로 함께
    사라진다. `allow_downstream_delete=True` 로 명시해야 진행한다.
    """
    counts = downstream_counts(conn, snapshot.snapshot_ts, snapshot.source)
    if not allow_downstream_delete and any(counts.values()):
        raise DownstreamDataWouldBeDeleted(
            snapshot.snapshot_ts, snapshot.source, counts)
    with conn.cursor() as cur:
        _delete_existing(cur, snapshot.snapshot_ts, snapshot.source)
        for cluster in snapshot.clusters:
            cluster_id = _insert_cluster(cur, snapshot, cluster)
            _insert_members(cur, cluster_id, cluster)
            _insert_edges(cur, cluster_id, cluster)
        _register_snapshot(cur, snapshot)
