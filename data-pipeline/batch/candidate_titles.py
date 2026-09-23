"""후보 문서 제목 추출 — 시간별 조회수를 받을 대상을 정한다 (WP-137).

    python -m batch.candidate_titles --edits ./out/enwiki/2026-07 --out ./data/candidate-titles
    python -m batch.candidate_titles --edits ./out/enwiki/2026-07 --out ... --dry-run
    python -m batch.candidate_titles --edits ./out/enwiki/2026-07 --out ... \
        --since 2026-07-17 --until 2026-07-31

무엇을 푸는가
    2단계 계약(§3.2 2~3번)에서 조회수를 봐야 하는 건 **1단계를 통과한 문서**뿐이다 —
    그 시간에 사람의 편집이 1건 이상 난 문서. `other/pageviews` 시간별 덤프는 enwiki
    ns0 만 시간당 약 190만 행이라(2026-09-18 실측) 전수 적재하면 고정 2개월이 28억 행이
    된다. `batch.pageview_hourly_ingest --titles` 가 그 필터를 받는데, **그 파일을 만드는
    공식 경로가 없었다.** 이 모듈이 그 자리다.

🔴 **필터는 시간별이다 — 기간 전체의 합집합이 아니다.**
    "이 기간에 한 번이라도 편집된 문서" 로 뭉치면 필터가 수백만 제목이 되어 시간당
    100만 행이 남는다. 1단계는 **그 윈도우의** 편집을 보므로 시간마다 다른 집합이다.
    `spike/live_cycle.py` 가 `spike_candidate`(page, window_start)로 하는 것과 같은 입도다.

🔴 **제목을 골라 담지 않는다.** 입력 샤드에 있는 편집을 전부 본다. 특정 사건·문서를
    지정하는 인자는 없고, 앞으로도 두지 않는다 — 두는 순간 리플레이가 "심어 둔 사건
    재생" 이 된다(`spike/bulk_replay.py` 독스트링과 같은 이유).

필터는 상류와 같은 것을 쓴다
    ns0·revision·EDIT_TYPES 는 적재(`batch/normalize_dump.py`)가 이미 걸러서 샤드에
    남지 않는다. 여기서 더 하는 건 **봇 제외** 하나이고, 그 판정은
    `historical_windows.is_bot_edit` 을 그대로 부른다 — 집계와 갈리면 조회수를 받은
    문서 집합과 판정 대상 문서 집합이 어긋나고, 에러 없이 `views=None` 만 늘어난다.
    제목도 `canonical_title` 을 읽는 지점에서 통과시킨다 (WP-79·-92).

출력
    {out}/{wiki}/{YYYY-MM-DD}/{HH}.txt   canonical 공백형 제목, 한 줄에 하나(정렬)
    {out}/{wiki}/_manifest.json          입력·시간 수·제목 수·읽은 행 수
    파일 형식은 `pageview_hourly_ingest.load_titles` 가 읽는 그대로다.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Iterable, Iterator
from datetime import date
from pathlib import Path

from producer.normalize import canonical_title

from .historical_windows import floor_to_hour, is_bot_edit
from .historical_windows_ingest import read_jsonl_shards

MANIFEST_NAME = "_manifest.json"


def candidates_by_hour(
    edit_events: Iterable[dict], *,
    since: date | None = None, until: date | None = None,
) -> tuple[dict[str, set[str]], int, int]:
    """edit_event → {정각 ts: {canonical 제목}}. 반환: (집합, 읽은 행, 봇 제외 수).

    since/until 은 날짜 경계 포함. 샤드는 월 단위라 리플레이 구간이 월 중간에서
    시작·끝날 때 여기서 자른다.
    """
    by_hour: dict[str, set[str]] = defaultdict(set)
    read = bots = 0
    for rec in edit_events:
        read += 1
        if is_bot_edit(rec):
            bots += 1
            continue
        hour = floor_to_hour(rec["event_ts"])
        day = date.fromisoformat(hour[:10])
        if since is not None and day < since:
            continue
        if until is not None and day > until:
            continue
        by_hour[hour].add(canonical_title(rec["title"]))
    return dict(by_hour), read, bots


def write_hours(by_hour: dict[str, set[str]], root: Path, wiki: str) -> int:
    """시간마다 {YYYY-MM-DD}/{HH}.txt 를 쓴다. 반환: 쓴 제목 총수."""
    total = 0
    for hour, titles in by_hour.items():
        out_dir = root / wiki / hour[:10]
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{hour[11:13]}.txt").write_text(
            "\n".join(sorted(titles)) + "\n", encoding="utf-8")
        total += len(titles)
    return total


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="시간별 후보 문서 제목 추출 (WP-137)")
    p.add_argument("--edits", required=True, help="편집 적재본 디렉터리 (-56)")
    p.add_argument("--out", required=True, help="후보 제목 출력 루트")
    p.add_argument("--wiki", default="enwiki")
    p.add_argument("--since", help="시작 날짜(포함) YYYY-MM-DD")
    p.add_argument("--until", help="끝 날짜(포함) YYYY-MM-DD")
    p.add_argument("--dry-run", action="store_true", help="쓰지 않고 세기만")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    edits_dir = Path(args.edits)
    if not edits_dir.exists():
        print(f"--edits 경로 없음: {edits_dir}", file=sys.stderr)
        return 2

    since = date.fromisoformat(args.since) if args.since else None
    until = date.fromisoformat(args.until) if args.until else None

    events: Iterator[dict] = read_jsonl_shards(edits_dir, "part-*.jsonl.gz")
    by_hour, read, bots = candidates_by_hour(events, since=since, until=until)

    hours = len(by_hour)
    titles = sum(len(v) for v in by_hour.values())
    unique = len(set().union(*by_hour.values())) if by_hour else 0

    if args.dry_run:
        print(f"[dry-run] 시간 {hours:,} · 후보(시간×문서) {titles:,} · "
              f"고유 문서 {unique:,} · 읽음 {read:,} · 봇 제외 {bots:,}")
        return 0

    root = Path(args.out)
    written = write_hours(by_hour, root, args.wiki)

    manifest_path = root / args.wiki / MANIFEST_NAME
    prior = {}
    if manifest_path.exists():
        prior = json.loads(manifest_path.read_text(encoding="utf-8"))
    runs = prior.get("runs", [])
    runs.append({
        "issue": "WP-137", "edits": str(edits_dir),
        "since": args.since, "until": args.until,
        "rows_read": read, "bot_skipped": bots,
        "hours": hours, "candidate_pairs": written, "unique_titles": unique,
    })
    manifest_path.write_text(
        json.dumps({"wiki": args.wiki, "runs": runs}, ensure_ascii=False, indent=2)
        + "\n", encoding="utf-8")

    print(f"후보 제목 생성: {root / args.wiki}  시간 {hours:,} · "
          f"후보(시간×문서) {written:,} · 고유 문서 {unique:,} · "
          f"읽음 {read:,} · 봇 제외 {bots:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
