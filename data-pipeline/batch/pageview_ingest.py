"""pageview_complete 일별 덤프를 받아 시간별 조회수 JSONL.gz 로 적재한다. WP-57.

    python -m batch.pageview_ingest --wiki enwiki --date 2025-06-12
    python -m batch.pageview_ingest --wiki enwiki --month 2025-06              # 그 달 전체
    python -m batch.pageview_ingest --wiki enwiki --date 2025-06-12 --dry-run   # 세기만
    python -m batch.pageview_ingest --wiki enwiki --date 2025-06-12 --agents user,automated

명세 §4·§5·§10·§11. 소비: baseline `view_ewma`(WP-58/-60).

한 날짜의 agent 파일들(user/automated/spider …)을 발견해 모두 적재한다. agent 구성은
시기마다 다르므로(§57) 후보를 순회하며 실제 있는 것만 처리하고, 404 는 결손으로 기록한다
— agent 끼리 합치거나 없는 agent 를 0 으로 채우지 않는다.

다운로드·shard·매니페스트는 mediawiki 적재(WP-56, ingest.py)와 같은 장치를 쓴다
— HDFS(WP-28)가 서면 ShardWriter 한 곳만 갈아끼운다.
"""

from __future__ import annotations

import argparse
import bz2
import json
import shutil
import sys
import urllib.error
from calendar import monthrange
from dataclasses import asdict
from pathlib import Path

from .ingest import Counts, MANIFEST_NAME, ShardWriter, download, env
from .pageview import SchemaMismatch, aggregate, project_for

PAGEVIEW_BASE = "https://dumps.wikimedia.org/other/pageview_complete"

#: 순회할 agent 후보. 있는 것만 적재된다 — 없는 건 결손으로 기록. §57: 하드코딩 금지의 뜻은
#: "이 목록이 곧 결과가 아니다"이다. 발견은 404 여부로 한다.
CANDIDATE_AGENTS = ("user", "automated", "spider")

#: shard 크기 잠정치. 실적재에서 재고 확정한다(명세 §11). §56 과 같은 이유.
DEFAULT_SHARD_RECORDS = 500_000


def dump_url(date: str, agent: str) -> str:
    """/{YYYY}/{YYYY}-{MM}/pageviews-{YYYYMMDD}-{agent}.bz2 (덤프 디렉터리 규칙)."""
    year, month, day = date.split("-")
    return (f"{PAGEVIEW_BASE}/{year}/{year}-{month}/"
            f"pageviews-{year}{month}{day}-{agent}.bz2")


def read_lines(path: Path):
    """bz2 를 텍스트 줄로 흘려보낸다. 인코딩은 UTF-8, 깨진 바이트는 대체."""
    with bz2.open(path, "rt", encoding="utf-8", errors="replace") as handle:
        yield from handle


def ingest_agent(
    date: str, wiki: str, project: str, agent: str,
    cache_dir: Path, writer: ShardWriter | None, counts: Counts,
) -> str:
    """한 agent 파일을 받아 적재한다. 반환: "ok" | "missing"(404).

    404 는 그 날짜에 그 agent 파일이 없다는 뜻이라 결손으로 남기고 계속한다.
    """
    cache = cache_dir / f"pageviews-{date.replace('-', '')}-{agent}.bz2"
    try:
        dump = download(dump_url(date, agent), cache)
    except urllib.error.HTTPError as err:
        if err.code == 404:
            print(f"결손: {agent} 파일 없음 (404)")
            return "missing"
        raise

    for rec in aggregate(read_lines(dump), project, wiki, agent, date):
        counts.read += 1
        if writer is not None:
            writer.write(asdict(rec))
        counts.written += 1
    return "ok"


def dates_in_month(month: str) -> list[str]:
    """YYYY-MM → 그 달의 모든 날짜 리스트 ["YYYY-MM-01", …]."""
    year, mon = (int(x) for x in month.split("-"))
    return [f"{month}-{day:02d}" for day in range(1, monthrange(year, mon)[1] + 1)]


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="pageview_complete 덤프 적재 (WP-57)")
    p.add_argument("--wiki", default="enwiki")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--date", help="하루만: YYYY-MM-DD")
    group.add_argument("--month", help="한 달 전체: YYYY-MM (하루씩 순회)")
    p.add_argument("--agents", default=",".join(CANDIDATE_AGENTS),
                   help="순회할 agent 후보 (쉼표 구분). 없는 건 결손 기록")
    p.add_argument("--out", default=env("PAGEVIEW_OUT", "./data/pageview"))
    p.add_argument("--cache", default=env("DUMP_CACHE", "./data/cache"))
    p.add_argument("--shard-records", type=int, default=DEFAULT_SHARD_RECORDS)
    p.add_argument("--dry-run", action="store_true", help="적재 없이 세기만")
    return p


def ingest_date(
    date: str, wiki: str, project: str, agents: list[str],
    out_root: Path, cache_dir: Path, shard_records: int, dry_run: bool,
) -> str:
    """하루를 적재한다. 반환: "ok" | "skip"(이미 적재) | "missing"(그날 agent 파일 0).

    SchemaMismatch 는 잡지 않고 위로 던진다 — 형식 손상은 전체 실행을 멈춰야 한다.
    """
    out_dir = out_root / wiki / date
    if (out_dir / MANIFEST_NAME).exists() and not dry_run:
        print(f"이미 적재됨: {date} (건너뛴다)")
        return "skip"

    counts = Counts()
    present: list[str] = []
    missing: list[str] = []

    if dry_run:
        for agent in agents:
            status = ingest_agent(date, wiki, project, agent, cache_dir, None, counts)
            (present if status == "ok" else missing).append(agent)
        print(f"[dry-run] {date} agents={present} missing={missing} "
              f"records={counts.written:,}")
        return "ok" if present else "missing"

    # 형제 .partial 에 다 쓴 뒤 통째로 rename — 반쪽 출력이 완료본으로 안 보이게.
    staging = out_dir.with_name(out_dir.name + ".partial")
    if staging.exists():
        shutil.rmtree(staging)
    with ShardWriter(staging, shard_records) as writer:
        for agent in agents:
            status = ingest_agent(date, wiki, project, agent, cache_dir, writer, counts)
            (present if status == "ok" else missing).append(agent)

    if not present:
        # agent 파일이 하나도 없으면 그날 자체가 결손이다. 빈 완료본을 만들지 않는다.
        print(f"결손 날짜: {date} — 적재할 agent 파일이 없다 {missing}", file=sys.stderr)
        shutil.rmtree(staging, ignore_errors=True)
        return "missing"

    if out_dir.exists():
        shutil.rmtree(out_dir)
    staging.rename(out_dir)
    (out_dir / MANIFEST_NAME).write_text(
        json.dumps({"wiki": wiki, "date": date, "project": project,
                    "agents_present": present, "agents_missing": missing,
                    "shards": writer.shards, "records": counts.written},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"적재 완료: {out_dir}  agents={present} missing={missing} "
          f"records={counts.written:,}")
    return "ok"


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    project = project_for(args.wiki)
    agents = [a.strip() for a in args.agents.split(",") if a.strip()]
    dates = [args.date] if args.date else dates_in_month(args.month)

    out_root = Path(args.out)
    cache_dir = Path(args.cache)
    cache_dir.mkdir(parents=True, exist_ok=True)

    tally = {"ok": 0, "skip": 0, "missing": 0}
    try:
        for date in dates:
            tally[ingest_date(date, args.wiki, project, agents,
                              out_root, cache_dir, args.shard_records, args.dry_run)] += 1
    except SchemaMismatch as mismatch:
        # 위치가 하나만 밀려도 전부 틀린 값이 된다. 조용히 넘기지 않는다.
        print(f"스키마 불일치 — 덤프 형식이 바뀌었을 수 있다: {mismatch}", file=sys.stderr)
        return 2

    if args.month:
        print(f"월 적재 요약 {args.month}: 적재 {tally['ok']} · 건너뜀 {tally['skip']} · "
              f"결손 {tally['missing']} (총 {len(dates)}일)")
    # 하루라도 실제로 적재됐거나 이미 있으면 성공. 전부 결손이면 3.
    return 0 if (tally["ok"] or tally["skip"]) else 3


if __name__ == "__main__":
    sys.exit(main())
