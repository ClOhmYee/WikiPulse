"""LIVE 시간 주기 — 대기가 필요한 조회수만 받아 재판정한다 (WP-135).

    python -m spike.live_cycle --dsn "$DATABASE_URL"                 # 한 번 돌고 끝
    python -m spike.live_cycle --loop --interval 900                 # 15분마다
    python -m spike.live_cycle --dry-run                             # 받을 것만 보여준다

WP-127(시간별 적재)·-128(대기 보관·재판정)으로 부품은 있었지만 **그걸 돌리는 것이
없었다.** 사람이 두 명령을 손으로 쳐야 확정이 났다. 이 모듈이 한 주기를 정의한다.

한 주기

    1. 대기 중인데 조회수가 아직 없는 윈도우를 찾는다  (spike_candidate ⟕ page_view_hourly)
    2. 그 **시간·그 문서만** 적재한다                  (batch.pageview_hourly_ingest)
    3. 재판정한다                                     (spike.recheck)

🔴 **필터가 대기 목록에서 나온다.** 전수 적재는 시간당 149만 행이라 못 한다(-127 실측).
    조회수를 봐야 하는 건 1단계를 통과해 대기 중인 문서뿐이므로, 받을 양이 대기 수만큼으로
    줄어든다. 이게 이 모듈이 두 CLI 를 그냥 이어 부르는 것보다 나은 유일한 이유다.

⚠️ **아직 안 나온 시간은 안 받는다.** 시간별 덤프는 윈도우 끝 기준 **약 2시간** 뒤에
    공개된다 (실측 125~153분 — 2026-09-18 4구간 · 2026-09-21 5구간). 그 전에 받으면 404 라
    헛다운로드가 된다 — `AVAILABLE_AFTER_HOURS` 만큼 지난 시간만 시도한다.

⚠️ **중복 실행을 막는다.** 두 주기가 겹치면 같은 45 MB 파일을 두 번 받는다. 적재·재판정은
    멱등이라 결과는 같지만 러너가 서비스 EC2(t3 버스트)라 낭비다. PostgreSQL advisory lock
    으로 막는다 — 파일 락과 달리 여러 호스트에서 돌려도 하나만 잡는다.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from batch.pageview_hourly_ingest import ingest_hour, prune_cache

from .candidate_store import CandidateStore
from .recheck import RecheckSummary, recheck

log = logging.getLogger("spike.live_cycle")

#: 윈도우 시작으로부터 이만큼 지나야 그 시간 파일이 나와 있다.
#: 🔴 실측은 윈도우 **끝 기준 125~153분**이다 (2026-09-18 4구간 125~134분 · 2026-09-21
#:    재측정 5구간 127~153분). 시작 기준으로는 약 3~3.5시간이다 — ~~2시간~~ 은 파일명을
#:    윈도우 시작으로 잘못 읽었을 때의 값이었다.
#:    3으로 잡고 아직이면 다음 주기가 다시 본다. 여유를 더 주면 그만큼 확정이 늦어진다.
#:    ⚠️ 최대 153분 구간은 3시간 컷오프에서 404 가 한 번 더 난다 — 실패가 아니라 대기이고
#:    다음 주기가 받는다. 헛다운로드를 0으로 만들려면 4가 필요한데, 그만큼 전부 늦어진다.
AVAILABLE_AFTER_HOURS = 3

#: 한 주기에 받을 시간 파일 수 상한. 밀린 구간을 따라잡되 한 주기가 무한정 길어지지 않게.
DEFAULT_MAX_HOURS = 6

#: advisory lock 키. 이 숫자 자체에 뜻은 없고 다른 잡과 안 겹치기만 하면 된다.
LOCK_KEY = 15_21_609

#: 조회수가 아직 없는 대기. 🔴 LEFT JOIN 이다 — 이미 들어온 것은 recheck 가 처리한다.
SELECT_MISSING_SQL = """
SELECT c.window_start, p.title
  FROM spike_candidate c
  JOIN wiki_page p ON p.id = c.page_id
  LEFT JOIN page_view_hourly v
         ON v.page_id = c.page_id AND v.ts_hour = c.window_start
 WHERE c.source = %s
   AND v.page_id IS NULL
   AND c.window_start <= %s
 ORDER BY c.window_start
"""


@dataclass
class CycleSummary:
    """한 주기 결과. 로그·측정용."""
    hours_due: int = 0
    hours_ingested: int = 0
    hours_pending: int = 0      # 아직 파일이 안 나옴(404)
    titles: int = 0
    cache_pruned: int = 0
    recheck: RecheckSummary = field(default_factory=RecheckSummary)
    seconds: float = 0.0

    def format(self) -> str:
        return (f"시간 {self.hours_ingested}/{self.hours_due} 적재 "
                f"(대기 {self.hours_pending}) · 문서 {self.titles:,} · "
                f"{self.recheck.format()} · 캐시 정리 {self.cache_pruned} · "
                f"{self.seconds:.1f}s")


def missing_views(conn, source: str, *, now: datetime,
                  max_hours: int = DEFAULT_MAX_HOURS) -> list[tuple[str, frozenset[str]]]:
    """조회수가 없는 대기를 (ts_hour, 제목 집합) 으로 묶는다. 오래된 시간부터.

    `now` 기준으로 아직 파일이 안 나왔을 시간은 빼고 준다.
    """
    cutoff = now - timedelta(hours=AVAILABLE_AFTER_HOURS)
    by_hour: dict[str, set[str]] = {}
    with conn.cursor() as cur:
        cur.execute(SELECT_MISSING_SQL, (source, cutoff))
        for window_start, title in cur.fetchall():
            key = window_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:00:00")
            by_hour.setdefault(key, set()).add(title)
    return [(hour, frozenset(titles))
            for hour, titles in sorted(by_hour.items())[:max_hours]]


def run_once(
    conn, *, source: str = "live", cache_dir: Path, out_root: Path,
    wiki: str = "enwiki", now: datetime | None = None,
    max_hours: int = DEFAULT_MAX_HOURS, dry_run: bool = False,
) -> CycleSummary:
    """한 주기. 커넥션은 호출자가 연다 — 루프에서 재사용한다."""
    started = time.monotonic()
    now = now or datetime.now(timezone.utc)
    summary = CycleSummary()

    due = missing_views(conn, source, now=now, max_hours=max_hours)
    summary.hours_due = len(due)
    summary.titles = len({t for _, titles in due for t in titles})

    for ts_hour, titles in due:
        if dry_run:
            log.info("[dry-run] %s 문서 %d건 받을 차례", ts_hour, len(titles))
            continue
        status = ingest_hour(ts_hour, wiki, cache_dir, out_root,
                             titles=titles, shard_records=500_000,
                             dry_run=False, conn=conn)
        if status == "pending":
            # 아직 안 나왔다. 다음 주기가 다시 본다 — 실패가 아니다.
            summary.hours_pending += 1
        else:
            summary.hours_ingested += 1

    summary.recheck = recheck(conn, source=source, dry_run=dry_run)
    if not dry_run:
        # WP-171: 다 쓴 시간별 원본은 매 주기 끝에 정리한다.
        # ingest_hour() 만 직접 부르므로 main() 안의 prune_cache 호출은 이 서비스에
        # 안 걸린다 — 그래서 여기, 실제로 매 주기 도는 자리에 둔다.
        summary.cache_pruned = prune_cache(cache_dir)
    summary.seconds = time.monotonic() - started
    return summary


def try_lock(conn) -> bool:
    """advisory lock 을 잡는다. 이미 다른 주기가 돌고 있으면 False.

    세션 락이라 커넥션이 닫히면 자동으로 풀린다 — 프로세스가 죽어도 락이 안 남는다.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,))
        return bool(cur.fetchone()[0])


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="LIVE 시간 주기 (WP-135)")
    p.add_argument("--dsn", default=os.environ.get("DATABASE_URL", ""))
    p.add_argument("--source", default="live", choices=["live", "replay"])
    p.add_argument("--wiki", default="enwiki")
    p.add_argument("--cache", default=os.environ.get("DUMP_CACHE", "./data/cache"))
    p.add_argument("--out", default=os.environ.get("PAGEVIEW_HOURLY_OUT",
                                                   "./data/pageview-hourly"))
    p.add_argument("--max-hours", type=int, default=DEFAULT_MAX_HOURS,
                   help="한 주기에 받을 시간 파일 수 상한 (밀린 구간 따라잡기)")
    p.add_argument("--loop", action="store_true", help="계속 돈다. 안 주면 한 번만")
    p.add_argument("--interval", type=int, default=900,
                   help="--loop 일 때 주기(초). 기본 15분 — 파일이 매시 한 번 나오지만 "
                        "지연이 125~153분으로 흔들려서 더 자주 본다")
    p.add_argument("--dry-run", action="store_true", help="받을 것만 보여주고 아무것도 안 쓴다")
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_arg_parser().parse_args(argv)
    if not args.dsn:
        print("DSN 이 없다 — --dsn 또는 DATABASE_URL 을 준다", file=sys.stderr)
        return 2

    import psycopg     # DB 경로에서만 필요

    cache_dir = Path(args.cache)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_root = Path(args.out)

    with psycopg.connect(args.dsn) as conn:
        if not try_lock(conn):
            log.warning("다른 주기가 돌고 있다 — 이번 주기는 건너뛴다")
            return 0
        while True:
            try:
                summary = run_once(conn, source=args.source, cache_dir=cache_dir,
                                   out_root=out_root, wiki=args.wiki,
                                   max_hours=args.max_hours, dry_run=args.dry_run)
                log.info("%s%s", "[dry-run] " if args.dry_run else "", summary.format())
            except Exception:
                # 🔴 한 주기 실패가 다음 주기를 막지 않는다. 네트워크·404·DB 오류는
                #    다음에 다시 시도하면 되는 종류다. 로그에는 남긴다.
                conn.rollback()
                log.exception("주기 실패 — 다음 주기에 다시 시도한다")
                if not args.loop:
                    return 1
            if not args.loop:
                return 0
            time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
