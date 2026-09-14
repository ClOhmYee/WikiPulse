"""Clickstream 월별 덤프를 받아 link 이동 JSONL.gz 로 적재한다. WP-81.

    python -m batch.clickstream_ingest --wiki enwiki --month 2025-06
    python -m batch.clickstream_ingest --wiki enwiki --month 2025-06 --dry-run   # 세기만
    python -m batch.clickstream_ingest --wiki enwiki --month 2025-06 --out ./out

명세 §3.2 4번(클러스터링 게이트)·§5(데이터 소스). 소비: cluster/driver.py.

다운로드·shard 출력·매니페스트는 WP-56(batch/ingest.py)과 같은 장치를 쓴다
— HDFS(WP-28)가 서면 ShardWriter 한 곳만 갈아끼운다. 여기서 새로 하는 일은
Clickstream TSV 를 link 행만 골라 (prev, curr, n) 정규화 레코드로 바꾸는 것뿐이다.
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

from .clickstream import SchemaMismatch, parse_row
from .ingest import Counts, MANIFEST_NAME, ShardWriter, download, env

CLICKSTREAM_BASE = "https://dumps.wikimedia.org/other/clickstream"

#: shard 크기 잠정치. enwiki 실적재에서 재고 확정한다(명세 §11). §56 과 같은 이유.
DEFAULT_SHARD_RECORDS = 500_000


def dump_url(month: str, wiki: str) -> str:
    """/{month}/clickstream-{wiki}-{month}.tsv.gz (덤프 디렉터리 규칙)."""
    return f"{CLICKSTREAM_BASE}/{month}/clickstream-{wiki}-{month}.tsv.gz"


def read_lines(path: Path):
    """gzip TSV 를 텍스트 줄로 흘려보낸다. 인코딩은 UTF-8."""
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        yield from handle


def convert(lines, writer: ShardWriter | None, counts: Counts) -> None:
    """link 행만 골라 (prev, curr, n) 레코드로 쓴다. writer 가 None 이면 세기만 한다."""
    for line in lines:
        if not line.strip():
            continue
        counts.read += 1
        row = parse_row(line)          # SchemaMismatch 는 main 이 잡는다
        if row is None:
            counts.skip("type")          # external·other
            continue
        if writer is not None:
            writer.write({"prev": row.prev, "curr": row.curr, "n": row.n})
        counts.written += 1


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Clickstream 월별 덤프 적재 (WP-81)")
    p.add_argument("--wiki", default="enwiki")
    p.add_argument("--month", required=True, help="YYYY-MM")
    p.add_argument("--out", default=env("CLICKSTREAM_OUT", "./data/clickstream"))
    p.add_argument("--cache", default=env("DUMP_CACHE", "./data/cache"))
    p.add_argument("--shard-records", type=int, default=DEFAULT_SHARD_RECORDS)
    p.add_argument("--dry-run", action="store_true", help="적재 없이 세기만")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    out_dir = Path(args.out) / args.wiki / args.month
    manifest = out_dir / MANIFEST_NAME
    if manifest.exists() and not args.dry_run:
        print(f"이미 적재됨: {manifest} (건너뛴다)")
        return 0

    cache = Path(args.cache) / f"clickstream-{args.wiki}-{args.month}.tsv.gz"
    dump = download(dump_url(args.month, args.wiki), cache)

    counts = Counts()
    try:
        if args.dry_run:
            convert(read_lines(dump), None, counts)
            print(f"[dry-run] read={counts.read:,} link={counts.written:,} "
                  f"skipped={counts.skipped}")
            return 0

        # 형제 .partial 디렉터리에 다 쓴 뒤 통째로 rename — 반쪽 출력이 완료본으로 안 보이게.
        staging = out_dir.with_name(out_dir.name + ".partial")
        if staging.exists():
            shutil.rmtree(staging)
        with ShardWriter(staging, args.shard_records) as writer:
            convert(read_lines(dump), writer, counts)
    except SchemaMismatch as mismatch:
        # 위치가 하나만 밀려도 전부 틀린 값이 된다. 조용히 넘기지 않는다.
        print(f"스키마 불일치 — 덤프 컬럼이 바뀌었을 수 있다: {mismatch}", file=sys.stderr)
        return 2
    if out_dir.exists():
        shutil.rmtree(out_dir)
    staging.rename(out_dir)

    (out_dir / MANIFEST_NAME).write_text(
        json.dumps({"wiki": args.wiki, "month": args.month,
                    "shards": writer.shards, **asdict(counts)},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    print(f"적재 완료: {out_dir}  read={counts.read:,} link={counts.written:,} "
          f"skipped={counts.skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
