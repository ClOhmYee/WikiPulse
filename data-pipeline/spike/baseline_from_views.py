"""`page_view_hourly` 이력으로 `page_baseline` 을 채운다 (WP-212).

    python -m spike.baseline_from_views --dsn ... --as-of 2026-09-22
    python -m spike.baseline_from_views --dry-run          # 세기만 한다

## 왜 필요한가

운영 `page_baseline` 이 **0행**이다(2026-09-22 실측). `spike(source=live)` 2,852건
전부 `view_baseline IS NULL` 이라, 명세 §3.2 3번의 `z >= 3 AND 2배 이상` 이 **한 번도
발동한 적이 없고** 늘 절대 하한(100회)만으로 판정한다.

기존 적재 경로(`baseline_sink`)의 입력은 Historical Window(-58) 산출물인데, 그건
**편집+조회 합본**이라 편집 덤프 재생이 앞서야 만들어진다. LIVE 는 그 경로가 없다.
여기서는 **이미 매시간 받고 있는 조회수만으로** 같은 수식을 돌린다.

🔴 **수식을 새로 쓰지 않는다.** `baseline_rows.build_rows` 를 그대로 부른다 — 가중치·
반감기·28일 경계·`sample_days` 정의가 Spark 판(`baseline.py`)과 한 곳에서 와야 한다.
두 판이 갈리면 기준선이 **에러 없이** 달라지고 `view_ratio` 가 통째로 틀린다.

## ⚠️ 이 경로가 만드는 기준선의 한계

- **편집 통계가 없다.** `edit_count=0` 으로 넣으므로 `edit_ewma`·`edit_stddev` 는
  의미가 없다. 🔴 `edit_z` 는 진단값이지 관문이 아니라서(`detector` 상수 주석) 판정에는
  영향이 없지만, **로그에 찍히는 `edit_z` 를 이 행 기준으로 해석하면 안 된다.**
- **봇이 섞여 있다.** 시간별 덤프에는 agent 구분이 아예 없다. 다만 그게 이 용도에는
  오히려 맞다 — `Neatsville, Kentucky` 처럼 **매일 9만 회씩 꾸준히 긁히는 문서**는
  기준선에도 그 트래픽이 들어가 배수가 1.2배로 주저앉는다(2026-09-22 실측).
  ⚠️ 반대로 `Roblox` 2026-08-10 같은 **일회성 폭주**는 기준선이 낮아 그대로 통과한다.
  그건 이 경로로 못 푼다 — `-210` 코멘트 §3 참고.
- **이력이 쌓이는 만큼만 좋아진다.** 28일이 차기 전에는 `sample_days < 7` 이라
  `detector` 가 얇은 기준선으로 보고 기존 fallback 을 쓴다. **중간에 깨지는 구간이
  없다** — 그래서 켜 두고 기다리면 된다.

## 🔴 한 번에 다 읽지 않는다

하한 50 이면 28일 창이 약 1,170만 관측이다(-212 실측 17,426행/시간). 파이썬 dict
로 한꺼번에 올리면 수 GB 라, Kafka·Spark 와 같이 사는 16 GB EC2 에서 `live-cycle`
이 OOM 으로 죽는다 — 그러면 조회수 적재까지 같이 멈춘다. 문서 순으로 정렬해 서버
커서로 흘리고 **문서 경계에서만** 끊어 묶음마다 `build_rows` → upsert 한다. 한 문서의
관측은 반드시 한 묶음에 들어가므로 결과는 한꺼번에 돌린 것과 같다.

## ⚠️ 입력이 없는 시간을 0 으로 채우지 않는다

`page_view_hourly` 에 행이 없는 것은 "0회" 와 "안 받았다" 둘 다를 뜻할 수 있다
(WP-199). 0 을 채워 넣으면 표본이 두꺼워 보여 기준선이 실제보다 낮아지고,
그러면 **모든 문서가 급등으로 보인다.** 관측이 있는 슬롯만 센다 — `build_rows` 의
`sample_days` 정의가 이미 그렇다.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone

from .baseline_rows import BASELINE_WINDOW_DAYS, build_rows
from .baseline_sink import load

log = logging.getLogger(__name__)

#: 🔴 `hour_of_day` 는 UTC 다. DB 시간대에 기대면 슬롯이 통째로 밀린다 —
#: `baseline.py` 가 같은 이유로 세션 timeZone 을 UTC 로 고정한다.
SELECT_VIEWS_SQL = """
SELECT p.wiki,
       p.title,
       v.ts_hour,
       EXTRACT(HOUR FROM v.ts_hour AT TIME ZONE 'UTC')::int AS hour_of_day,
       v.views
  FROM page_view_hourly v
  JOIN wiki_page p ON p.id = v.page_id
 WHERE v.ts_hour > %s AND v.ts_hour <= %s
   AND p.wiki = %s
 ORDER BY v.page_id
"""

#: 한 묶음의 문서 수. 문서당 최대 24슬롯 × 28일 = 672 관측이라 5천 문서면 최악 340만 —
#: 실제로는 하한 50 을 매시간 넘는 문서가 드물어 훨씬 작다.
DEFAULT_BATCH_PAGES = 5_000


def window_bounds(as_of: date, window_days: int = BASELINE_WINDOW_DAYS
                  ) -> tuple[datetime, datetime]:
    """[as_of-window_days, as_of] 를 tz-aware UTC 경계로. `build_rows` 와 같은 창이다.

    ⚠️ 끝은 `as_of` 의 **끝**(다음 날 0시)이다. `as_of` 0시로 자르면 그날 하루가
    통째로 빠지는데, 행 수만 줄어서 눈에 안 띈다.
    """
    start = datetime(as_of.year, as_of.month, as_of.day, tzinfo=timezone.utc) \
        - timedelta(days=window_days)
    end = datetime(as_of.year, as_of.month, as_of.day, tzinfo=timezone.utc) \
        + timedelta(days=1)
    return start, end


def read_views(conn, wiki: str, as_of: date, window_days: int = BASELINE_WINDOW_DAYS):
    """`page_view_hourly` 를 `build_rows` 가 받는 형태로 읽는다.

    🔴 `edit_count` 를 **0 으로 준다.** 이 경로에는 편집 정보가 없다 — 모듈 독스트링의
    한계 절 참고. `build_rows` 는 편집·조회를 같은 창에서 따로 집계하므로 조회수
    기준선은 이 값에 영향받지 않는다.
    """
    start, end = window_bounds(as_of, window_days)
    # 🔴 서버 커서다 — 모듈 독스트링 "한 번에 다 읽지 않는다". `withhold` 는 묶음마다
    #    커밋해도 커서가 살아 있게 한다(없으면 첫 커밋에서 커서가 닫힌다).
    with conn.cursor(name="baseline_from_views", withhold=True) as cur:
        cur.itersize = 10_000       # 기본 100 이면 1,170만 행에 왕복 11만 번이다
        cur.execute(SELECT_VIEWS_SQL, (start, end, wiki))
        for wiki_name, title, ts_hour, hour_of_day, views in cur:
            yield {
                "wiki": wiki_name,
                "title": title,
                "window_start": ts_hour,
                "hour_of_day": hour_of_day,
                "edit_count": 0,
                "views": views,
            }


def batches_by_page(observations, batch_pages: int) -> Iterator[list[dict]]:
    """문서 순으로 들어온 관측을 **문서 경계에서만** 끊어 묶는다.

    🔴 입력이 (wiki, title) 로 모여 있어야 한다 — SQL 이 `ORDER BY page_id` 다. 한 문서가
    두 묶음에 걸치면 슬롯 하나가 두 번 계산돼 뒤의 것이 앞의 것을 덮어쓰고, 표본이
    반쪽인 기준선이 **에러 없이** 남는다.
    """
    batch: list[dict] = []
    pages = 0
    current = None
    for obs in observations:
        key = (obs["wiki"], obs["title"])
        if key != current:
            if pages >= batch_pages:
                yield batch
                batch, pages = [], 0
            current = key
            pages += 1
        batch.append(obs)
    if batch:
        yield batch


def run(conn, *, wiki: str = "enwiki", as_of: date | None = None,
        window_days: int = BASELINE_WINDOW_DAYS, dry_run: bool = False,
        batch_pages: int = DEFAULT_BATCH_PAGES) -> dict:
    as_of = as_of or datetime.now(timezone.utc).date()
    summary = {"observations": 0, "rows": 0, "thin": 0, "written": 0}
    for batch in batches_by_page(read_views(conn, wiki, as_of, window_days),
                                 batch_pages):
        rows = build_rows(batch, as_of=as_of, window_days=window_days)
        summary["observations"] += len(batch)
        summary["rows"] += len(rows)
        summary["thin"] += sum(1 for r in rows if r.sample_days < 7)
        if rows and not dry_run:
            summary["written"] += load(conn, rows)      # 묶음마다 커밋
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="page_view_hourly → page_baseline (WP-212)")
    p.add_argument("--dsn", default=os.environ.get("DATABASE_URL", ""))
    p.add_argument("--wiki", default="enwiki")
    p.add_argument("--as-of", help="창의 끝(YYYY-MM-DD). 기본은 오늘(UTC)")
    p.add_argument("--window-days", type=int, default=BASELINE_WINDOW_DAYS)
    p.add_argument("--dry-run", action="store_true", help="세기만 하고 안 쓴다")
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    args = build_arg_parser().parse_args(argv)
    if not args.dsn:
        print("DSN 이 없다 — --dsn 또는 DATABASE_URL 을 준다", file=sys.stderr)
        return 2
    as_of = date.fromisoformat(args.as_of) if args.as_of else None

    import psycopg     # DB 경로에서만 필요

    with psycopg.connect(args.dsn) as conn:
        s = run(conn, wiki=args.wiki, as_of=as_of,
                window_days=args.window_days, dry_run=args.dry_run)
    print(("[dry-run] " if args.dry_run else "")
          + f"관측 {s['observations']:,} → 기준선 {s['rows']:,}행 "
            f"(표본 7일 미만 {s['thin']:,}) · 적재 {s['written']:,}")
    return 0


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(main())
