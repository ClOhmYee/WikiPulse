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

하루 한 번 (WP-212)

    4. `page_baseline` 을 `page_view_hourly` 이력으로 다시 굴린다  (spike.baseline_from_views)

    `--min-views` 로 하한 적재를 켰을 때만 돈다 — 후보만 적재하면 문서별 이력이 안 쌓여
    기준선이 영영 얇다. 별도 cron 대신 여기 둔 이유는 이 컨테이너가 이미 advisory lock
    을 잡고 도는 유일한 상주 프로세스라서다(수동 `docker run` 을 하나 더 늘리지 않는다, -196).

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

from . import baseline_from_views
from .candidate_store import DEFAULT_EXPIRE_HOURS, CandidateStore
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

#: 기준선 창의 끝을 대기 만료만큼 늦춘다 (WP-212).
#: 🔴 `page_baseline` 은 판본이 하나뿐이고 재판정은 **그 시점 기준선**을 다시 읽는다.
#:    창에 아직 대기 중인 윈도우의 날이 들어가면 급등 자신이 기준선에 섞이는데, EWMA 는
#:    최근 날에 가중치가 가장 커서 배수가 **에러 없이** 깎인다 — 진짜 급등이 폐기된다.
#:    대기는 `first_seen_at`(≈ 윈도우 끝) 부터 `DEFAULT_EXPIRE_HOURS`(36시간) 안에 끝난다.
#:    윈도우 1시간 + 여유 1시간을 더해 그만큼 뺀 날의 **전날**까지만 쓰면, 살아 있는 어떤
#:    대기의 날도 창 밖이다. 최신 2~3일이 빠지지만 반감기가 14일이라 영향이 작다.
BASELINE_LAG_HOURS = DEFAULT_EXPIRE_HOURS + 2


def baseline_as_of(now: datetime):
    """지금 기준선을 굴린다면 창의 끝(포함)이 될 날. 위 `BASELINE_LAG_HOURS` 참고."""
    return (now - timedelta(hours=BASELINE_LAG_HOURS)).date() - timedelta(days=1)


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
    min_views: int | None = None,
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
                             dry_run=False, conn=conn, min_views=min_views)
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


def maybe_refresh_baseline(conn, *, now: datetime, last_as_of, wiki: str = "enwiki"):
    """`baseline_as_of(now)` 가 지난번과 다르면 기준선을 한 번 굴린다. 새 as_of 를 돌려준다.

    하루에 한 번 날이 바뀔 때만 돈다. 프로세스를 재시작하면 `last_as_of` 가 비어 한 번 더
    도는데, upsert 라 멱등이다.

    🔴 실패해도 조회수 적재·재판정을 막지 않는다 — 기준선이 하루 늦는 것은 fallback 이
    받아 주지만, 적재가 멈추면 이력 자체가 끊긴다. 실패하면 as_of 를 갱신하지 않아
    다음 주기가 다시 시도한다.
    """
    as_of = baseline_as_of(now)
    if as_of == last_as_of:
        return last_as_of
    started = time.monotonic()
    try:
        s = baseline_from_views.run(conn, wiki=wiki, as_of=as_of)
    except Exception:
        conn.rollback()
        log.exception("기준선 실패 (as_of=%s) — 다음 주기에 다시 시도한다", as_of)
        return last_as_of
    log.info("기준선 as_of=%s · 관측 %s → %s행 (표본 7일 미만 %s) · 적재 %s · %.1fs",
             as_of, f"{s['observations']:,}", f"{s['rows']:,}", f"{s['thin']:,}",
             f"{s['written']:,}", time.monotonic() - started)
    return as_of


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
    # 🔴 **기본 꺼짐.** 켜면 그 시간 상위 문서를 후보와 무관하게 적재한다
    #    (WP-212) — `page_baseline` 을 만들 이력이 그래야 쌓인다.
    #    ⚠️ 행이 는다: 하한 50 이면 시간당 약 17,400행, 28일 약 1,170만 행 (실측).
    #    ⚠️ 덤프를 한 번 더 읽어 약 10초가 더 걸린다.
    # 기본은 하한 적재와 같이 켜진다 — 하한 없이는 이력이 안 쌓여 굴려도 전부 얇다.
    p.add_argument("--no-baseline", action="store_true",
                   help="하루 한 번 기준선 굴리기를 끈다 (WP-212)")
    p.add_argument("--min-views", type=int,
                   default=(int(os.environ["PAGEVIEW_MIN_VIEWS"])
                            if os.environ.get("PAGEVIEW_MIN_VIEWS") else None),
                   help="이 조회수 이상인 문서는 후보가 아니어도 적재한다 "
                        "(WP-212, 기본 꺼짐)")
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
        refresh_baseline = (args.min_views is not None and not args.no_baseline
                            and not args.dry_run)
        last_as_of = None
        while True:
            try:
                summary = run_once(conn, source=args.source, cache_dir=cache_dir,
                                   out_root=out_root, wiki=args.wiki,
                                   max_hours=args.max_hours, dry_run=args.dry_run,
                                   min_views=args.min_views)
                log.info("%s%s", "[dry-run] " if args.dry_run else "", summary.format())
            except Exception:
                # 🔴 한 주기 실패가 다음 주기를 막지 않는다. 네트워크·404·DB 오류는
                #    다음에 다시 시도하면 되는 종류다. 로그에는 남긴다.
                conn.rollback()
                log.exception("주기 실패 — 다음 주기에 다시 시도한다")
                if not args.loop:
                    return 1
            if refresh_baseline:
                last_as_of = maybe_refresh_baseline(
                    conn, now=datetime.now(timezone.utc), last_as_of=last_as_of,
                    wiki=args.wiki)
            if not args.loop:
                return 0
            time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
