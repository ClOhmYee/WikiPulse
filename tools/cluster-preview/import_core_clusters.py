"""PoC 5 CORE_ONLY 컴포넌트를 preview DB 의 서비스 스키마로 적재한다.

정본 규칙 (PoC 5, 재계산 없음 — 이 스크립트는 알고리즘을 돌리지 않는다)

    같은 snapshot
    + strict historical as-of direct Wikipedia link
    + sym focus tau=0.005
    + D2 directional bridge suppression

입력은 PoC 5 가 이미 만들어 둔 `full-1104/components.csv` 그대로다
(snapshots 1,104 / roots 22,080 / components 19,432).

🔴 5434·5435 는 열지 않는다. 대상은 5436 preview 한 곳뿐이다.
🔴 없는 값을 만들지 않는다. 아래 세 가지만 "여러 root 를 하나로 합칠 때" 유도한다.

    pulse_score        = 구성 root 들의 spike_score 최댓값
                         (singleton 이면 원래 pulse_score 와 정확히 같다 — 실측 확인)
    issue_key          = spike_score 가 가장 큰 root 의 **기존** issue_key 를 그대로 물려받는다
    first_detected_at  = 구성 root 들의 first_detected_at 최솟값

    label·category·status·source·score_version 은 baseline 값을 그대로 쓴다.
    뉴스·AI 요약·종목은 원본에 아예 없다(0행). 만들지 않는다.

멤버 구성

    seed  = 그 component 의 root 들. baseline.cluster_member 행을 컬럼째 복사한다.
    비-seed = 각 root 의 기존 clickstream 확장 멤버(spike_score IS NULL). 자기 root 가
              들어간 새 클러스터로 따라 들어간다. 같은 page 가 root 로도 있으면 root 행을 남긴다.
    cluster_edge = 기존 clickstream 간선을 새 cluster_id 로 옮긴다. 새로 만들지 않는다.

사용

    python import_core_clusters.py [--dsn ...] [--csv ...] [--target-schema public]
"""

from __future__ import annotations

import argparse
import csv
import os
from collections import defaultdict

import psycopg

DEFAULT_DSN = ""
    "PREVIEW_DSN",
    "",
)
DEFAULT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "poc5-core-components-1104.csv")


def canon(title: str) -> str:
    """`poc-simple-root-grouping/links.py:canon` 과 같은 규칙.

    components.csv 의 제목이 이 함수를 거친 값이라 DB 제목도 같은 함수를 통과시켜야
    맞물린다. 복사해 둔 이유는 PoC 디렉터리를 import 의존성으로 걸지 않기 위해서다.
    """
    t = " ".join(title.replace("_", " ").split())
    return t[:1].upper() + t[1:] if t else t


def read_components(path: str) -> dict[str, list[list[str]]]:
    out: dict[str, list[list[str]]] = defaultdict(list)
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            out[row["snapshot_ts"]].append(row["titles"].split("|"))
    return out


ROOTS_SQL = """
SELECT ic.snapshot_ts, ic.id, ic.pulse_score, ic.status, ic.source, ic.created_at,
       ic.issue_key, ic.first_detected_at, ic.hot, ic.category,
       cm.page_id, wp.title, cm.weight, cm.is_seed, cm.edit_count, cm.views,
       cm.edit_baseline, cm.view_baseline, cm.spike_score, cm.size_score,
       cm.completeness, cm.window_start, cm.window_end
  FROM baseline.issue_cluster ic
  JOIN baseline.cluster_member cm ON cm.cluster_id = ic.id AND cm.spike_score IS NOT NULL
  JOIN public.wiki_page wp        ON wp.id = cm.page_id
"""

EXTRA_SQL = """
SELECT cm.cluster_id, cm.page_id, cm.weight, cm.is_seed, cm.edit_count, cm.views,
       cm.edit_baseline, cm.view_baseline, cm.spike_score, cm.size_score,
       cm.completeness, cm.window_start, cm.window_end
  FROM baseline.cluster_member cm
 WHERE cm.spike_score IS NULL
"""

EDGES_SQL = """
SELECT cluster_id, source_page_id, target_page_id, kind, directed, weight,
       evidence_label, evidence_month, evidence_observed_at
  FROM baseline.cluster_edge
"""

MEMBER_COLS = ("weight", "is_seed", "edit_count", "views", "edit_baseline",
               "view_baseline", "spike_score", "size_score", "completeness",
               "window_start", "window_end")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=DEFAULT_DSN)
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--target-schema", default="public")
    # 기본은 root 만 담는다 — CORE_ONLY 가 실제로 내놓는 것이 root component 이기 때문이다.
    # ⚠️ 켜면 펄스맵이 통째로 안 그려진다. clickstream 확장 멤버는 window_start·window_end 가
    #    NULL 인데 프론트 계약(`contract.js` "metric window")이 노드마다 두 값을 요구한다.
    #    baseline 원본도 같은 이유로 5,120개 클러스터가 렌더 대상에서 탈락한다 — 이번 적재가
    #    만든 문제가 아니라 replay 데이터셋이 원래 그렇다.
    ap.add_argument("--keep-clickstream-members", action="store_true")
    args = ap.parse_args()
    if not args.dsn:
        ap.error("Set PREVIEW_DSN or pass --dsn; no database password is bundled.")

    if ":5434/" in args.dsn or ":5435/" in args.dsn:
        raise SystemExit("거부: 5434·5435 는 읽기 전용 원본이다. preview(5436) 로만 쓴다.")

    comps_by_ts = read_components(args.csv)
    print(f"components.csv  snapshots {len(comps_by_ts)}  "
          f"components {sum(len(v) for v in comps_by_ts.values())}")

    conn = psycopg.connect(args.dsn, autocommit=False)
    t = args.target_schema

    # ---------------------------------------------------------------- 적재 입력
    ts_dt: dict[str, object] = {}
    roots_by_ts: dict[str, dict[str, dict]] = defaultdict(dict)
    root_old_cluster: dict[int, int] = {}          # page_id -> 기존 cluster_id
    collisions = 0
    for r in conn.execute(ROOTS_SQL):
        ts = r[0].isoformat()
        ts_dt[ts] = r[0]
        key = canon(r[11])
        rec = {
            "old_cluster_id": r[1], "pulse_score": r[2], "status": r[3], "source": r[4],
            "created_at": r[5], "issue_key": r[6], "first_detected_at": r[7],
            "hot": r[8], "category": r[9], "page_id": r[10], "title": r[11],
            "weight": r[12], "is_seed": r[13], "edit_count": r[14], "views": r[15],
            "edit_baseline": r[16], "view_baseline": r[17], "spike_score": r[18],
            "size_score": r[19], "completeness": r[20],
            "window_start": r[21], "window_end": r[22],
        }
        if key in roots_by_ts[ts]:
            collisions += 1
        roots_by_ts[ts][key] = rec
        root_old_cluster[rec["old_cluster_id"]] = rec["page_id"]
    print(f"baseline roots  snapshots {len(roots_by_ts)}  "
          f"roots {sum(len(v) for v in roots_by_ts.values())}  제목 충돌 {collisions}")
    if collisions:
        raise SystemExit("같은 snapshot 안에서 canon 제목이 겹친다 — 매핑이 모호해진다.")

    extra_by_old: dict[int, list[dict]] = defaultdict(list)
    for r in conn.execute(EXTRA_SQL):
        extra_by_old[r[0]].append(dict(zip(("page_id",) + MEMBER_COLS,
                                           (r[1], r[2], r[3], r[4], r[5], r[6], r[7],
                                            r[8], r[9], r[10], r[11], r[12]))))
    edges_by_old: dict[int, list[tuple]] = defaultdict(list)
    for r in conn.execute(EDGES_SQL):
        edges_by_old[r[0]].append(r[1:])
    print(f"baseline 비-seed 멤버 {sum(len(v) for v in extra_by_old.values())}  "
          f"clickstream 간선 {sum(len(v) for v in edges_by_old.values())}")

    # ---------------------------------------------------------------- 정합성
    missing = 0
    for ts, comps in comps_by_ts.items():
        have = roots_by_ts.get(ts)
        if have is None:
            raise SystemExit(f"components.csv 의 snapshot {ts} 가 DB 에 없다")
        flat = [x for c in comps for x in c]
        if len(flat) != len(set(flat)):
            raise SystemExit(f"{ts}: 같은 root 가 두 component 에 들어 있다")
        if set(flat) != set(have):
            missing += 1
    if missing:
        raise SystemExit(f"{missing}개 snapshot 에서 root 집합이 components.csv 와 다르다")
    print("정합성 OK — 1,104 snapshot 모두 root 집합이 일치한다")

    # ---------------------------------------------------------------- 행 구성
    # cluster_id 를 파이썬에서 1..N 으로 미리 매긴다. 한 건씩 INSERT … RETURNING 하면
    # 왕복이 19,432번이라 십수 분 걸린다 — COPY 한 번으로 끝낸다.
    cluster_rows, member_rows, edge_rows = [], [], []
    for ts in sorted(comps_by_ts):
        roots = roots_by_ts[ts]
        for comp in comps_by_ts[ts]:
            recs = [roots[x] for x in comp]
            lead = max(recs, key=lambda r: (r["spike_score"], r["title"]))
            cid = len(cluster_rows) + 1
            cluster_rows.append((
                cid, ts_dt[ts], None, lead["spike_score"], lead["status"], lead["source"],
                min(r["created_at"] for r in recs), lead["issue_key"],
                min(r["first_detected_at"] for r in recs),
                any(r["hot"] for r in recs), lead["category"]))

            members: dict[int, tuple] = {}
            for r in recs:
                members[r["page_id"]] = tuple(r[c] for c in MEMBER_COLS)
            if args.keep_clickstream_members:
                for r in recs:
                    for e in extra_by_old[r["old_cluster_id"]]:
                        members.setdefault(e["page_id"], tuple(e[c] for c in MEMBER_COLS))
            member_rows += [(cid, pid) + vals for pid, vals in members.items()]

            # 간선은 양 끝이 모두 이 클러스터의 멤버일 때만 남긴다(테이블 주석의 계약).
            seen = set()
            for r in recs:
                for e in edges_by_old[r["old_cluster_id"]]:
                    if e[:3] in seen or e[0] not in members or e[1] not in members:
                        continue
                    seen.add(e[:3])
                    edge_rows.append((cid,) + e)

    # ---------------------------------------------------------------- 교체
    # 🔴 읽기 질의가 이미 트랜잭션을 열어 뒀다. 여기서 conn.transaction() 을 쓰면
    #    savepoint 가 될 뿐이고 close() 가 바깥 트랜잭션을 롤백한다. 명시적으로 커밋한다.
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE {t}.issue_cluster RESTART IDENTITY CASCADE")
        cur.execute(f"DELETE FROM {t}.cluster_snapshot")
        # COPY 는 GENERATED ALWAYS 컬럼에 값을 못 넣는다. preview DB 한정으로 BY DEFAULT 로
        # 바꾼다 — 여전히 identity 라 값을 생략하면 자동 생성된다(백엔드 동작 무영향).
        cur.execute(f"ALTER TABLE {t}.issue_cluster ALTER COLUMN id SET GENERATED BY DEFAULT")

        with cur.copy(f"COPY {t}.issue_cluster (id, snapshot_ts, label, pulse_score, status,"
                      " source, created_at, issue_key, first_detected_at, hot, category)"
                      " FROM STDIN") as cp:
            for row in cluster_rows:
                cp.write_row(row)
        with cur.copy(f"COPY {t}.cluster_member (cluster_id, page_id, " +
                      ", ".join(MEMBER_COLS) + ") FROM STDIN") as cp:
            for row in member_rows:
                cp.write_row(row)
        with cur.copy(f"COPY {t}.cluster_edge (cluster_id, source_page_id, target_page_id,"
                      " kind, directed, weight, evidence_label, evidence_month,"
                      " evidence_observed_at) FROM STDIN") as cp:
            for row in edge_rows:
                cp.write_row(row)

        cur.execute(f"SELECT setval(pg_get_serial_sequence('{t}.issue_cluster','id'), %s)",
                    (len(cluster_rows),))
        cur.execute(
            f"INSERT INTO {t}.cluster_snapshot "
            "(snapshot_ts, source, cluster_count, score_version, new_window_hours, completed_at) "
            "SELECT b.snapshot_ts, b.source, "
            f"       (SELECT count(*) FROM {t}.issue_cluster c "
            "         WHERE c.snapshot_ts = b.snapshot_ts AND c.source = b.source), "
            "       b.score_version, b.new_window_hours, b.completed_at "
            "  FROM baseline.cluster_snapshot b")
    conn.commit()

    print(f"적재 완료 — issue_cluster {len(cluster_rows)}  cluster_member {len(member_rows)}  "
          f"cluster_edge {len(edge_rows)}")
    with conn.cursor() as cur:
        for q in (f"SELECT count(*) FROM {t}.issue_cluster",
                  f"SELECT count(*) FROM {t}.cluster_member",
                  f"SELECT count(*) FROM {t}.cluster_edge",
                  f"SELECT count(*) FROM {t}.cluster_snapshot",
                  f"SELECT sum(cluster_count) FROM {t}.cluster_snapshot"):
            print(f"  커밋 후 확인 {q.split('FROM ')[1]:32s} {cur.execute(q).fetchone()[0]}")
    conn.close()


if __name__ == "__main__":
    main()
