"""전체 1,104 스냅샷 회귀 — **production 경로만** 써서 PoC 5 결과를 재현하는지 본다.

검사하는 것은 두 단계 전부다 (WP-161).

    1. ROOT SELECTION   `cluster.root_selection.load_selection` — spike → 시점당 20 root
    2. CORE GROUPING    `cluster.driver.build_snapshot_at` → `cluster.snapshot.build_snapshot`
                        → `cluster.rootgraph.core`

🔴 **PoC 산출물을 결과로 읽어 통과시키지 않는다.** root 는 `spike` 에서 production
selector 가 고르고, 클러스터는 production driver 가 만든다. PoC frozen root set 은
**selector 가 같은 root 를 골랐는지 대조하는 oracle 로만** 쓴다.

어긋나면 종료 코드가 0 이 아니다.

사용
    python tools/cluster-preview/verify_core_regression.py
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, defaultdict
from datetime import timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "data-pipeline"))

import psycopg                                             # noqa: E402

from cluster.driver import build_snapshot_at, load_snapshot_times   # noqa: E402
from cluster.root_selection import (                       # noqa: E402
    DEFAULT_COOLDOWN_HOURS,
    RootSelectionConfig,
    load_selection,
)

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

#: oracle — PoC 5 가 실제로 쓴 root. 비교 대상일 뿐 입력이 아니다.
FROZEN_ROOTS_SQL = """
SELECT ic.snapshot_ts, cm.page_id
  FROM baseline.issue_cluster ic
  JOIN baseline.cluster_member cm ON cm.cluster_id = ic.id AND cm.spike_score IS NOT NULL
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


def check_root_selection(conn, source: str) -> tuple[bool, set]:
    """B. production selector 가 PoC frozen root set 과 같은 root 를 고르는가."""
    config = RootSelectionConfig()
    print(f"ROOT SELECTION  {config.describe()}")
    selection = load_selection(conn, source, config)
    frozen = {(ts, pid) for ts, pid in conn.execute(FROZEN_ROOTS_SQL)}

    per_snapshot = Counter(ts for ts, _ in selection)
    wrong_count = {ts: n for ts, n in per_snapshot.items() if n != 20}

    last_seen: dict[int, list] = defaultdict(list)
    for ts, pid in sorted(selection):
        last_seen[pid].append(ts)
    window = timedelta(hours=DEFAULT_COOLDOWN_HOURS)
    violations = sum(1 for picks in last_seen.values()
                     for a, b in zip(picks, picks[1:]) if b - a < window)

    only_prod, only_poc = selection - frozen, frozen - selection
    ok = (selection == frozen and not wrong_count and not violations)
    print(f"  PoC frozen roots         : {len(frozen):,}")
    print(f"  production selected roots: {len(selection):,}")
    print(f"  exact (snapshot_ts, page_id) match: {selection == frozen}")
    print(f"  mismatch production-only : {len(only_prod):,}")
    print(f"  mismatch PoC-only        : {len(only_poc):,}")
    print(f"  스냅샷당 20 위반          : {len(wrong_count):,}")
    print(f"  24h 쿨다운 위반           : {violations:,}")
    for ts, pid in sorted(only_prod)[:5]:
        print(f"    prod-only  {ts} page {pid}")
    for ts, pid in sorted(only_poc)[:5]:
        print(f"    PoC-only   {ts} page {pid}")
    return ok, selection


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=DEFAULT_DSN)
    ap.add_argument("--source", default="replay")
    args = ap.parse_args()

    conn = psycopg.connect(args.dsn)
    roots_ok, selection = check_root_selection(conn, args.source)

    # ---- production driver 로 전 시점을 생산한다 (저장은 안 한다)
    times = load_snapshot_times(conn, args.source)
    print(f"\nCORE GROUPING   스냅샷 {len(times):,}")
    sizes: Counter[int] = Counter()
    roots = components = 0
    found: dict[str, tuple[int, set[str]]] = {}
    titles_by_id = {pid: title for pid, title in
                    conn.execute("SELECT id, title FROM wiki_page")}
    for i, ts in enumerate(times):
        snapshot = build_snapshot_at(conn, ts, args.source, selection=selection)
        key = ts.strftime("%Y-%m-%d %H:%M")
        for cluster in snapshot.clusters:
            members = {titles_by_id[m.page_id] for m in cluster.members}
            sizes[len(members)] += 1
            components += 1
            roots += len(members)
            for _name, case_ts, anchor, _n, _must in CASES:
                if key == case_ts and anchor in members:
                    found[anchor] = (len(members), members)
        if i and i % 200 == 0:
            print(f"  {i}/{len(times)}", file=sys.stderr, flush=True)
    conn.close()

    buckets = Counter(bucket(n) for n, c in sizes.items() for _ in range(c))
    actual = {
        "snapshots": len(times),
        "roots": roots,
        "components": components,
        "buckets": {k: buckets.get(k, 0) for k in EXPECTED["buckets"]},
        "max": max(sizes),
        "giant_20plus": sum(c for n, c in sizes.items() if n >= 20),
    }

    print("\n분포 비교 (PoC 5 full-1104 대비)")
    print(f"{'항목':<16}{'기대':>10}{'실측':>10}   판정")
    ok = roots_ok
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

    print("\n" + ("회귀 없음 — production 경로가 PoC 5 결과를 그대로 낸다." if ok
                  else "🔴 회귀가 있다. 위 불일치 항목을 본다."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
