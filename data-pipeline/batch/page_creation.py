"""mediawiki_history 에서 `title -> 문서 생성일` 인덱스를 뽑는다. WP-115.

    python -m batch.page_creation --wiki enwiki --range 2024-09 --range 2024-10
    python -m batch.page_creation --wiki enwiki --range 2024-09 --dry-run   # 세기만

`cluster/snapshot.py` 의 생성일 창 게이트(§3.2 4번, WP-51)가 이웃마다
`created_at` 을 요구하는데, 그 값을 주는 소스가 파이프라인에 없었다 —
`cluster/driver.load_creation_dates` 가 `NotImplementedError` 골격이었던 자리다.
이 모듈이 그 소스다.

🔴 **판정 규칙을 만들지 않는다.** 여기서 하는 일은 추출뿐이다. "며칠 안이면 같은
    이슈인가" 는 전부 `snapshot.py` 가 정한다(`DEFAULT_CREATION_WINDOW_DAYS`).
    이 모듈에 임계값이 없는 것이 정상이다.

왜 덤프에서 뽑나 (2026-09-17 확인)
    - `wiki_page` 에 생성일 컬럼이 **없다**(V1). `first_seen` 은 적재 시각이라 무관하다.
    - `-56` 의 edit_event 15필드에 `page_creation_timestamp` 가 **없다**.
    - `-58` 의 윈도우 샤드는 `{wiki,title,window_start,hour_of_day,edit_count,
      editor_count,views}` 뿐이다.
    → 남는 소스는 덤프 원본 컬럼 하나뿐이다. `batch/schema.py` 의 78컬럼에
      `page_creation_timestamp` 가 이미 정의돼 있어 위치만 꺼내면 된다.

✅ **revision 행에도 생성일이 실려 있다.** 그래서 "그 달에 생성된 문서" 가 아니라
    **"그 달에 편집된 모든 문서"** 의 생성일을 얻는다 — 2005년에 생긴 문서라도
    2024-09 에 한 번 편집됐으면 인덱스에 들어온다. 생성월 덤프를 따로 받을 필요가 없다.

⚠️ **없는 제목은 "옛 문서" 가 아니라 "미상" 이다.** 그 달에 한 번도 편집되지 않은
    문서는 인덱스에 없다. `created_at=None` 은 게이트에서 탈락하는데
    (`_within_creation_window` 가 None 을 False 로 본다), 그건 "창 밖" 이라는
    판정이 아니라 "근거 없음" 이다. 둘을 같은 것으로 보고 커버리지를 안 재면
    게이트가 조용히 대부분을 떨어뜨린다 — 소비하는 쪽이 resolve 율을 보고해야 한다.

🔴 같은 제목에 생성일이 여러 개 나온다 — **마지막으로 그 제목을 가진 페이지**를 쓴다.
    enwiki 2024-09+10 에서 충돌이 47,746건이었다(2026-09-17 실측). 사건 문서는 사건
    도중 이동(rename)되는 일이 흔해서, 옛 문서가 쓰던 제목을 새 사건 문서가 물려받는다.

    ~~가장 이른 값을 남긴다~~ → **`event_timestamp` 가 가장 늦은 행의 생성일** (2026-09-17).
    이른 값을 고르면 `Hurricane Helene` 이 2006-01-07(옛 문서), `Typhoon Yagi` 가
    2023-06-06 으로 나왔다 — Wikipedia API 가 주는 실제 값은 2024-09-23·2024-09-01 이다.
    그 값으로는 **진짜 신규 사건 문서가 "옛 문서" 로 보여 생성일 창에서 탈락한다.**
    에러는 안 나고 멤버만 사라지는 유형이다.

    `(wiki, title)` 이 이 프로젝트의 자연키이고(V1), Clickstream 덤프도 제목으로
    문서를 가리킨다. 그러니 "이 제목이 지금 가리키는 문서" 가 맞는 해석이다.
    충돌 수는 매니페스트에 `title_conflicts` 로 남긴다.

제목 정규화는 `producer/normalize.canonical_title` 하나를 쓴다 (WP-79·-91).
덤프는 밑줄형이고 `wiki_page`·Clickstream 적재본은 공백형이다 — 여기서 맞춰야
`(wiki, title)` 자연키가 갈라지지 않는다.
"""

from __future__ import annotations

import argparse
import bz2
import gzip
import json
import shutil
import sys
import time
from collections.abc import Iterable, Iterator
from datetime import date, datetime
from pathlib import Path

from producer.normalize import ARTICLE_NAMESPACE, SkipEvent, canonical_title

from .ingest import Counts, MANIFEST_NAME, ShardWriter, download, dump_url, env
from .normalize_dump import DUMP_TIMESTAMP_FORMAT
from .schema import SchemaMismatch, field, split_row

#: 덤프 스냅샷. `-109` 가 쓴 것과 같은 값이라 같은 파일을 캐시에서 재사용한다.
DEFAULT_SNAPSHOT = "2026-08"

#: shard 하나에 담을 레코드 수. `-56`·`-81` 과 같은 잠정치.
DEFAULT_SHARD_RECORDS = 500_000


def creation_entry(row) -> tuple[str, date, datetime]:
    """덤프 행 하나에서 `(canonical 제목, 생성일, 이벤트 시각)` 을 꺼낸다.

    이벤트 시각은 제목 충돌을 가를 때만 쓴다 — 어느 페이지가 그 제목을 **마지막으로**
    가졌는지 (모듈 docstring 🔴).

    Raises:
        SkipEvent: 대상이 아닌 행. 오류가 아니라 정상적인 필터링이다.

    ⚠️ `event_entity` 로 거르지 않는다. `normalize_dump` 는 편집량을 세므로
        revision 행만 봐야 하지만, 여기는 "이 제목의 생성일" 이라 page 행도 같은
        값을 준다. 거르면 근거만 줄고 값은 안 바뀐다.
    """
    # 현재 값이 아니라 과거 시점 값을 쓴다 — `normalize_dump` 와 같은 이유다.
    # 삭제된 문서에서 현재 값이 비어 ns0 집계가 반토막 나는 것이 실측돼 있다.
    namespace = field(row, "page_namespace_historical")
    if namespace != str(ARTICLE_NAMESPACE):
        raise SkipEvent(f"namespace={namespace}")

    title = canonical_title(field(row, "page_title_historical"))
    if not title:
        raise SkipEvent("title 결측")

    raw = field(row, "page_creation_timestamp")
    if not raw:
        raise SkipEvent("page_creation_timestamp 결측")
    try:
        moment = datetime.strptime(raw, DUMP_TIMESTAMP_FORMAT)
    except ValueError:
        # 덤프에 드물게 깨진 타임스탬프가 있다. 지어내지 않고 버린다.
        raise SkipEvent("page_creation_timestamp 형식")

    raw_event = field(row, "event_timestamp")
    if not raw_event:
        raise SkipEvent("event_timestamp 결측")
    try:
        event_at = datetime.strptime(raw_event, DUMP_TIMESTAMP_FORMAT)
    except ValueError:
        raise SkipEvent("event_timestamp 형식")

    return title, moment.date(), event_at


def scan(source: Path, index: dict[str, tuple[date, datetime]], counts: Counts) -> int:
    """덤프 하나를 훑어 `index` 에 `(생성일, 근거 이벤트 시각)` 을 채운다.

    반환: 제목 충돌 수. 500 MB 를 통째로 올리지 않으려고 줄 단위로 흘린다
    (`batch/ingest.convert` 와 같다).

    여러 덤프를 이어서 부를 수 있다 — 같은 `index` 를 넘기면 누적된다. 월 경계에서
    같은 제목이 다시 나와도 `event_timestamp` 비교라 순서와 무관하게 같은 값이 남는다.
    """
    conflicts = 0
    with bz2.open(source, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            counts.read += 1
            try:
                title, created, event_at = creation_entry(split_row(line))
            except SkipEvent as skipped:
                counts.skip(str(skipped))
                continue
            seen = index.get(title)
            if seen is None:
                index[title] = (created, event_at)
                counts.written += 1
                continue
            seen_created, seen_at = seen
            if seen_created != created:
                # 이동·재생성으로 제목 주인이 바뀐 경우. 늦은 쪽이 현재 주인이다.
                conflicts += 1
            if event_at > seen_at:
                index[title] = (created, event_at)
    return conflicts


def write_index(
    index: dict[str, tuple[date, datetime] | date], out_dir: Path, shard_records: int
) -> list[str]:
    """제목순으로 정렬해 JSONL.gz shard 로 쓴다.

    정렬해 두면 같은 입력이 같은 바이트를 내서 재실행 비교가 쉽다
    (`ShardWriter` 가 gzip mtime 을 0 으로 고정한 것과 같은 이유).
    """
    with ShardWriter(out_dir, shard_records) as writer:
        for title in sorted(index):
            entry = index[title]
            # `scan` 은 (생성일, 근거 시각) 을 담지만 적재본에는 생성일만 남긴다 —
            # 소비 쪽(창 게이트)이 쓰는 값이 그것뿐이라 근거 시각은 버린다.
            created = entry[0] if isinstance(entry, tuple) else entry
            writer.write({"title": title, "created": created.isoformat()})
        return writer.shards


def read_index(directory: str | Path) -> Iterator[tuple[str, date]]:
    """적재본을 `(제목, 생성일)` 로 되읽는다. 소비는 `cluster/driver.py`."""
    directory = Path(directory)
    for shard in sorted(directory.glob("part-*.jsonl.gz")):
        with gzip.open(shard, "rt", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                rec = json.loads(line)
                yield rec["title"], date.fromisoformat(rec["created"])


def creation_dates_for(
    directory: str | Path, titles: Iterable[str]
) -> dict[str, date]:
    """찾는 제목들의 생성일만 골라 돌려준다. 인덱스를 한 번만 순회한다.

    인덱스가 수백만 행이라 통째로 dict 에 올리지 않는다 — 후보 집합으로 거른다.
    없는 제목은 **키 자체가 없다**(None 을 넣지 않는다). 호출자가
    "미상" 과 "창 밖" 을 구분해 셀 수 있어야 하기 때문이다(모듈 docstring ⚠️).
    """
    wanted = set(titles)
    found: dict[str, date] = {}
    for title, created in read_index(directory):
        if title in wanted:
            found[title] = created
    return found


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="mediawiki_history → title 별 문서 생성일 인덱스 (WP-115)")
    p.add_argument("--wiki", default="enwiki")
    p.add_argument("--range", dest="ranges", action="append", required=True,
                   help="덤프 구간 YYYY-MM. 여러 번 줄 수 있다 (합쳐 한 인덱스가 된다)")
    p.add_argument("--snapshot", default=DEFAULT_SNAPSHOT,
                   help=f"덤프 스냅샷 (기본 {DEFAULT_SNAPSHOT} — -109 와 같은 파일)")
    p.add_argument("--out", default=env("PAGE_CREATION_OUT", "./data/page-creation"))
    p.add_argument("--cache", default=env("DUMP_CACHE", "./dumps"))
    p.add_argument("--shard-records", type=int, default=DEFAULT_SHARD_RECORDS)
    p.add_argument("--dry-run", action="store_true", help="적재 없이 세기만")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    out_dir = Path(args.out) / args.wiki / "_".join(args.ranges)
    manifest = out_dir / MANIFEST_NAME
    if manifest.exists() and not args.dry_run:
        print(f"이미 적재됨: {manifest} (건너뛴다)")
        return 0

    index: dict[str, tuple[date, datetime]] = {}
    counts = Counts()
    conflicts = 0
    started = time.monotonic()

    for time_range in args.ranges:
        cache = Path(args.cache) / f"{args.snapshot}.{args.wiki}.{time_range}.tsv.bz2"
        try:
            dump = download(dump_url(args.snapshot, args.wiki, time_range), cache)
            conflicts += scan(dump, index, counts)
        except SchemaMismatch as mismatch:
            # 위치가 하나만 밀려도 전부 틀린 값이 된다. 조용히 넘기지 않는다.
            print(f"스키마 불일치 — 덤프 컬럼이 바뀌었을 수 있다: {mismatch}",
                  file=sys.stderr)
            return 2
        print(f"  {time_range}: 누적 제목 {len(index):,}개 "
              f"(읽음 {counts.read:,})")

    elapsed = time.monotonic() - started
    if args.dry_run:
        print(f"[dry-run] read={counts.read:,} titles={len(index):,} "
              f"conflicts={conflicts:,} skipped={counts.skipped} {elapsed:.1f}s")
        return 0

    # 형제 .partial 에 다 쓴 뒤 통째로 rename — 반쪽 출력이 완료본으로 안 보이게.
    staging = out_dir.with_name(out_dir.name + ".partial")
    if staging.exists():
        shutil.rmtree(staging)
    shards = write_index(index, staging, args.shard_records)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    staging.rename(out_dir)

    (out_dir / MANIFEST_NAME).write_text(
        json.dumps({"wiki": args.wiki, "snapshot": args.snapshot,
                    "ranges": args.ranges, "shards": shards,
                    "titles": len(index), "title_conflicts": conflicts,
                    "read": counts.read, "written": counts.written,
                    "skipped": counts.skipped,
                    "elapsed_seconds": round(elapsed, 1)},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    print(f"적재 완료: {out_dir}  제목 {len(index):,}개  충돌 {conflicts:,}  "
          f"{elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
