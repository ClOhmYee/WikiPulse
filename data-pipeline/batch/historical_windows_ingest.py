"""Historical Window 집계 CLI — baseline 입력 데이터셋을 만든다. WP-58.

    python -m batch.historical_windows_ingest \
        --edits ./out/enwiki/2025-06 \
        --views ./data/pageview/enwiki \
        --out ./data/baseline-input/enwiki/2025-06

    ... --agents user,automated      # baseline 에 쓸 agent 만 합산 (기본: 전부)
    ... --dry-run                     # 행 수만

--edits  : 편집 적재본(WP-56) 디렉터리 (part-*.jsonl.gz)
--views  : 조회수 적재본(WP-57) wiki 디렉터리. 하위 날짜 폴더를 재귀로 읽는다
소비     : spike/baseline.py build_baseline (WP-60 이 page_id 해석 후 적재)

Spark/HDFS(WP-27/-28)가 서면 parquet 출력·"배치==스트리밍" 대조를 잇는다.
지금은 형제 적재(-56·-57)와 같은 순수 파이썬·JSONL.gz 경로다.
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sys
from collections.abc import Iterator
from dataclasses import asdict
from pathlib import Path

from .historical_windows import WINDOW_HOURS, build_windows
from .ingest import MANIFEST_NAME, ShardWriter

DEFAULT_SHARD_RECORDS = 500_000


def read_jsonl_shards(directory: Path, pattern: str) -> Iterator[dict]:
    """디렉터리 아래 JSONL.gz shard 들을 dict 로 흘려보낸다. pattern 은 glob."""
    for shard in sorted(directory.glob(pattern)):
        with gzip.open(shard, "rt", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Historical Window 집계 (WP-58)")
    p.add_argument("--edits", required=True, help="편집 적재본 디렉터리 (-56)")
    p.add_argument("--views", required=True, help="조회수 적재본 wiki 디렉터리 (-57)")
    p.add_argument("--out", required=True, help="baseline 입력 출력 디렉터리")
    p.add_argument("--agents", default="", help="합산할 agent (쉼표 구분). 비우면 전부")
    p.add_argument("--keep-bots", action="store_true", help="봇 편집도 센다(진단용)")
    p.add_argument("--shard-records", type=int, default=DEFAULT_SHARD_RECORDS)
    p.add_argument("--dry-run", action="store_true", help="적재 없이 행 수만")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    edits_dir = Path(args.edits)
    views_dir = Path(args.views)
    for label, path in (("--edits", edits_dir), ("--views", views_dir)):
        if not path.exists():
            print(f"{label} 경로 없음: {path}", file=sys.stderr)
            return 2

    agents = {a.strip() for a in args.agents.split(",") if a.strip()} or None

    def edit_events() -> Iterator[dict]:
        return read_jsonl_shards(edits_dir, "part-*.jsonl.gz")

    def pageviews() -> Iterator[dict]:
        return read_jsonl_shards(views_dir, "**/part-*.jsonl.gz")

    rows = build_windows(edit_events(), pageviews(),
                         agents=agents, keep_bots=args.keep_bots)

    if args.dry_run:
        print(f"[dry-run] window rows={len(rows):,} "
              f"(edits={edits_dir} views={views_dir} agents={agents or '전부'})")
        return 0

    out_dir = Path(args.out)
    staging = out_dir.with_name(out_dir.name + ".partial")
    if staging.exists():
        shutil.rmtree(staging)
    with ShardWriter(staging, args.shard_records) as writer:
        for row in rows:
            writer.write(asdict(row))
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    staging.rename(out_dir)

    (out_dir / MANIFEST_NAME).write_text(
        json.dumps({"issue": "WP-58",
                    "edits": str(edits_dir), "views": str(views_dir),
                    "agents": sorted(agents) if agents else "all",
                    "window_hours": WINDOW_HOURS,
                    "rows": len(rows), "shards": writer.shards},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    print(f"집계 완료: {out_dir}  rows={len(rows):,}  shards={len(writer.shards)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
