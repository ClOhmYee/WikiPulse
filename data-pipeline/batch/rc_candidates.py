"""RecentChanges 수집본 → candidate title (WP-164).

`batch/recentchanges.py` 가 남긴 raw 시간 파일을 읽어, **덤프 경로와 같은 정의**로
candidate title 을 만든다. 이 산출물의 소비처는 이슈 판정 1차 관문(명세 §3.2 —
enwiki namespace 0 에서 봇이 아닌 편집 1건 이상)이다.

🔴 **집계 규칙을 여기서 새로 쓰지 않는다.** RC 레코드를 `normalize_dump` 가 내는
    edit_event 모양으로 **바꾸기만** 하고, (wiki, title, hour) 집계와 봇 필터는
    `historical_windows.aggregate_edits` 를 그대로 부른다. 규칙이 두 벌이면
    한쪽만 바뀌어도 에러 없이 결과가 갈린다 — 이 저장소가 -79·-91·-115 에서
    반복해 겪은 형태다.

⚠️ **제목 기준이 덤프와 다르다.** RC 는 **현재 제목**을 준다(`title_basis: current`).
    덤프는 사건 당시 제목(`page_title_historical`)이다. 공백 구간에서 문서가
    이동(rename)됐다면 두 소스가 같은 문서를 다른 제목으로 부른다. 이 차이는
    산출물 manifest 에 적고 지우지 않는다 — 근거는
    `docs/validation/2026-09-21-edit-source-gap.md`.

⚠️ **봇 판정은 RC 의 `bot` 플래그다.** `allrevisions` + 사용자 그룹 조회로 대체하면
    정밀도가 0.4394 로 떨어진다(같은 문서 §3). RC 가 주는 플래그를 `is_bot` 으로
    그대로 실어 보내고, 거르는 것은 `aggregate_edits` 가 한다.

무엇을 버리나
    namespace 0 이 아닌 것, `type` 이 edit/new 가 아닌 것(log·categorize 등).
    수집이 이미 `rcnamespace=0`·`rctype=edit|new` 로 좁혀 받지만, 재수집 시한이
    없는 데이터라 읽는 쪽에서 한 번 더 막는다.

실행
    python -m batch.rc_candidates --root data/recentchanges-164 \
        --out data/rc-candidates-164
"""

from __future__ import annotations

import argparse
import bz2
import gzip
import json
import sys
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from pathlib import Path

from producer.normalize import canonical_title

from .historical_windows import aggregate_edits, hour_of_day
from .normalize_dump import SkipEvent, normalize_dump
from .schema import COLUMN_COUNT, COLUMN_INDEX

#: 이 산출물의 출처 라벨. 덤프는 "dump", 실시간은 "eventstreams" 다.
RC_SOURCE = "recentchanges"

#: 편집 신호로 볼 RC type. log·categorize·external 은 편집이 아니다.
EDIT_TYPES = frozenset({"edit", "new"})

#: 본문 namespace. 명세 §3.2 1차 관문이 여기로 한정한다.
NAMESPACE_MAIN = 0

#: 산출 shard 하나에 담을 행 수. 적재본(-56)과 같은 입도.
DEFAULT_SHARD_RECORDS = 500_000

TS = "%Y-%m-%dT%H:%M:%SZ"


def read_raw(root: Path) -> Iterator[dict]:
    """수집본 시간 파일을 시간 순으로 읽는다. `{root}/{wiki}/{YYYY}/{MM}/{DD}/{HH}.ndjson.gz`."""
    for shard in sorted(root.rglob("*.ndjson.gz")):
        with gzip.open(shard, "rt", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)


def is_edit_record(rec: dict) -> bool:
    """편집 신호인가. 봇 여부는 **보지 않는다** — 거르는 것은 집계 쪽 책임이다."""
    return rec.get("ns") == NAMESPACE_MAIN and rec.get("type") in EDIT_TYPES


def to_edit_event(rec: dict, wiki: str) -> dict:
    """RC 레코드를 `normalize_dump` 의 edit_event 모양으로 바꾼다.

    `aggregate_edits` 가 읽는 키만 맞추면 되지만(wiki·title·event_ts·user·is_bot·rev_id),
    덤프 산출물과 나란히 두고 대조할 수 있게 출처·식별자도 같이 남긴다.
    """
    return {
        "wiki": wiki,
        "title": canonical_title(rec["title"]),
        "event_type": rec["type"],
        "rev_id": rec.get("revid"),
        "rev_parent_id": rec.get("old_revid") or None,
        "user": rec.get("user"),
        # 🔴 RC 의 bot 플래그를 그대로 쓴다 (모듈 docstring ⚠️).
        "is_bot": bool(rec.get("bot")),
        "is_minor": bool(rec.get("minor")),
        "event_ts": rec["timestamp"],
        "source": RC_SOURCE,
        "rc_id": rec.get("rcid"),
        "page_id": rec.get("pageid"),
    }


def edit_events(records: Iterable[dict], wiki: str) -> Iterator[dict]:
    for rec in records:
        if is_edit_record(rec):
            yield to_edit_event(rec, wiki)


def candidate_rows(aggregates: dict) -> list[dict]:
    """집계를 산출 행으로. 정렬해 내보내 재실행 결과가 바이트로 같게 한다."""
    rows = []
    for (wiki, title, window_start), agg in aggregates.items():
        rows.append({
            "wiki": wiki,
            "title": title,
            "window_start": window_start,
            "hour_of_day": hour_of_day(window_start),
            "edit_count": agg.edit_count,
            "editor_count": agg.editor_count,
            "max_rev_id": agg.max_rev_id,
            "last_edit_ts": agg.last_edit_ts,
        })
    rows.sort(key=lambda r: (r["window_start"], r["title"]))
    return rows


def write_rows(rows: list[dict], out_dir: Path, shard_records: int) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("part-*.jsonl.gz"):
        stale.unlink()
    shards: list[str] = []
    for index in range(0, max(len(rows), 1), shard_records):
        name = f"part-{len(shards):05d}.jsonl.gz"
        with gzip.open(out_dir / name, "wt", encoding="utf-8") as handle:
            for row in rows[index:index + shard_records]:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        shards.append(name)
    return shards


# ------------------------------------------------------------------ 이음매

#: 덤프를 믿는 마지막 시각. 여기부터는 RC 가 정본이다 (WP-164 인수 조건 4).
#: 🔴 덤프 파일 자체는 02:29:37 까지 있지만 **마지막 분이 분 중간에서 잘려 있다**
#:    (02:29 는 110행, 직전 분은 167행). 통째로 믿으면 편집 수가 조용히 모자란다.
SEAM_TS = "2026-09-01T02:00:00Z"

#: 겹치는 구간의 끝. 덤프의 잘린 마지막 분(02:29)은 대조에서 뺀다.
SEAM_OVERLAP_END = "2026-09-01T02:29:00Z"


def _seconds(ts: str) -> str:
    """타임스탬프를 초 정밀도로 자른다.

    🔴 **두 소스의 표기가 다르다.** 덤프는 `2026-09-01T02:00:00.000Z`, RC 는
    `2026-09-01T02:00:00Z` 다. 자르지 않고 문자열로 비교하면 `.`(0x2E) < `Z`(0x5A)
    라 **정각 행이 덤프 쪽에서만 경계 밖으로 밀린다** — 에러 없이 이음매가
    안 맞는 것처럼 보인다(2026-09-22 실측: 덤프에만 34 · RC 에만 3 으로 나왔다).
    """
    return ts[:19]


def _in_seam(ts: str) -> bool:
    return _seconds(SEAM_TS) <= _seconds(ts) < _seconds(SEAM_OVERLAP_END)


def read_dump_revisions(path: Path, wiki: str) -> dict[int, str]:
    """덤프 꼬리 파일의 ns0 revision → {rev_id: event_ts}. 필터는 normalize_dump 것."""
    out: dict[int, str] = {}
    with bz2.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = line.rstrip("\n").split("\t")
            if len(row) != COLUMN_COUNT:
                continue
            try:
                event = normalize_dump(row, wikis=frozenset({wiki}))
            except SkipEvent:
                continue
            out[int(event["rev_id"])] = event["event_ts"]
    return out


def verify_seam(root: Path, dump: Path, wiki: str) -> int:
    """이음매에서 중복·누락이 0 인지 본다.

    겹치는 구간 `[SEAM_TS, SEAM_OVERLAP_END)` 을 두 소스에서 각각 뽑아 `rev_id` 로
    맞춘다. 이 구간은 **두 소스가 같은 편집을 담고 있어야 한다** — 한쪽에만 있는
    것이 있으면 이어붙였을 때 그만큼 새거나 겹친다.
    """
    dump_rows = {rev: ts for rev, ts in read_dump_revisions(dump, wiki).items()
                 if _in_seam(ts)}
    rc_rows = {
        int(rec["revid"]): rec["timestamp"]
        for rec in read_raw(root)
        if is_edit_record(rec) and rec.get("revid") and _in_seam(rec["timestamp"])
    }

    only_dump = sorted(set(dump_rows) - set(rc_rows))
    only_rc = sorted(set(rc_rows) - set(dump_rows))
    both = set(dump_rows) & set(rc_rows)

    print(f"이음매 {SEAM_TS} ~ {SEAM_OVERLAP_END} (덤프의 잘린 마지막 분 제외)")
    print(f"  덤프 {len(dump_rows):,} · RC {len(rc_rows):,} · 공통 {len(both):,}")
    print(f"  덤프에만 {len(only_dump):,} · RC 에만 {len(only_rc):,}")
    for label, revs in (("덤프에만", only_dump), ("RC 에만", only_rc)):
        for rev in revs[:5]:
            ts = dump_rows.get(rev) or rc_rows.get(rev)
            print(f"    {label} rev={rev} ts={ts}")
    if only_dump or only_rc:
        print("🔴 이음매가 안 맞는다 — 이어붙이면 그만큼 새거나 겹친다.")
        return 1
    print("✅ 중복·누락 0")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default="data/recentchanges-164",
                   help="batch.recentchanges 수집본 루트")
    p.add_argument("--wiki", default="enwiki")
    p.add_argument("--out", default="data/rc-candidates-164")
    p.add_argument("--shard-records", type=int, default=DEFAULT_SHARD_RECORDS)
    p.add_argument("--dry-run", action="store_true", help="적재 없이 세기만")
    p.add_argument("--verify-seam", metavar="DUMP",
                   help="덤프 꼬리 파일(2026-08.enwiki.2026-09.tsv.bz2)과 "
                        "이음매를 대조한다. 적재는 하지 않는다")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    root = Path(args.root) / args.wiki
    if not root.is_dir():
        print(f"수집본이 없다: {root}", file=sys.stderr)
        return 2

    # 🔴 이벤트를 리스트로 모으지 않는다. 구간 전체가 180만 건이라 dict 로 들면
    #    수 GB 다. 세는 값은 흘려보내면서 같이 센다.
    if args.verify_seam:
        return verify_seam(root, Path(args.verify_seam), args.wiki)

    read = kept = bots = 0

    def counted() -> Iterator[dict]:
        nonlocal read, kept, bots
        for rec in read_raw(root):
            read += 1
            if not is_edit_record(rec):
                continue
            kept += 1
            event = to_edit_event(rec, args.wiki)
            if event["is_bot"]:
                bots += 1
            yield event

    aggregates = aggregate_edits(counted())
    rows = candidate_rows(aggregates)
    titles = {(r["wiki"], r["title"]) for r in rows}

    print(f"읽음 {read:,} · 편집 {kept:,} · 봇 {bots:,} "
          f"({100.0 * bots / kept if kept else 0:.1f}%)")
    print(f"candidate 윈도우 {len(rows):,} · candidate title {len(titles):,}")
    if rows:
        print(f"구간 {rows[0]['window_start']} ~ {rows[-1]['window_start']}")

    if args.dry_run:
        return 0

    out_dir = Path(args.out) / args.wiki
    shards = write_rows(rows, out_dir, args.shard_records)
    manifest = {
        "issue": "WP-164",
        "wiki": args.wiki,
        "source": RC_SOURCE,
        # ⚠️ 덤프는 사건 당시 제목이다. 지우지 말 것 (모듈 docstring).
        "title_basis": "current",
        "rows_read": read,
        "edits": kept,
        "bot_edits": bots,
        "windows": len(rows),
        "titles": len(titles),
        "window_start_first": rows[0]["window_start"] if rows else None,
        "window_start_last": rows[-1]["window_start"] if rows else None,
        "shards": shards,
        "shard_records": args.shard_records,
        "generated_at": datetime.now(timezone.utc).strftime(TS),
    }
    (out_dir / "_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"적재 완료: {out_dir}  shard {len(shards)}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
