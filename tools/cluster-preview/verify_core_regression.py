"""전체 1,104 스냅샷 CORE 회귀 — 프로덕션 코드로 PoC 5 분포가 재현되는지 (WP-186).

무엇을 검사하나
    `cluster.snapshot.build_snapshot`(프로덕션 함수)을 22,080 root 전부에 돌려
    PoC 5 가 오프라인으로 낸 분포와 **정확히** 같은지 본다. 다르면 0 이 아닌 코드로 끝난다.

🔴 **root 집합은 `baseline.cluster_member` 에서 읽는다. `spike` 가 아니다.**
    preview DB 의 `spike` 는 스냅샷당 51~393행인데 `issue_cluster` 는 정확히 20행이고,
    한 문서가 하루에 두 번 root 가 되지 않는다(2026-09-22 실측). 두 테이블이 **서로 다른
    실행의 산출물**이라는 뜻이다 — 지금 `cluster.driver` 에는 그런 상한·중복 제거가 없다.
    PoC 5 가 측정한 것은 전자이므로 회귀도 전자로 잰다. root 선택 규칙은 이번 범위 밖이다
    (detector·root selection 수정 금지).

    즉 이 스크립트가 보증하는 것은 **"같은 root 를 주면 같은 component 가 나온다"** 이지
    "driver 를 그대로 돌리면 19,432 가 나온다" 가 아니다.

사용
    python tools/cluster-preview/verify_core_regression.py
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "data-pipeline"))

import psycopg                                             # noqa: E402

from cluster import asof_links                             # noqa: E402
from cluster.snapshot import Seed, build_snapshot          # noqa: E402

DEFAULT_DSN = ""
    "PREVIEW_DSN",
    "postgresql://replay:<local-db-password>@localhost:5436/wikipulse_cluster_preview",
)

#: PoC 5 `full-1104/summary.json` 실측. 한 칸이라도 어긋나면 회귀다.
EXPECTED = {
    "snapshots": 1104,
    "roots": 22080,
    "components": 19432,
    "buckets": {"1": 17569, "2": 1461, "3-4": 322, "5-7": 57, "8-12": 20, "13+": 3},
    "max": 16,
    "giant_20plus": 0,
}

#: 대표 사건 — 크기와 반드시 들어 있어야 할 멤버.
CASES = [
    ("Dolly", "2026-08-25 20:00", "Stella Parton", 16,
     ["Dollywood", "Randy Parton", "Coat of Many Colors (song)", "Straight Talk"]),
    ("Mangione / Brian Thompson", "2026-08-14 00:00", "Luigi Mangione", 2,
     ["Killing of Brian Thompson"]),
    ("SummerSlam", "2026-08-02 00:00", "SummerSlam", 3,
     ["Nick Aldis", "Gunther (wrestler)"]),
    ("SummerSlam (2026)", "2026-08-04 19:00", "SummerSlam (2026)", 2, ["Brock Lesnar"]),
    ("WWE 08-03", "2026-08-03 00:00", "Trick Williams", 6,
     ["Sami Zayn", "Chelsea Green", "WWE United States Championship"]),
    ("WWE 08-15", "2026-08-15 03:00", "Hikuleo (wrestler)", 6,
     ["Jacy Jayne", "List of WWE personnel"]),
    ("Norwegian royal family", "2026-08-28 08:00", "Norwegian royal family", 12,
     ["Haakon VIII", "Durek Verrett", "Monarchy of Norway"]),
    ("Tim Curry", "2026-08-26 17:00", "Tim Curry", 9,
     ["Clue (film)", "The Rocky Horror Picture Show"]),
]

ROOTS_SQL = """
SELECT ic.snapshot_ts, cm.page_id, w.title, cm.views, cm.spike_score,
       cm.window_start, cm.window_end, cm.edit_count, cm.completeness, s.max_rev_id
  FROM baseline.issue_cluster ic
  JOIN baseline.cluster_member cm ON cm.cluster_id = ic.id AND cm.spike_score IS NOT NULL
  JOIN wiki_page w ON w.id = cm.page_id
  JOIN spike s ON s.page_id = cm.page_id AND s.detected_at = ic.snapshot_ts
               AND s.source = ic.source
 ORDER BY ic.snapshot_ts, cm.spike_score DESC, cm.page_id
"""


def bucket(n: int) -> str:
    if n <= 2:
        return str(n)
    if n <= 4:
        return "3-4"
    if n <= 7:
        return "5-7"
    if n <= 12:
        return "8-12"
    return "13+"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=DEFAULT_DSN)
    args = ap.parse_args()

    conn = psycopg.connect(args.dsn)
    by_ts: dict[object, list[Seed]] = {}
    for (ts, page_id, title, views, spike_score, window_start, window_end,
         edit_count, completeness, max_rev_id) in conn.execute(ROOTS_SQL):
        by_ts.setdefault(ts, []).append(Seed(
            page_id=page_id, wiki="enwiki", title=title,
            event_date=window_start.date(), spike_score=float(spike_score),
            window_start=window_start, window_end=window_end,
            edit_count=edit_count, views=views, completeness=completeness,
            max_rev_id=max_rev_id))
    roots = sum(len(v) for v in by_ts.values())
    print(f"입력  스냅샷 {len(by_ts):,} · root {roots:,}")

    all_revs = [s.max_rev_id for v in by_ts.values() for s in v if s.max_rev_id]
    cache = asof_links.load_cached(conn, all_revs)
    print(f"as-of 링크 캐시 보유 {len(cache):,}/{len(set(all_revs)):,} "
          f"(미보유 root 는 singleton 이 된다)")
    conn.close()

    sizes: Counter[int] = Counter()
    components = 0
    found: dict[str, tuple[int, set[str]]] = {}
    for ts, seeds in by_ts.items():
        root_links = {s.page_id: cache[s.max_rev_id]
                      for s in seeds if s.max_rev_id in cache}
        snapshot = build_snapshot(ts, "replay", seeds, root_links=root_links)
        key = ts.strftime("%Y-%m-%d %H:%M")
        titles = {s.page_id: s.title for s in seeds}
        for cluster in snapshot.clusters:
            members = {titles[m.page_id] for m in cluster.members}
            sizes[len(members)] += 1
            components += 1
            for _name, case_ts, anchor, _n, _must in CASES:
                if key == case_ts and anchor in members:
                    found[anchor] = (len(members), members)

    buckets = Counter(bucket(n) for n, c in sizes.items() for _ in range(c))
    actual = {
        "snapshots": len(by_ts),
        "roots": roots,
        "components": components,
        "buckets": {k: buckets.get(k, 0) for k in EXPECTED["buckets"]},
        "max": max(sizes),
        "giant_20plus": sum(c for n, c in sizes.items() if n >= 20),
    }

    print("\n분포 비교 (PoC 5 full-1104 대비)")
    print(f"{'항목':<16}{'기대':>10}{'실측':>10}   판정")
    ok = True
    flat_expected = {**{k: v for k, v in EXPECTED.items() if k != "buckets"},
                     **{f"size {k}": v for k, v in EXPECTED["buckets"].items()}}
    flat_actual = {**{k: v for k, v in actual.items() if k != "buckets"},
                   **{f"size {k}": v for k, v in actual["buckets"].items()}}
    for name, expected in flat_expected.items():
        got = flat_actual[name]
        same = got == expected
        ok &= same
        print(f"{name:<16}{expected:>10,}{got:>10,}   {'OK' if same else '불일치'}")

    print("\n대표 사건")
    for name, case_ts, anchor, size, must in CASES:
        got = found.get(anchor)
        if got is None:
            print(f"  ✗ {name:<26} {case_ts}  {anchor} 을 못 찾았다")
            ok = False
            continue
        got_size, members = got
        missing = [m for m in must if m not in members]
        good = got_size == size and not missing
        ok &= good
        print(f"  {'OK' if good else '✗ '} {name:<26} {case_ts}  [{got_size}]"
              + (f"  기대 {size}" if got_size != size else "")
              + (f"  빠진 멤버 {missing}" if missing else ""))

    print("\n" + ("회귀 없음 — PoC 5 분포와 정확히 일치한다." if ok
                  else "🔴 회귀가 있다. 위 불일치 항목을 본다."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
