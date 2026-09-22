"""PoC 가 이미 받아 둔 as-of 링크를 V11 캐시(`page_asof_links`)로 옮긴다. 1회성.

왜 있나
    CORE 회귀를 돌리려면 root 22,080건의 as-of strict 링크가 필요하다. PoC 가 이미
    전부 받아 SQLite 에 갖고 있으므로(`%TEMP%/poc_asof_links.sqlite3`) 위키미디어를
    다시 22,080번 때릴 이유가 없다.

    🔴 **소스는 read-only 로만 연다** (`mode=ro&immutable=1`). 연구 세션 소유 파일이다.

같은 값인가
    PoC `links.py` 의 `canon`·`_is_ns0`·`wikitext_links` 와 `cluster/asof_links.py` 의
    `link_key`·`is_ns0`·`wikitext_links` 는 같은 규칙이다(전자를 후자로 포팅했다).
    그래서 저장된 `strict` 배열을 그대로 옮길 수 있다. 이 스크립트가 **표본으로 재검증**해
    다르면 멈춘다 — 조용히 다른 정규화가 섞이면 간선이 사라지는데 에러가 안 난다.

사용
    python tools/cluster-preview/seed_asof_link_cache.py
    python tools/cluster-preview/seed_asof_link_cache.py --sqlite ... --dsn ...
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "data-pipeline"))

import psycopg                                             # noqa: E402

from cluster.asof_links import link_key                    # noqa: E402

DEFAULT_SQLITE = os.path.join(os.environ.get("TEMP", "."), "poc_asof_links.sqlite3")
DEFAULT_DSN = ""
    "PREVIEW_DSN",
    "postgresql://replay:<local-db-password>@localhost:5436/wikipulse_cluster_preview",
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", default=DEFAULT_SQLITE)
    ap.add_argument("--dsn", default=DEFAULT_DSN)
    ap.add_argument("--batch", type=int, default=2000)
    args = ap.parse_args()

    if ":5434/" in args.dsn or ":5435/" in args.dsn:
        raise SystemExit("거부: 5434·5435 는 읽기 전용 원본이다. preview(5436) 로만 쓴다.")

    src = sqlite3.connect(f"file:{args.sqlite}?mode=ro&immutable=1", uri=True)
    total = src.execute("SELECT count(*) FROM asof_links WHERE error IS NULL").fetchone()[0]
    print(f"PoC 캐시 {args.sqlite}: 정상 수집 {total:,}건")

    conn = psycopg.connect(args.dsn)
    written = checked = 0
    rows: list[tuple] = []
    cur_pg = conn.cursor()
    for rev_id, title, strict in src.execute(
            "SELECT rev_id, title, strict FROM asof_links WHERE error IS NULL"):
        links = json.loads(strict)
        if checked < 200:                       # 정규화 동일성 표본 재검증
            for target in links[:20]:
                if link_key(target) != target:
                    raise SystemExit(
                        f"정규화 불일치: rev {rev_id} 의 {target!r} → "
                        f"{link_key(target)!r}. PoC canon 과 link_key 가 갈렸다.")
            checked += 1
        rows.append((rev_id, "enwiki", title or "", json.dumps(links), len(links), None))
        if len(rows) >= args.batch:
            written += _flush(cur_pg, rows)
            print(f"  {written:,}/{total:,}", end="\r", flush=True)
    written += _flush(cur_pg, rows)
    conn.commit()
    got = cur_pg.execute("SELECT count(*), sum(link_count) FROM page_asof_links").fetchone()
    conn.close()
    print(f"\n적재 {written:,}건 → page_asof_links 행 {got[0]:,} / 링크 {got[1]:,}")


def _flush(cur, rows: list[tuple]) -> int:
    if not rows:
        return 0
    cur.executemany(
        "INSERT INTO page_asof_links (rev_id, wiki, title, links, link_count, error)"
        " VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (rev_id) DO UPDATE SET"
        " links = EXCLUDED.links, link_count = EXCLUDED.link_count,"
        " fetched_at = now(), error = NULL",
        rows)
    n = len(rows)
    rows.clear()
    return n


if __name__ == "__main__":
    main()
