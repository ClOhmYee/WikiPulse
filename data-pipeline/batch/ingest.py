"""mediawiki_history 덤프를 받아 edit_event JSONL.gz 로 적재한다. WP-56.

    python -m batch.ingest --wiki enwiki --range 2025-06
    python -m batch.ingest --wiki enwiki --range 2025-06 --dry-run   # 세기만
    python -m batch.ingest --wiki aawiki --range all-time --out ./out

명세 §3.2 8번, §4, §5.

출력을 로컬로 한정한 이유
    HDFS 2노드(WP-28)가 아직 없다. 여기에 HDFS 클라이언트를 박아 두면
    인프라 없이는 파싱·정규화·테스트조차 못 돌린다. 출력 경로를 한 군데
    (`ShardWriter`)로 모아 뒀으니, HDFS 가 서면 같은 스토리에서 그 자리만 잇는다.

왜 shard 로 나누나
    한 달치를 gzip 하나로 만들면 Spark 가 분할해서 읽지 못해 태스크 1개로
    직렬화된다. ⚠️ `--shard-records` 기본값은 **잠정치**다 — enwiki 실적재에서
    파일 크기를 재고 확정해 명세 §11 에 적는다.

재실행 안전성과 이어받기
    1. 받은 덤프는 캐시에 남는다. `.part` 로 받아 완료 후 이름을 바꾸므로
       중간에 끊긴 파일을 완성본으로 착각하지 않는다. 다시 돌리면 HTTP Range 로
       받던 지점부터 이어받는다 (500 MB 를 처음부터 다시 받지 않는다).
    2. 정규화 출력은 임시 디렉터리에 쓴 뒤 통째로 옮기고 매니페스트를 남긴다.
       매니페스트가 있으면 그 (wiki, range) 는 건너뛴다. 절반만 남은 출력이
       완료본으로 보이는 상태가 생기지 않는다.
"""

from __future__ import annotations

import argparse
import bz2
import gzip
import json
import os
import shutil
import sys
import time
import urllib.request
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path

from producer.normalize import SkipEvent

from .normalize_dump import normalize_dump
from .schema import SchemaMismatch, split_row

DUMPS_BASE = "https://dumps.wikimedia.org/other/mediawiki_history"

#: 최신 스냅샷. 덤프는 마지막 2개 판만 보관한다 (readme.html).
DEFAULT_SNAPSHOT = "2026-08"

#: ⚠️ 잠정치. enwiki 실적재에서 shard 크기를 재고 확정한다 (명세 §11).
DEFAULT_SHARD_RECORDS = 500_000

MANIFEST_NAME = "_manifest.json"


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def user_agent() -> str:
    """Wikimedia 는 연락처 없는 User-Agent 를 차단한다. producer/config.py 와 같은 규칙."""
    contact = env("CONTACT_EMAIL").strip()
    if not contact:
        raise SystemExit(
            "CONTACT_EMAIL 이 필요하다. Wikimedia 는 연락처 없는 User-Agent 를 차단한다.\n"
            "  data-pipeline/.env.example 을 .env 로 복사해 채운다."
        )
    return f"WikiPulse/0.1 (WikiPulse; {contact})"


def dump_url(snapshot: str, wiki: str, time_range: str) -> str:
    """/{snapshot}/{wiki}/{snapshot}.{wiki}.{range}.tsv.bz2 (readme.html 의 규칙)."""
    return f"{DUMPS_BASE}/{snapshot}/{wiki}/{snapshot}.{wiki}.{time_range}.tsv.bz2"


@dataclass
class Counts:
    """한 번의 적재에서 무슨 일이 있었는지. 매니페스트와 화면에 그대로 나간다."""

    read: int = 0
    written: int = 0
    skipped: dict[str, int] = dataclass_field(default_factory=dict)

    def skip(self, reason: str) -> None:
        # SkipEvent 메시지는 "namespace=2" 꼴이라 앞부분만 모은다.
        key = str(reason).split("=")[0].strip()
        self.skipped[key] = self.skipped.get(key, 0) + 1


# --- 다운로드 -------------------------------------------------------------


def download(url: str, target: Path) -> Path:
    """덤프를 받는다. 이미 있으면 건너뛰고, 끊긴 것은 이어받는다.

    User-Agent 는 실제로 요청할 때만 만든다 — 캐시에 이미 있으면 CONTACT_EMAIL
    없이도 재실행·dry-run 이 돌아야 한다.
    """
    if target.exists():
        print(f"캐시 사용: {target.name} ({target.stat().st_size:,} bytes)")
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    have = partial.stat().st_size if partial.exists() else 0

    headers = {"User-Agent": user_agent()}
    if have:
        # 서버가 Range 를 무시하면 206 이 아니라 200 이 온다. 그때는 처음부터 쓴다.
        headers["Range"] = f"bytes={have}-"
        print(f"이어받기: {have:,} bytes 부터")

    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=120) as response:
        resumed = response.status == 206
        mode = "ab" if resumed else "wb"
        if have and not resumed:
            print("서버가 Range 를 무시했다 — 처음부터 받는다")
        with open(partial, mode) as out:
            shutil.copyfileobj(response, out, length=1 << 20)

    partial.rename(target)
    print(f"내려받음: {target.name} ({target.stat().st_size:,} bytes)")
    return target


# --- 출력 -----------------------------------------------------------------


class ShardWriter:
    """edit_event 를 JSONL.gz shard 로 나눠 쓴다.

    HDFS 가 붙는 자리다 (WP-28). 지금은 로컬 파일시스템만 쓴다 —
    출력 경로를 만드는 곳이 여기 한 군데뿐이라 나중에 이 클래스만 갈아끼우면 된다.
    """

    def __init__(self, directory: Path, shard_records: int) -> None:
        # 한 건도 안 나와도 디렉터리는 만든다. 없으면 "이벤트 0건" 인 정상 입력에서
        # 뒤의 rename 이 FileNotFoundError 로 터진다.
        directory.mkdir(parents=True, exist_ok=True)
        self.directory = directory
        self.shard_records = shard_records
        self.shards: list[str] = []
        self._handle: gzip.GzipFile | None = None
        self._in_shard = 0

    def write(self, event: dict) -> None:
        if self._handle is None or self._in_shard >= self.shard_records:
            self._roll()
        line = json.dumps(event, ensure_ascii=False)
        self._handle.write(f"{line}\n".encode("utf-8"))
        self._in_shard += 1

    def _roll(self) -> None:
        self.close()
        name = f"part-{len(self.shards):05d}.jsonl.gz"
        # mtime=0 으로 같은 입력이 같은 바이트를 내게 한다 (재실행 비교가 쉬워진다).
        self._handle = gzip.GzipFile(self.directory / name, "wb", mtime=0)
        self.shards.append(name)
        self._in_shard = 0

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> "ShardWriter":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


# --- 정규화 ---------------------------------------------------------------


def convert(source: Path, writer: ShardWriter | None, *, wikis=None) -> Counts:
    """덤프를 스트리밍으로 읽어 edit_event 로 바꾼다.

    writer 가 None 이면 세기만 한다 (--dry-run). 500 MB 를 통째로 메모리에
    올리지 않으려고 줄 단위로 흘린다.
    """
    counts = Counts()
    with bz2.open(source, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            counts.read += 1
            try:
                event = normalize_dump(split_row(line), wikis=wikis)
            except SkipEvent as skipped:
                counts.skip(str(skipped))
                continue
            counts.written += 1
            if writer is not None:
                writer.write(event)
    return counts


def write_manifest(directory: Path, payload: dict) -> None:
    """마지막에 쓴다. 이 파일이 있으면 그 단위는 완료된 것이다."""
    (directory / MANIFEST_NAME).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def ingest(
    *,
    wiki: str,
    time_range: str,
    snapshot: str,
    out: Path,
    cache: Path,
    shard_records: int,
    dry_run: bool,
    force: bool,
) -> Counts | None:
    """한 (wiki, range) 단위를 적재한다. 이미 완료됐으면 None."""
    destination = out / wiki / time_range
    if (destination / MANIFEST_NAME).exists() and not force:
        print(f"이미 완료: {destination} (다시 하려면 --force)")
        return None

    url = dump_url(snapshot, wiki, time_range)
    source = download(url, cache / f"{snapshot}.{wiki}.{time_range}.tsv.bz2")

    started = time.monotonic()
    if dry_run:
        counts = convert(source, None, wikis=frozenset({wiki}))
    else:
        # 임시로 쓴 뒤 통째로 옮긴다. 중간에 죽어도 반쪽 출력이 남지 않는다.
        staging = destination.with_name(destination.name + ".partial")
        if staging.exists():
            shutil.rmtree(staging)
        with ShardWriter(staging, shard_records) as writer:
            counts = convert(source, writer, wikis=frozenset({wiki}))
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging.rename(destination)
        write_manifest(
            destination,
            {
                "issue": "WP-56",
                "snapshot": snapshot,
                "wiki": wiki,
                "range": time_range,
                "source_url": url,
                "source_bytes": source.stat().st_size,
                "rows_read": counts.read,
                "events_written": counts.written,
                "skipped": counts.skipped,
                "shards": writer.shards,
                "shard_records": shard_records,
                "elapsed_seconds": round(time.monotonic() - started, 1),
            },
        )
    return counts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wiki", default=env("WIKIS", "enwiki").split(",")[0],
                        help="위키 DB 이름 (기본: enwiki)")
    parser.add_argument("--range", dest="time_range", required=True,
                        help="시간 범위. 큰 위키는 YYYY-MM, 작은 위키는 all-time")
    parser.add_argument("--snapshot", default=env("DUMP_SNAPSHOT", DEFAULT_SNAPSHOT),
                        help=f"덤프 스냅샷 (기본: {DEFAULT_SNAPSHOT})")
    parser.add_argument("--out", type=Path, default=Path(env("BATCH_OUT", "./out")),
                        help="출력 루트 (기본: ./out)")
    parser.add_argument("--cache", type=Path, default=Path(env("DUMP_CACHE", "./dumps")),
                        help="내려받은 덤프를 둘 곳 (기본: ./dumps)")
    parser.add_argument("--shard-records", type=int, default=DEFAULT_SHARD_RECORDS,
                        help=f"shard 당 이벤트 수 (잠정 기본값 {DEFAULT_SHARD_RECORDS:,})")
    parser.add_argument("--dry-run", action="store_true",
                        help="적재 없이 건수만 센다")
    parser.add_argument("--force", action="store_true",
                        help="완료된 단위도 다시 적재한다")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        counts = ingest(
            wiki=args.wiki,
            time_range=args.time_range,
            snapshot=args.snapshot,
            out=args.out,
            cache=args.cache,
            shard_records=args.shard_records,
            dry_run=args.dry_run,
            force=args.force,
        )
    except SchemaMismatch as mismatch:
        # 위치가 하나만 밀려도 전부 틀린 값이 된다. 조용히 넘기지 않는다.
        print(f"스키마 불일치 — 스냅샷 컬럼이 바뀌었을 수 있다: {mismatch}", file=sys.stderr)
        return 2
    if counts is None:
        return 0
    print(
        f"읽음 {counts.read:,} / 이벤트 {counts.written:,}"
        f"{' (dry-run, 적재 안 함)' if args.dry_run else ''}"
    )
    for reason, n in sorted(counts.skipped.items(), key=lambda kv: -kv[1]):
        print(f"  스킵 {reason}: {n:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
