"""후보 대기 재판정 — 조회수가 도착한 윈도우를 다시 판정한다 (WP-128).

    python -m spike.recheck --dsn "$DATABASE_URL"
    python -m spike.recheck --source replay --limit 5000
    python -m spike.recheck --dry-run            # 판정만, 저장·삭제 없음

명세 §3.2 3번: "조회수가 아직 도착하지 않았으면 1단계 후보로 보관했다가 도착 시
재판정한다. 조회수가 도착했지만 급등하지 않은 문서는 폐기하고, 통과한 문서만 `spike` 로
저장한다."

흐름

    spike_candidate ⨝ page_view_hourly      조회수가 들어온 대기만
      → detect() 재판정 (기준선은 그 시점 page_baseline 에서 다시 읽는다)
      → 확정: spike 적재 + 대기 삭제
      → 폐기: 대기 삭제 (다시 볼 이유가 없다)
      → 여전히 대기: 남긴다 (조회수 행이 있는데 대기가 나오는 건 계약상 없다 — 아래 ⚠️)
      → 만료: first_seen_at 이 오래된 대기 삭제

🔴 **재판정은 같은 윈도우를 다시 판정하는 것이다.** `detected_at` 은 윈도우 끝이라
(`spike_sink` 계약) 몇 번을 다시 돌려도 `spike` 행이 안 흔들린다. 재실행 멱등성이
여기에 걸려 있다 — `now()` 를 쓰면 같은 급증이 실행할 때마다 다른 시각으로 저장된다.

⚠️ **조회수가 0 이어도 판정은 끝난 것이다.** 0 은 "아무도 안 봤다" 는 관측이고, 절대
하한(100회)에 못 미쳐 폐기된다 — 대기로 되돌리지 않는다.

🔴 ~~"원본 미도착" 은 `page_view_hourly` 에 행이 **없는** 것으로 표현한다~~ →
**그걸로는 구분이 안 된다** (2026-09-22, WP-199). 위키미디어 덤프가 0회 문서를
아예 싣지 않아서, 행이 없는 것이 "미도착" 과 "0회" 둘 다를 뜻했다. 0회 문서가 영영
대기로 남았고 재판정이 가장 오래된 시간부터 도는 구조라 **큐가 맨 앞에서 막혔다** —
0회 500건이 뒤의 53,982건을 굶겼다.

    이제 적재 원장(`page_view_hourly_ingest`, V14)이 "그 시간 원본이 도착했는가" 를
    따로 말한다. 원장에 있으면 도착한 것이고, 그 시간에 행이 없는 문서는 0회다.
    ⚠️ 명세 §3.2 12번의 "장애와 정상 0건 구분" 을 **반대 방향으로** 틀렸던 경우다 —
    정상 0을 미도착으로 오인했다.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

from .baseline_repository import BaselineRepository
from .candidate_store import DEFAULT_EXPIRE_HOURS, CandidateStore
from .runtime import SpikeRuntime
from .spike_sink import SpikeSink

log = logging.getLogger("spike.recheck")

#: 한 번에 재판정할 대기 수. 커밋 단위이기도 하다 — 크게 잡으면 트랜잭션이 길어진다.
DEFAULT_LIMIT = 1_000


@dataclass
class RecheckSummary:
    """한 번의 재판정 결과. 로그·측정용."""
    rechecked: int = 0
    confirmed: int = 0
    rejected: int = 0
    still_pending: int = 0
    expired: int = 0
    remaining: int = 0

    def format(self) -> str:
        return (f"재판정 {self.rechecked:,} / 확정 {self.confirmed:,} / "
                f"폐기 {self.rejected:,} / 여전히 대기 {self.still_pending:,} / "
                f"만료 {self.expired:,} / 남은 대기 {self.remaining:,}")


def recheck(
    conn, *, source: str = "live", limit: int = DEFAULT_LIMIT,
    expire_hours: int = DEFAULT_EXPIRE_HOURS, now: datetime | None = None,
    dry_run: bool = False,
) -> RecheckSummary:
    """조회수가 도착한 대기를 재판정한다. 커밋은 여기서 한다(dry-run 이면 롤백).

    `dry_run` 이면 판정만 하고 아무것도 안 쓴다 — 규모를 먼저 보고 싶을 때.
    """
    store = CandidateStore(conn, source=source)
    sink = None if dry_run else SpikeSink(conn, source=source)
    runtime = SpikeRuntime(BaselineRepository(conn), sink)

    summary = RecheckSummary()
    for candidate in list(store.due(limit)):
        outcome = runtime.process(candidate.window)
        summary.rechecked += 1
        if outcome.decision.is_spike:
            summary.confirmed += 1
        elif outcome.decision.is_pending:
            # 계약상 여기 오면 안 된다 — 조회수 행이 있는데 대기가 났다는 뜻이다.
            # 삼키지 않고 센다. 값이 0 보다 크면 detect() 나 조인 둘 중 하나가 틀렸다.
            summary.still_pending += 1
            log.warning("조회수가 있는데 대기가 나왔다 page=%s window=%s",
                        candidate.page_id, candidate.window.window_start)
        else:
            summary.rejected += 1

        if dry_run:
            continue
        if outcome.decision.is_pending:
            store.bump(candidate.page_id, candidate.window.window_start)
        else:
            # 확정이든 폐기든 대기는 끝났다. 남기면 다음 실행이 또 판정한다.
            store.drop(candidate.page_id, candidate.window.window_start)

    if not dry_run:
        summary.expired = store.expire(now=now or datetime.now(timezone.utc),
                                       hours=expire_hours)
    summary.remaining = store.count()

    if dry_run:
        conn.rollback()
    else:
        conn.commit()
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="후보 대기 재판정 (WP-128)")
    p.add_argument("--dsn", default=os.environ.get("DATABASE_URL", ""),
                   help="PostgreSQL DSN (기본값 DATABASE_URL)")
    p.add_argument("--source", default="live", choices=["live", "replay"],
                   help="재판정할 출처. spike·spike_candidate 키의 일부다")
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    p.add_argument("--expire-hours", type=int, default=DEFAULT_EXPIRE_HOURS,
                   help="이 시간이 지난 대기는 버린다 (조회수가 영영 안 오는 문서)")
    p.add_argument("--dry-run", action="store_true", help="판정만, 저장·삭제 없음")
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_arg_parser().parse_args(argv)
    if not args.dsn:
        print("DSN 이 없다 — --dsn 또는 DATABASE_URL 을 준다", file=sys.stderr)
        return 2

    import psycopg     # DB 경로에서만 필요

    with psycopg.connect(args.dsn) as conn:
        summary = recheck(conn, source=args.source, limit=args.limit,
                          expire_hours=args.expire_hours, dry_run=args.dry_run)
    print(("[dry-run] " if args.dry_run else "") + summary.format())
    # 판정할 게 없는 것은 실패가 아니다 — 조회수가 아직 안 온 정상 상태다.
    return 0


if __name__ == "__main__":
    sys.exit(main())
