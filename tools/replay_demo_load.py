"""replay 산출물에서 **지정한 날짜의 스냅샷만** 다른 DB 로 옮긴다 (WP-157).

    python tools/replay_demo_load.py --src "$SRC_DSN" --dst "$DST_DSN" \
        --days 2026-07-17,2026-08-02 --dry-run
    python tools/replay_demo_load.py --src ... --dst ... --days ... [--replace]

시연을 2026-07-17 · 2026-08-02 이틀로 확정했다(-215). 격리 replay DB(5436 preview,
ROOT SELECTION + CORE)에서 그 이틀만 골라 운영에 올린다. 두 달 전체를 올리면 매칭·요약
워커가 크레딧을 다른 날에 쓴다 — 날짜 필터(-215)와 짝이다.

## 옮기는 것

    cluster_snapshot  (source, snapshot_ts)            그대로
    issue_cluster     새 id 를 받는다                   src id → dst id 매핑
    cluster_member    cluster_id·page_id 를 다시 매긴다 판정 당시 고정값 그대로
    cluster_edge      cluster_id·양 끝 page_id 재매핑
    spike             멤버 문서의 그 무렵 spike          (source, page_id, window_start) 충돌 무시
    wiki_page         (wiki, title) 로 찾고 없으면 만든다

🔴 **`wiki_page.id` 는 DB 마다 다르다.** 그대로 복사하면 FK 는 통과하는데 **엉뚱한 문서**를
가리킨다 — 에러가 안 나서 화면에서 제목이 뒤바뀐 걸 봐야 안다. 반드시 `(wiki, title)` 로
dst id 를 다시 찾는다.

## 옮기지 않는 것

`issue_report`·`cluster_stock`·`cluster_org_mention` — 운영 워커가 만든다. 소스에 있어도
옛 규칙·옛 모델 결과라 섞지 않는다. `page_intro` 는 워커가 그 시점 revision 으로 채운다.

## 안전장치

* 한 트랜잭션이다. 중간에 실패하면 dst 에 아무것도 안 남는다
* dst 에 같은 날 replay 스냅샷이 이미 있으면 **멈춘다.** `--replace` 를 줘야 그날 것을 지우고
  다시 넣는다 — 지우면 CASCADE 로 그날의 `issue_report`·`cluster_stock` 도 날아간다
  (2026-09-22 골든데이 `issue_report` 0행 사고와 같은 경로다)
* 날짜는 **UTC** 로 자른다. `snapshot_ts` 가 UTC 다
* src 와 dst 가 같으면 거부한다
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

SOURCE = "replay"

SNAPSHOT_COLS = ("snapshot_ts", "source", "cluster_count", "score_version", "new_window_hours")
CLUSTER_COLS = ("snapshot_ts", "label", "pulse_score", "status", "source", "created_at",
                "issue_key", "first_detected_at", "hot", "category")
MEMBER_COLS = ("weight", "is_seed", "edit_count", "views", "edit_baseline", "view_baseline",
               "spike_score", "size_score", "completeness", "window_start", "window_end")
EDGE_COLS = ("kind", "directed", "weight", "evidence_label", "evidence_month",
             "evidence_observed_at")
SPIKE_COLS = ("detected_at", "window_start", "edit_count", "edit_z", "view_ratio",
              "spike_score", "source", "views", "view_baseline", "max_rev_id", "last_edit_ts")


def parse_days(text: str) -> list[date]:
    days = sorted({date.fromisoformat(d.strip()) for d in text.split(",") if d.strip()})
    if not days:
        raise SystemExit("--days 가 비었다 (YYYY-MM-DD 쉼표 구분, UTC)")
    return days


def day_ranges(days: list[date]) -> list[tuple[datetime, datetime]]:
    """UTC 날짜 → [그날 0시, 다음날 0시)."""
    out = []
    for d in days:
        start = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        out.append((start, start + timedelta(days=1)))
    return out


def in_days_sql(column: str, n: int) -> str:
    """`(col >= %s AND col < %s) OR ...` — 파라미터는 day_ranges 를 펴서 준다."""
    return "(" + " OR ".join(f"({column} >= %s AND {column} < %s)" for _ in range(n)) + ")"


def flat(ranges):
    return [x for r in ranges for x in r]


def read_source(src, days: list[date]) -> dict:
    ranges = day_ranges(days)
    params = flat(ranges)
    data: dict = {}
    with src.cursor() as cur:
        cur.execute(f"SELECT {', '.join(SNAPSHOT_COLS)} FROM cluster_snapshot "
                    f"WHERE source = %s AND {in_days_sql('snapshot_ts', len(ranges))} "
                    "ORDER BY snapshot_ts", [SOURCE, *params])
        data["snapshots"] = cur.fetchall()

        cur.execute(f"SELECT id, {', '.join(CLUSTER_COLS)} FROM issue_cluster "
                    f"WHERE source = %s AND {in_days_sql('snapshot_ts', len(ranges))} "
                    "ORDER BY id", [SOURCE, *params])
        data["clusters"] = cur.fetchall()
        ids = [r[0] for r in data["clusters"]]

        cur.execute(f"SELECT cluster_id, page_id, {', '.join(MEMBER_COLS)} FROM cluster_member "
                    "WHERE cluster_id = ANY(%s)", [ids])
        data["members"] = cur.fetchall()

        cur.execute(f"SELECT cluster_id, source_page_id, target_page_id, {', '.join(EDGE_COLS)} "
                    "FROM cluster_edge WHERE cluster_id = ANY(%s)", [ids])
        data["edges"] = cur.fetchall()

        # 멤버 문서의 spike 중 그 무렵 것. 스냅샷이 24시간을 되돌아보므로 앞날 하루를 붙인다.
        member_pages = sorted({m[1] for m in data["members"]})
        wide = [(a - timedelta(days=1), b) for a, b in ranges]
        cur.execute(f"SELECT page_id, {', '.join(SPIKE_COLS)} FROM spike "
                    f"WHERE source = %s AND page_id = ANY(%s) "
                    f"AND {in_days_sql('detected_at', len(wide))}",
                    [SOURCE, member_pages, *flat(wide)])
        data["spikes"] = cur.fetchall()

        pages = set(member_pages)
        pages |= {e[1] for e in data["edges"]} | {e[2] for e in data["edges"]}
        cur.execute("SELECT id, wiki, title FROM wiki_page WHERE id = ANY(%s)", [sorted(pages)])
        data["pages"] = cur.fetchall()
    return data


def existing_days(dst, days: list[date]) -> list[tuple[str, int]]:
    ranges = day_ranges(days)
    with dst.cursor() as cur:
        cur.execute("SELECT (snapshot_ts AT TIME ZONE 'UTC')::date::text, count(*) FROM issue_cluster "
                    f"WHERE source = %s AND {in_days_sql('snapshot_ts', len(ranges))} "
                    "GROUP BY 1 ORDER BY 1", [SOURCE, *flat(ranges)])
        return cur.fetchall()


def delete_days(dst, days: list[date]) -> tuple[int, int]:
    """그날 replay 스냅샷을 지운다. CASCADE 로 멤버·간선·요약·종목이 같이 지워진다."""
    ranges = day_ranges(days)
    cond = in_days_sql("snapshot_ts", len(ranges))
    with dst.cursor() as cur:
        cur.execute(f"DELETE FROM issue_cluster WHERE source = %s AND {cond}", [SOURCE, *flat(ranges)])
        clusters = cur.rowcount
        cur.execute(f"DELETE FROM cluster_snapshot WHERE source = %s AND {cond}", [SOURCE, *flat(ranges)])
        return clusters, cur.rowcount


def map_pages(dst, pages) -> dict[int, int]:
    """src page_id → dst page_id. (wiki, title) 로 찾고 없으면 만든다."""
    mapping: dict[int, int] = {}
    with dst.cursor() as cur:
        for src_id, wiki, title in pages:
            cur.execute(
                "INSERT INTO wiki_page (wiki, title) VALUES (%s, %s) "
                "ON CONFLICT (wiki, title) DO UPDATE SET last_seen = wiki_page.last_seen "
                "RETURNING id", (wiki, title))
            mapping[src_id] = cur.fetchone()[0]
    return mapping


def write_dest(dst, data: dict) -> dict:
    counts: dict = defaultdict(int)
    page = map_pages(dst, data["pages"])
    counts["wiki_page"] = len(page)
    with dst.cursor() as cur:
        for row in data["snapshots"]:
            cur.execute(f"INSERT INTO cluster_snapshot ({', '.join(SNAPSHOT_COLS)}) "
                        f"VALUES ({', '.join(['%s'] * len(SNAPSHOT_COLS))})", row)
            counts["cluster_snapshot"] += 1

        cluster: dict[int, int] = {}
        for src_id, *rest in data["clusters"]:
            cur.execute(f"INSERT INTO issue_cluster ({', '.join(CLUSTER_COLS)}) "
                        f"VALUES ({', '.join(['%s'] * len(CLUSTER_COLS))}) RETURNING id", rest)
            cluster[src_id] = cur.fetchone()[0]
        counts["issue_cluster"] = len(cluster)

        member_rows = [(cluster[c], page[p], *rest) for c, p, *rest in data["members"]]
        cur.executemany(f"INSERT INTO cluster_member (cluster_id, page_id, {', '.join(MEMBER_COLS)}) "
                        f"VALUES ({', '.join(['%s'] * (2 + len(MEMBER_COLS)))})", member_rows)
        counts["cluster_member"] = len(member_rows)

        edge_rows = [(cluster[c], page[s], page[t], *rest) for c, s, t, *rest in data["edges"]]
        cur.executemany("INSERT INTO cluster_edge (cluster_id, source_page_id, target_page_id, "
                        f"{', '.join(EDGE_COLS)}) "
                        f"VALUES ({', '.join(['%s'] * (3 + len(EDGE_COLS)))})", edge_rows)
        counts["cluster_edge"] = len(edge_rows)

        inserted = 0
        for p, *rest in data["spikes"]:
            cur.execute(f"INSERT INTO spike (page_id, {', '.join(SPIKE_COLS)}) "
                        f"VALUES ({', '.join(['%s'] * (1 + len(SPIKE_COLS)))}) "
                        "ON CONFLICT (source, page_id, window_start) DO NOTHING", (page[p], *rest))
            inserted += cur.rowcount
        counts["spike"] = inserted
        counts["spike_skipped"] = len(data["spikes"]) - inserted
    return dict(counts)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="replay 스냅샷 날짜 단위 이관 (WP-157)")
    p.add_argument("--src", required=True, help="격리 replay DB DSN (읽기만 한다)")
    p.add_argument("--dst", required=True, help="대상 DB DSN")
    p.add_argument("--days", required=True, help="UTC 날짜, 쉼표 구분 (예: 2026-07-17,2026-08-02)")
    p.add_argument("--replace", action="store_true",
                   help="dst 에 그날 replay 가 있으면 지우고 다시 넣는다 (요약·종목도 같이 지워진다)")
    p.add_argument("--dry-run", action="store_true", help="읽고 세기만 한다. dst 에 안 쓴다")
    args = p.parse_args(argv)
    if args.src == args.dst:
        raise SystemExit("거부: src 와 dst 가 같다")
    days = parse_days(args.days)

    import psycopg

    with psycopg.connect(args.src) as src:
        src.read_only = True
        data = read_source(src, days)
    print(f"src: 스냅샷 {len(data['snapshots'])} · 이슈 {len(data['clusters'])} · "
          f"멤버 {len(data['members'])} · 간선 {len(data['edges'])} · "
          f"spike {len(data['spikes'])} · 문서 {len(data['pages'])}")
    if not data["clusters"]:
        print("옮길 이슈가 없다 — 날짜·source 를 확인한다", file=sys.stderr)
        return 1

    with psycopg.connect(args.dst) as dst:
        already = existing_days(dst, days)
        if already:
            print(f"dst 에 이미 있다: {already}")
            if not args.replace:
                print("멈춘다 — 지우고 다시 넣으려면 --replace (그날 요약·종목도 지워진다)",
                      file=sys.stderr)
                return 2
        if args.dry_run:
            print("[dry-run] dst 에 쓰지 않았다")
            return 0
        if already:
            print("삭제: issue_cluster %d · cluster_snapshot %d" % delete_days(dst, days))
        counts = write_dest(dst, data)
        dst.commit()
    print("적재:", " · ".join(f"{k} {v:,}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
