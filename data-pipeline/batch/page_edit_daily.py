"""mediawiki_history 에서 `title -> 날짜별 편집 수` 인덱스를 뽑는다. WP-145.

    python -m batch.page_edit_daily --wiki enwiki --range 2026-08 --range 2026-09
    python -m batch.page_edit_daily --wiki enwiki --range 2026-08 --dry-run   # 세기만

`cluster/snapshot.py` 의 비-씨드 재급증 게이트(WP-77·144)가 이웃마다
사건기간·기준기간 편집 수를 요구하는데, 그 값을 주는 소스가 파이프라인에 없었다.
이 모듈이 그 소스다. 소비는 `cluster/driver.py`.

🔴 **판정 규칙을 만들지 않는다.** 여기서 하는 일은 집계뿐이다. "비율 5배·절대 20건"
    과 "사건기간을 어디로 잡는가" 는 전부 `snapshot.py`·`driver.py` 가 정한다.
    이 모듈에 임계값이 없는 것이 정상이다.

왜 덤프인가 (WP-145 에서 후보 넷을 비교)
    - ❌ Wikimedia REST `metrics/edits/per-page` — POC(`ai/nonseed-resurgence-poc`)가
      쓴 것. 재급증 게이트는 생성일 창을 **떨어진** 후보에 도는데 그게 대다수라
      (Iran 1,331 중 1,330) 스냅샷당 수천 건 왕복이 된다.
    - ❌ `page_edit_window` — 단기 보존 스트리밍 산출물이고 `wiki_page` 에 등록된
      문서만 담는다. 배경 문서 60일치가 거기 없다.
    - ❌ `batch/historical_windows` 산출물 — `edit_count` 가 **봇 제외**라 쓸 수 없다.
      아래 🔴 참고.
    - ✅ mediawiki_history — `batch/page_creation` 이 생성일을 뽑는 바로 그 원본이다.
      필요한 컬럼이 전부 있고 후보당 왕복이 0 이다.

🔴 **봇을 거르지 않는다 — 파이프라인의 다른 편집 집계와 의도적으로 다르다.**
    `normalize_dump`·`historical_windows`·스트리밍은 전부 봇을 뺀다. 여기는 넣는다.
    목적이 다르기 때문이다 — 이슈 판정 1차 관문은 "사람이 손댔는가"를 묻고(§3.2),
    재급증은 "이 문서가 평소보다 얼마나 들썩였는가"를 묻는다.
    POC 실측: `user` 단독으로 재면 `Mojtaba_Khamenei` 가 1,053건에서 **5건**까지
    떨어져 신호 자체가 사라진다(`ai/nonseed-resurgence-poc/RESULT.md`).
    ⚠️ "다른 모듈과 통일" 하려는 정리가 이 신호를 죽인다. 바꾸기 전에 위 수치를 본다.

🔴 **`event_entity == revision` 행만 센다.** `page_creation` 은 일부러 안 거르지만
    (생성일은 page 행도 같은 값을 준다) 편집 수는 거르지 않으면 부풀려진다.
    enwiki 2026-07 실측(2026-09-20): 617만 행 중 **102만(16.6%)** 이 revision 이 아니고,
    추가로 161만이 ns0 밖이라 남는 편집이 354만이다.
    ⚠️ `normalize_dump` docstring 의 "편집이 아닌 행이 61%" 와 다르다 — 그쪽은 다른
    덤프 구간이거나 다른 세는 법(이 모듈은 event_entity 를 **먼저** 보므로 이 값이
    non-revision 의 순수 비율이다)이다. 두 수치를 같은 것으로 놓고 한쪽을 고치지 말 것.

⚠️ **없는 제목은 "편집 0건" 이 아니라 "미상" 이다.** 덤프 구간 밖이거나 적재하지 않은
    달의 문서는 인덱스에 없다. `creation_dates_for` 와 같은 계약으로 **키 자체를
    만들지 않는다** — 소비하는 쪽이 둘을 구분해 커버리지를 보고해야 한다. 0 으로
    뭉개면 기준기간이 0 이 되어 비율이 무한대가 되고, 인덱스 구멍이 "재급증" 으로
    위장된다.

🔴 **마지막 달은 잘려 있다 — 없는 것보다 위험하다** (2026-09-20 실측).
    스냅샷 `2026-08` 의 `2026-09` 파일은 3 MB 뿐이고 **2026-09-01 하루치**(ns0 편집
    24,378건)만 들어 있다. 다른 달은 500 MB 대다. 스냅샷을 뜨는 시점에 그 달이 막
    시작했기 때문이다.

    이걸 모르고 쓰면 사건기간이 데이터 끝을 넘는 문서에서 **편집 수가 과소 계수**되고,
    그 결과가 "재급증 미달로 탈락" 과 구분되지 않는다 — 진짜 재조명 문서를 조용히
    놓친다. 그래서 적재본에 실제 데이터 구간(`first_day`·`last_day`)을 남기고
    `coverage_until` 로 읽을 수 있게 한다. 소비하는 쪽(`cluster/driver.py`)이
    사건기간 끝이 그 날짜를 넘으면 판정하지 않고 **미상으로 센다.**

⚠️ **월 덤프는 공개가 늦다 — LIVE 에서는 아직 못 쓴다.** 사건기간이 최신 달이면
    덤프가 없어 재급증 판정이 통째로 미상이 된다. replay 구간에서 먼저 쓴다.

제목 표기는 canonical 공백형이다(§5.1, `producer/normalize.canonical_title`).
`page_creation` 인덱스와 같은 키여야 같은 이웃을 가리킨다.
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
from datetime import date, datetime, timezone
from pathlib import Path

from producer.normalize import ARTICLE_NAMESPACE, SkipEvent, canonical_title

from .ingest import Counts, MANIFEST_NAME, ShardWriter, download, dump_url, env
from .normalize_dump import DUMP_TIMESTAMP_FORMAT, REVISION_ENTITY
from .schema import SchemaMismatch, field, split_row

#: 덤프 스냅샷. `-109`·`-115` 와 같은 값이라 같은 파일을 캐시에서 재사용한다.
DEFAULT_SNAPSHOT = "2026-08"

#: shard 하나에 담을 레코드 수. `-56`·`-81`·`-115` 와 같은 잠정치.
DEFAULT_SHARD_RECORDS = 500_000


def _utc(raw: str) -> datetime:
    """덤프 타임스탬프 -> timezone-aware UTC. 형식이 다르면 ValueError."""
    return datetime.strptime(raw, DUMP_TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)


def edit_entry(row) -> tuple[str, date]:
    """덤프 행 하나에서 `(canonical 제목, 편집 날짜 UTC)` 를 꺼낸다.

    날짜까지만 남긴다. 재급증은 여러 주 구간을 비교하는 판정이라 시(hour) 정밀도가
    필요 없고, 날짜로 접으면 인덱스가 한 자릿수 배로 작아진다. 생성일
    (`page_creation`)이 시각을 보존하는 것과 대비되는데 이유가 다르다 — 거기는
    `생성 시각 <= snapshot_ts` 를 시 단위로 따져야 한다.

    Raises:
        SkipEvent: 대상이 아닌 행. 오류가 아니라 정상적인 필터링이다.
    """
    entity = field(row, "event_entity")
    if entity != REVISION_ENTITY:
        raise SkipEvent(f"event_entity={entity}")

    # 현재 값이 아니라 과거 시점 값을 쓴다 — `normalize_dump`·`page_creation` 과 같다.
    # 삭제된 문서에서 현재 값이 비어 ns0 집계가 반토막 나는 것이 실측돼 있다.
    namespace = field(row, "page_namespace_historical")
    if namespace != str(ARTICLE_NAMESPACE):
        raise SkipEvent(f"namespace={namespace}")

    title = canonical_title(field(row, "page_title_historical"))
    if not title:
        raise SkipEvent("title 결측")

    raw_event = field(row, "event_timestamp")
    if not raw_event:
        raise SkipEvent("event_timestamp 결측")
    try:
        moment = _utc(raw_event)
    except ValueError:
        # 덤프에 드물게 깨진 타임스탬프가 있다. 지어내지 않고 버린다.
        raise SkipEvent("event_timestamp 형식")

    # 🔴 is_bot 을 보지 않는다. 모듈 docstring 의 🔴 참고.
    return title, moment.date()


def scan(source: Path, index: dict[str, dict[date, int]], counts: Counts) -> None:
    """덤프 하나를 훑어 `index[title][날짜]` 편집 수를 누적한다.

    500 MB 를 통째로 올리지 않으려고 줄 단위로 흘린다(`batch/ingest.convert` 와 같다).
    여러 덤프를 이어서 부를 수 있다 — 같은 `index` 를 넘기면 누적된다.

    제목 충돌을 `page_creation` 처럼 다루지 않는다. 거기는 "이 제목의 주인이 누구냐"를
    가려야 해서 마지막 페이지를 골랐지만, 여기는 **그 제목으로 일어난 편집량**이
    알고 싶은 값이라 이동 전후를 합치는 것이 맞다. 재조명 판정의 대상은 제목이
    가리키는 주제이지 페이지 실체가 아니다.
    """
    with bz2.open(source, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            counts.read += 1
            try:
                title, day = edit_entry(split_row(line))
            except SkipEvent as skipped:
                counts.skip(str(skipped))
                continue
            per_day = index.setdefault(title, {})
            per_day[day] = per_day.get(day, 0) + 1
            counts.written += 1


def write_index(
    index: dict[str, dict[date, int]], out_dir: Path, shard_records: int
) -> list[str]:
    """제목순으로 정렬해 JSONL.gz shard 로 쓴다.

    한 줄이 한 제목이고 `days` 는 `"YYYY-MM-DD" -> 편집 수` 다. 날짜도 정렬해서 쓴다 —
    같은 입력이 같은 바이트를 내야 재실행 비교가 된다(`ShardWriter` 가 gzip mtime 을
    0 으로 고정한 것과 같은 이유).
    """
    with ShardWriter(out_dir, shard_records) as writer:
        for title in sorted(index):
            days = index[title]
            writer.write({
                "title": title,
                "days": {day.isoformat(): days[day] for day in sorted(days)},
            })
        return writer.shards


def read_index(directory: str | Path) -> Iterator[tuple[str, dict[date, int]]]:
    """적재본을 `(제목, {날짜: 편집 수})` 로 되읽는다. 소비는 `cluster/driver.py`."""
    directory = Path(directory)
    for shard in sorted(directory.glob("part-*.jsonl.gz")):
        with gzip.open(shard, "rt", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                rec = json.loads(line)
                try:
                    days = {date.fromisoformat(d): int(n)
                            for d, n in rec["days"].items()}
                except (ValueError, TypeError) as bad:
                    raise ValueError(
                        f"{shard}: 날짜별 편집 수를 못 읽었다 ({rec.get('days')!r})"
                    ) from bad
                yield rec["title"], days


def data_span(index: dict[str, dict[date, int]]) -> tuple[date | None, date | None]:
    """인덱스가 실제로 담은 첫·마지막 날짜. 요청한 range 와 다를 수 있다(위 🔴)."""
    days = [day for per_day in index.values() for day in per_day]
    return (min(days), max(days)) if days else (None, None)


def coverage_until(directory: str | Path) -> date | None:
    """적재본이 담은 **마지막 날짜**. 없으면 None.

    🔴 소비하는 쪽은 사건기간 끝이 이 날짜를 넘으면 **판정하지 않는다.** 넘는데도
    세면 잘린 구간의 편집이 0 으로 잡혀 진짜 재조명 문서가 "미달" 로 탈락한다 —
    에러 없이 놓치는 쪽으로 틀린다(모듈 docstring 🔴).

    옛 적재본에는 `last_day` 가 없다. 그때는 None 을 돌려주고, 소비 쪽이 "구간을
    모른다" 로 다루게 한다 — 날짜를 지어내지 않는다.
    """
    manifest = Path(directory) / MANIFEST_NAME
    if not manifest.exists():
        return None
    raw = json.loads(manifest.read_text(encoding="utf-8")).get("last_day")
    return date.fromisoformat(raw) if raw else None


def edit_days_for(
    directory: str | Path, titles: Iterable[str]
) -> dict[str, dict[date, int]]:
    """찾는 제목들의 날짜별 편집 수만 골라 돌려준다. 인덱스를 한 번만 순회한다.

    구간이 **씨드마다 다를 때** 쓴다 — 사건일이 씨드마다 달라서 하나의 고정 구간으로
    미리 합칠 수 없다(`cluster/driver.py`). 고정 구간이면 `edit_counts_for` 가 낫다.

    ⚠️ 없는 제목은 키 자체가 없다 — `edit_counts_for` 와 같은 계약이다.
    """
    wanted = set(titles)
    return {title: days for title, days in read_index(directory) if title in wanted}


def edit_counts_for(
    directory: str | Path,
    titles: Iterable[str],
    start: date,
    end: date,
) -> dict[str, int]:
    """찾는 제목들의 `[start, end)` 구간 편집 수 합을 돌려준다.

    구간은 **시작 포함·끝 제외** 다. 사건기간과 그 직전 기준기간을 맞물려 부를 때
    경계 하루가 양쪽에 들어가면 비율이 조용히 틀어진다.

    인덱스를 한 번만 순회한다 — 수백만 행이라 통째로 dict 에 올리지 않고 후보
    집합으로 거른다(`creation_dates_for` 와 같은 이유).

    ⚠️ **없는 제목은 키 자체가 없다.** 0 을 넣지 않는다 — 호출자가 "미상" 과
    "구간 편집 0건" 을 구분해 세야 하기 때문이다(모듈 docstring ⚠️).
    구간 안에 편집이 없었을 뿐 인덱스에 있는 제목은 `0` 이 들어간다.
    """
    if start >= end:
        raise ValueError(f"start < end 여야 한다: {start} ~ {end}")
    return {
        title: sum_days(days, start, end)
        for title, days in edit_days_for(directory, titles).items()
    }


def sum_days(days: dict[date, int], start: date, end: date) -> int:
    """`[start, end)` 구간 편집 수 합. 시작 포함·끝 제외 (위 함수 docstring)."""
    return sum(n for day, n in days.items() if start <= day < end)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="mediawiki_history → title 별 날짜별 편집 수 인덱스 "
                    "(봇 포함, WP-145)")
    p.add_argument("--wiki", default="enwiki")
    p.add_argument("--range", dest="ranges", action="append", required=True,
                   help="덤프 구간 YYYY-MM. 여러 번 줄 수 있다 (합쳐 한 인덱스가 된다)")
    p.add_argument("--snapshot", default=DEFAULT_SNAPSHOT,
                   help=f"덤프 스냅샷 (기본 {DEFAULT_SNAPSHOT} — -115 와 같은 파일)")
    p.add_argument("--out", default=env("PAGE_EDIT_DAILY_OUT", "./data/page-edit-daily"))
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

    index: dict[str, dict[date, int]] = {}
    counts = Counts()
    started = time.monotonic()

    for time_range in args.ranges:
        cache = Path(args.cache) / f"{args.snapshot}.{args.wiki}.{time_range}.tsv.bz2"
        try:
            dump = download(dump_url(args.snapshot, args.wiki, time_range), cache)
            scan(dump, index, counts)
        except SchemaMismatch as mismatch:
            # 위치가 하나만 밀려도 전부 틀린 값이 된다. 조용히 넘기지 않는다.
            print(f"스키마 불일치 — 덤프 컬럼이 바뀌었을 수 있다: {mismatch}",
                  file=sys.stderr)
            return 2
        print(f"  {time_range}: 누적 제목 {len(index):,}개 (읽음 {counts.read:,})")

    first, last = data_span(index)
    elapsed = time.monotonic() - started
    if args.dry_run:
        print(f"[dry-run] read={counts.read:,} titles={len(index):,} "
              f"edits={counts.written:,} skipped={counts.skipped} {elapsed:.1f}s")
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
                    "titles": len(index),
                    # 🔴 **요청한 range 가 아니라 실제로 본 날짜다.** 마지막 달이
                    #    잘려 있어도(위 🔴) range 목록만으로는 안 드러난다.
                    "first_day": first.isoformat() if first else None,
                    "last_day": last.isoformat() if last else None,
                    # 🔴 봇 포함이라는 사실을 적재본에 남긴다. 나중에 이 인덱스를
                    #    다른 집계와 비교할 때 규칙이 다르다는 걸 매니페스트만 보고
                    #    알 수 있어야 한다.
                    "editor_types": "all",
                    "read": counts.read, "edits": counts.written,
                    "skipped": counts.skipped,
                    "elapsed_seconds": round(elapsed, 1)},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    print(f"적재 완료: {out_dir}  제목 {len(index):,}개  편집 {counts.written:,}건  "
          f"{elapsed:.1f}s")
    print(f"  데이터 구간: {first} ~ {last}")
    if last is not None and args.ranges:
        # 마지막 range 의 달과 last_day 의 달이 같은데 날짜가 그 달 초면 잘린 것이다.
        if last.isoformat()[:7] == args.ranges[-1] and last.day <= 7:
            print(f"  🔴 마지막 달이 잘려 있다 — {args.ranges[-1]} 은 {last} 까지뿐이다. "
                  "사건기간이 이 날짜를 넘는 문서는 판정하지 않는다(소비 쪽이 미상으로 센다).",
                  file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
