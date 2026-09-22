"""`other/pageviews` 시간별 덤프를 받아 적재한다 (WP-127).

    python -m batch.pageview_hourly_ingest --date 2025-06-12                 # 하루 24시간
    python -m batch.pageview_hourly_ingest --hour 2025-06-12T09               # 한 시간만
    python -m batch.pageview_hourly_ingest --date 2025-06-12 --dry-run        # 세기만
    python -m batch.pageview_hourly_ingest --hour 2026-09-18T04 --titles cand.txt
    python -m batch.pageview_hourly_ingest --hour 2026-09-18T04 --dsn "$DATABASE_URL"

🔴 **이 소스가 2단계 최종 관문이다** (명세 §3.2 3번). 일별 `pageview_complete`
(`batch/pageview_ingest.py`)는 하루가 끝나야 나와 LIVE 판정에 못 쓴다.

**후보 문서로 거르는 게 정상 경로다.** enwiki ns0 만 시간당 약 190만 행이라(2026-09-18
실측) 전부 담으면 하루 4,500만 행·고정 2개월 28억 행이다. 2단계 계약에서 조회수를 봐야
하는 건 1단계(사람 편집 1건 이상)를 통과한 문서뿐이므로 `--titles` 로 그 집합을 준다.
파일은 canonical 공백형 제목 한 줄에 하나다. 안 주면 전부 적재한다 — 품질 측정·전수
비교용이고, 그 크기를 알고 쓰라는 뜻이다.

출력은 두 갈래이고 같이 쓸 수 있다.
    JSONL.gz shard : `--out` 아래 `{wiki}/{date}/{HH}/`. 매니페스트가 있으면 건너뛴다
    PostgreSQL     : `--dsn` 을 주면 `page_view_hourly` 로 upsert (재실행 안전)

⚠️ 아직 없는 시간은 404 다 — 결손이 아니라 **아직 안 나온 것**이다. 2026-09-18 실측에서
   [03:00~04:00) 구간 파일이 06:06Z 에 올라왔다 — 윈도우 **끝 기준 약 2시간**이다
   (125~134분, 4개 구간). 그래서 404 를 실패로 세지 않고 "대기" 로 따로 센다 —
   LIVE 스케줄러가 재시도할 자리다.
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sys
import time
import urllib.error
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .ingest import MANIFEST_NAME, Counts, ShardWriter, download, env
from .pageview import SchemaMismatch
from .pageview_hourly import aggregate, filename_hour, ts_hour_from_filename

PAGEVIEW_HOURLY_BASE = "https://dumps.wikimedia.org/other/pageviews"

#: shard 크기. 시간당 enwiki ns0 이 약 190만 행이라(필터 없이) 일별 적재와 같은 값을 쓴다.
DEFAULT_SHARD_RECORDS = 500_000

#: `page_view_hourly` 는 (page_id, ts_hour) 가 PK 다(V1). 같은 시간을 다시 받으면 값만 갱신한다.
#: `mobile_views` 는 V16 (WP-210) — views 에 포함된 부분집합이다.
UPSERT_VIEW_SQL = """
INSERT INTO page_view_hourly (page_id, ts_hour, views, mobile_views)
VALUES (%s, %s, %s, %s)
ON CONFLICT (page_id, ts_hour) DO UPDATE SET views = EXCLUDED.views,
                                             mobile_views = EXCLUDED.mobile_views
"""

#: 캐시 보존 시간. `live-cycle`의 `--max-hours`(기본 6)와 candidate 36시간 만료를
#: 합쳐도 이 값을 넘지 않는다 — 그래서 이보다 오래된 캐시는 다시 읽힐 일이 없다.
DEFAULT_CACHE_MAX_AGE_HOURS = 48


def dump_url(ts_hour: str) -> str:
    """윈도우 **시작** → 그 구간을 담은 파일 URL.

    🔴 파일명 시각은 윈도우 **끝**이다 (`batch/pageview_hourly` 모듈 독스트링).
       `2025-06-12T08:00:00` 구간은 `pageviews-20250612-090000.gz` 에 들어 있다.
       ~~시작 시각을 그대로 파일명에 넣었다~~ → 한 시간 뒤 파일을 받아 조회수가 통째로
       밀렸다 (2026-09-18 실측으로 발견).
    """
    date, hour = filename_hour(ts_hour)
    return (f"{PAGEVIEW_HOURLY_BASE}/{date[:4]}/{date[:4]}-{date[4:6]}/"
            f"pageviews-{date}-{hour}0000.gz")


def prune_cache(cache_dir: Path, *, max_age_hours: int = DEFAULT_CACHE_MAX_AGE_HOURS,
                 now: float | None = None) -> int:
    """`max_age_hours` 보다 오래된 원본 캐시(`pageviews-*.gz`)를 지운다. 반환: 지운 개수.

    `download()`가 남기는 캐시는 같은 시간을 다시 요청할 때 재다운로드를 피하려고
    있다(그쪽 독스트링). 그 재사용 창을 넘긴 파일은 이미 `page_view_hourly`에
    필요한 조각이 다 들어갔고 다시 읽힐 일이 없다 — LIVE 원본 정리 로직 부재
    (`infra/live-cycle/README.md` "지우는 코드는 없다") 를 메운다.

    ⚠️ `.partial` 로 끝나는 미완료 다운로드는 지우지 않는다 — 진행 중일 수 있다.
    """
    cutoff = (now if now is not None else time.time()) - max_age_hours * 3600
    removed = 0
    for dump in cache_dir.glob("pageviews-*.gz"):
        try:
            if dump.stat().st_mtime < cutoff:
                dump.unlink()
                removed += 1
        except FileNotFoundError:
            pass
    return removed


def read_lines(path: Path):
    """gz 를 텍스트 줄로 흘려보낸다. 깨진 바이트는 대체한다 — 한 줄 때문에 멈추지 않는다."""
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
        yield from handle


def hours_of_day(date: str) -> list[str]:
    """`YYYY-MM-DD` → 그날 24시간의 ts_hour 목록."""
    return [f"{date}T{hour:02d}:00:00" for hour in range(24)]


def normalize_hour(value: str) -> str:
    """`2025-06-12T09` · `2025-06-12T09:00` · `2025-06-12 09:00:00` → `2025-06-12T09:00:00`."""
    text = value.strip().replace(" ", "T")
    date, _, time_part = text.partition("T")
    if not time_part:
        raise SystemExit(f"--hour 는 YYYY-MM-DDTHH 형식이다 (받은 값: {value!r})")
    return f"{date}T{time_part[:2]}:00:00"


def load_titles(path: Path | None) -> frozenset[str] | None:
    """후보 제목 파일 → 집합. 한 줄에 제목 하나, canonical 공백형.

    ⚠️ 밑줄형을 주면 한 건도 안 걸리는데 그게 "조회수 0" 으로 읽힌다. 여기서 막지 않는
    이유는 밑줄이 들어간 정상 제목과 구분할 방법이 없어서다 — 파일을 만드는 쪽이
    `canonical_title` 을 거친 값을 쓴다(명세 §5.1).
    """
    if path is None:
        return None
    titles = {line.strip() for line in path.read_text(encoding="utf-8").splitlines()}
    titles.discard("")
    if not titles:
        raise SystemExit(f"후보 제목 파일이 비었다: {path}")
    return frozenset(titles)


def ingest_hour(
    ts_hour: str, wiki: str, cache_dir: Path, out_root: Path, *,
    titles: frozenset[str] | None, shard_records: int, dry_run: bool, conn=None,
) -> str:
    """한 시간을 적재한다. 반환: "ok" | "skip"(이미 적재) | "pending"(아직 안 나옴).

    SchemaMismatch 는 잡지 않고 위로 던진다 — 형식 손상은 전체 실행을 멈춰야 한다.
    """
    out_dir = out_root / wiki / ts_hour[:10] / ts_hour[11:13]
    if (out_dir / MANIFEST_NAME).exists() and not dry_run and conn is None:
        print(f"이미 적재됨: {ts_hour} (건너뛴다)")
        return "skip"

    url = dump_url(ts_hour)
    cache = cache_dir / Path(url).name
    try:
        dump = download(url, cache)
    except urllib.error.HTTPError as err:
        if err.code == 404:
            # 결손이 아니라 아직 안 나온 것이다 (모듈 독스트링 ⚠️).
            print(f"대기: {ts_hour} 파일이 아직 없다 (404)")
            return "pending"
        raise

    # 🔴 시각은 파일명에서 다시 읽는다. 캐시 파일이 엉뚱해도 여기서 드러난다.
    #    파일명은 윈도우 끝이라 ts_hour_from_filename 이 한 시간을 빼서 돌려준다.
    if ts_hour_from_filename(dump.name) != ts_hour:
        raise SchemaMismatch(
            f"파일명 시각({ts_hour_from_filename(dump.name)})이 요청({ts_hour})과 다르다")

    counts = Counts()
    records = []
    for rec in aggregate(read_lines(dump), wiki, ts_hour, titles=titles):
        counts.read += 1
        records.append(rec)

    if dry_run:
        total = sum(r.views for r in records)
        print(f"[dry-run] {ts_hour} 문서 {len(records):,} · 조회수 {total:,}")
        return "ok"

    if conn is not None:
        written = load_to_db(conn, records)
        # 🔴 **적재했다는 사실을 남긴다** (WP-199). 이게 없으면 조회수 0 인
        #    문서와 아직 안 온 시간이 구분되지 않는다 — 덤프가 0회 문서를 아예 안
        #    싣기 때문에 둘 다 "page_view_hourly 에 행 없음" 으로 보인다.
        #    ⚠️ written 이 0 이어도 기록한다. LIVE 는 대기 목록의 문서만 받으므로
        #    그 시간 후보가 전부 0회면 0행이 정상이다.
        record_ingest(conn, wiki, ts_hour, written)
        print(f"DB 적재 {ts_hour}: {written:,}행")

    staging = out_dir.with_name(out_dir.name + ".partial")
    if staging.exists():
        shutil.rmtree(staging)
    with ShardWriter(staging, shard_records) as writer:
        for rec in records:
            writer.write(asdict(rec))
            counts.written += 1

    if out_dir.exists():
        shutil.rmtree(out_dir)
    staging.rename(out_dir)
    (out_dir / MANIFEST_NAME).write_text(
        json.dumps({"wiki": wiki, "ts_hour": ts_hour, "source": "other/pageviews",
                    "filtered": titles is not None,
                    "shards": writer.shards, "records": counts.written,
                    "views_total": sum(r.views for r in records)},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"적재 {ts_hour}: 문서 {counts.written:,} · 조회수 {sum(r.views for r in records):,}")
    return "ok"


#: 적재 원장 upsert (V14). 재적재하면 행 수·시각만 갱신한다.
RECORD_INGEST_SQL = """
INSERT INTO page_view_hourly_ingest (wiki, ts_hour, rows, ingested_at)
VALUES (%s, %s, %s, now())
ON CONFLICT (wiki, ts_hour) DO UPDATE
   SET rows = EXCLUDED.rows, ingested_at = EXCLUDED.ingested_at
"""


def record_ingest(conn, wiki: str, ts_hour: str, rows: int) -> None:
    """이 (wiki, 시간) 을 실제로 받아 적재했다고 남긴다 (WP-199).

    🔴 **행 수가 아니라 행의 존재가 신호다.** `rows=0` 도 "도착했고, 그 시간 후보가
    전부 0회였다" 는 완전한 사실이다. 읽는 쪽이 `rows > 0` 을 조건으로 쓰면 그
    경우를 미도착으로 오인한다 — 지금 고치려는 버그와 같은 형태다.
    """
    with conn.cursor() as cur:
        cur.execute(RECORD_INGEST_SQL, (wiki, ts_hour, rows))
    conn.commit()


def load_to_db(conn, records) -> int:
    """`page_view_hourly` 로 upsert 한다. 반환: 쓴 행 수.

    문서는 `wiki_page` 에 없으면 만든다 — 조회수가 편집보다 먼저 도착할 수 있다
    (`spike/baseline_sink.resolve_page_ids` 와 같은 규칙).
    """
    from spike.baseline_sink import resolve_page_ids

    if not records:
        return 0
    with conn.cursor() as cur:
        page_ids = resolve_page_ids(cur, [(r.wiki, r.title) for r in records])
        cur.executemany(UPSERT_VIEW_SQL, [
            (page_ids[(r.wiki, r.title)], r.ts_hour, r.views, r.mobile_views)
            for r in records
        ])
    conn.commit()
    return len(records)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="other/pageviews 시간별 덤프 적재 (WP-127)")
    p.add_argument("--wiki", default="enwiki")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--date", help="하루 24시간: YYYY-MM-DD")
    group.add_argument("--hour", help="한 시간만: YYYY-MM-DDTHH")
    group.add_argument("--latest", type=int, metavar="N",
                       help="지금부터 과거 N시간 (LIVE 따라잡기용). 아직 안 나온 시간은 대기")
    p.add_argument("--titles", type=Path,
                   help="후보 제목 파일(canonical 공백형, 한 줄에 하나). 없으면 전부 적재")
    p.add_argument("--out", default=env("PAGEVIEW_HOURLY_OUT", "./data/pageview-hourly"))
    p.add_argument("--cache", default=env("DUMP_CACHE", "./data/cache"))
    p.add_argument("--dsn", default=env("DATABASE_URL"),
                   help="주면 page_view_hourly 에도 upsert 한다")
    p.add_argument("--shard-records", type=int, default=DEFAULT_SHARD_RECORDS)
    p.add_argument("--dry-run", action="store_true", help="적재 없이 세기만")
    return p


def target_hours(args) -> list[str]:
    if args.date:
        return hours_of_day(args.date)
    if args.hour:
        return [normalize_hour(args.hour)]
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return [f"{(now - timedelta(hours=back)):%Y-%m-%dT%H}:00:00"
            for back in range(args.latest, 0, -1)]


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    titles = load_titles(args.titles)
    out_root = Path(args.out)
    cache_dir = Path(args.cache)
    cache_dir.mkdir(parents=True, exist_ok=True)

    conn = None
    if args.dsn and not args.dry_run:
        import psycopg      # DB 경로에서만 필요 — 샤드만 쓸 때는 드라이버 없이 돈다

        conn = psycopg.connect(args.dsn)

    tally = {"ok": 0, "skip": 0, "pending": 0}
    try:
        for ts_hour in target_hours(args):
            tally[ingest_hour(ts_hour, args.wiki, cache_dir, out_root,
                              titles=titles, shard_records=args.shard_records,
                              dry_run=args.dry_run, conn=conn)] += 1
    except SchemaMismatch as mismatch:
        print(f"스키마 불일치 — 덤프 형식이 바뀌었을 수 있다: {mismatch}", file=sys.stderr)
        return 2
    finally:
        if conn is not None:
            conn.close()

    removed = prune_cache(cache_dir)
    if removed:
        print(f"캐시 정리: {removed}개 삭제 ({DEFAULT_CACHE_MAX_AGE_HOURS}시간 초과)")

    print(f"요약: 적재 {tally['ok']} · 건너뜀 {tally['skip']} · 대기 {tally['pending']}")
    # 대기(아직 안 나온 시간)만 남은 것은 실패가 아니다 — 다음 실행에서 받는다.
    return 0 if (tally["ok"] or tally["skip"]) else 3


if __name__ == "__main__":
    sys.exit(main())
