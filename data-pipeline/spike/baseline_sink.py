"""기준선 행을 page_baseline 에 적재한다 (WP-60).

    python -m spike.baseline_sink --input ./data/baseline-input/enwiki/2025-06
    python -m spike.baseline_sink --input ... --as-of 2025-06-30 --dry-run

입력은 Historical Window 산출물(WP-58). 계산은 baseline_rows.py,
가중치는 ewma.py(WP-59). 여기서 하는 일은 **문서 식별자 해석과 upsert** 뿐이다.

(wiki, title) → wiki_page.id
    파이프라인 전체가 (wiki, title) 을 문서 키로 쓴다 — EventStreams 에 page_id 가
    없어서다(wiki_page 주석). page_baseline 은 wiki_page.id 를 FK 로 받으므로
    적재 시점에 해석한다. 없는 문서는 만들어 준다: 편집 덤프에는 있지만 아직
    wiki_page 에 안 들어온 문서에서 기준선만 통째로 버려지지 않게.

멱등성
    page_baseline PK 는 (page_id, slot_index) 다. 같은 키가 오면 값을 갱신하고
    updated_at 을 새로 찍는다. 같은 입력을 두 번 돌려도 행이 늘지 않는다.
    ⚠️ 실 PostgreSQL 로 멱등성을 확인한 기록은 아직 없다 — README 참고.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from collections.abc import Iterable, Iterator
from datetime import date
from pathlib import Path

from .baseline_rows import BaselineRow, build_rows
from .ewma import DEFAULT_HALFLIFE_DAYS

#: 없으면 만들고, 있으면 last_seen 만 건드려 id 를 돌려받는다.
#: DO NOTHING 을 쓰면 충돌 시 RETURNING 이 비어 id 를 못 받는다 — 그래서 DO UPDATE.
RESOLVE_PAGE_SQL = """
INSERT INTO wiki_page (wiki, title)
VALUES (%s, %s)
ON CONFLICT (wiki, title) DO UPDATE SET last_seen = now()
RETURNING id
"""

UPSERT_BASELINE_SQL = """
INSERT INTO page_baseline
    (page_id, slot_index, edit_ewma, edit_stddev, view_ewma, view_stddev,
     sample_days, updated_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, now())
ON CONFLICT (page_id, slot_index) DO UPDATE SET
    edit_ewma   = EXCLUDED.edit_ewma,
    edit_stddev = EXCLUDED.edit_stddev,
    view_ewma   = EXCLUDED.view_ewma,
    view_stddev = EXCLUDED.view_stddev,
    sample_days = EXCLUDED.sample_days,
    updated_at  = now()
"""


def read_windows(input_dir: Path) -> Iterator[dict]:
    """-58 산출물 shard 를 흘려보낸다."""
    for shard in sorted(input_dir.glob("**/part-*.jsonl.gz")):
        with gzip.open(shard, "rt", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)


def resolve_page_ids(cur, keys: Iterable[tuple[str, str]]) -> dict[tuple[str, str], int]:
    """(wiki, title) 들을 wiki_page.id 로 해석한다. 없으면 만든다.

    한 문서가 슬롯 168개를 갖기 때문에 고유 키만 한 번씩 조회한다(캐시).
    """
    resolved: dict[tuple[str, str], int] = {}
    for wiki, title in dict.fromkeys(keys):          # 순서 유지 중복 제거
        cur.execute(RESOLVE_PAGE_SQL, (wiki, title))
        resolved[(wiki, title)] = cur.fetchone()[0]
    return resolved


def upsert_rows(cur, rows: Iterable[BaselineRow], page_ids: dict[tuple[str, str], int]) -> int:
    """기준선 행들을 page_baseline 에 upsert 한다. 반환: 쓴 행 수."""
    params = [
        (page_ids[(row.wiki, row.title)], row.slot_index,
         row.edit_ewma, row.edit_stddev, row.view_ewma, row.view_stddev,
         row.sample_days)
        for row in rows
    ]
    if params:
        cur.executemany(UPSERT_BASELINE_SQL, params)
    return len(params)


def load(conn, rows: list[BaselineRow]) -> int:
    """한 트랜잭션으로 해석 + upsert. 중간에 실패하면 아무것도 안 남는다."""
    with conn.cursor() as cur:
        page_ids = resolve_page_ids(cur, ((r.wiki, r.title) for r in rows))
        written = upsert_rows(cur, rows, page_ids)
    conn.commit()
    return written


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="기준선 산출·적재 (WP-60)")
    p.add_argument("--input", required=True, help="Historical Window 산출물 (-58)")
    p.add_argument("--as-of", help="기준선 창의 끝 YYYY-MM-DD (기본: 관측 중 최신일)")
    p.add_argument("--halflife-days", type=float, default=DEFAULT_HALFLIFE_DAYS,
                   help=f"EWMA 반감기 (WP-59, 잠정 기본 {DEFAULT_HALFLIFE_DAYS:g})")
    p.add_argument("--dsn", default=os.environ.get("DATABASE_URL", ""),
                   help="PostgreSQL DSN (기본: $DATABASE_URL)")
    p.add_argument("--dry-run", action="store_true", help="적재 없이 산출만")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    input_dir = Path(args.input)
    if not input_dir.exists():
        print(f"--input 경로 없음: {input_dir}", file=sys.stderr)
        return 2

    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    rows = build_rows(read_windows(input_dir), as_of=as_of,
                      halflife_days=args.halflife_days)

    thin = sum(1 for r in rows if r.sample_days < 7)
    no_std = sum(1 for r in rows if r.edit_stddev is None)
    print(f"기준선 행 {len(rows):,}  (얇음 sample_days<7: {thin:,} · "
          f"edit_stddev 없음: {no_std:,})")

    if args.dry_run:
        return 0
    if not args.dsn:
        print("DSN 이 없다. --dsn 또는 $DATABASE_URL 을 준다.", file=sys.stderr)
        return 2

    import psycopg     # 적재할 때만 필요 — dry-run 은 DB 드라이버 없이도 돈다

    with psycopg.connect(args.dsn) as conn:
        written = load(conn, rows)
    print(f"적재 완료: page_baseline {written:,} 행 upsert")
    return 0


if __name__ == "__main__":
    sys.exit(main())
