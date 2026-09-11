"""yfinance 일봉 적재 + 일별 증분 갱신 (WP-64)

    python -m stock.prices              # 전 종목. 없으면 5년, 있으면 마지막 날부터
    python -m stock.prices --period 2y  # 초기 적재 기간 (기본 5y, 기존 행 없는 종목만)
    python -m stock.prices --tickers AAPL,MSFT   # 특정 종목만
    python -m stock.prices --limit 20 --dry-run  # DB 안 건드리고 20종목만 시험

한 코드 경로로 초기 적재와 일별 갱신을 둘 다 한다
    종목마다 stock_price 에 마지막 trade_date 가 있으면 그 날부터(포함), 없으면
    --period 전체를 받는다. 그래서
      - 첫 실행 → 전 종목이 5년치를 받는다 (초기 적재)
      - 매일 cron → 전 종목이 마지막 날 이후만 받는다 (증분 갱신)
      - 중간에 죽고 재실행 → 이미 받은 종목은 마지막 날만, 못 받은 종목은 5년
    summaries·embed 처럼 "아직 안 한 것부터 이어서" 와 같은 원리다. 일 1회
    cron 은 이 스크립트를 인자 없이 돌리면 된다.

왜 raw (auto_adjust=False) 인가
    🔴 조정가(adjusted)는 배당·분할이 새로 생길 때마다 과거 전 구간이 다시
    계산된다. 그러면 5년치를 한 번 받아 두고 매일 하루씩 append 하는 이 구조에서
    초기 적재분과 이후 증분분의 조정 기준이 달라져 같은 날짜 값이 서로 어긋난다.
    raw OHLC 는 해당 날짜 값이 (정정 말고는) 안 변해서 증분 append 와 정합하다.
    분할일에 차트가 튀지만, 이 그래프는 "참고 컨텍스트" 이지 정밀 수익률이 아니다
    (명세 §9). close 는 NOT NULL 이라 결측 행은 버린다.

한도·끊김
    yfinance 는 비공식이라 429·연결 끊김이 잦다. 종목별로 지수 백오프 재시도하고,
    다 실패하면 그 종목만 건너뛰고 나머지를 계속 적재한다 (인수 조건 3).
"""

from __future__ import annotations

import argparse
import datetime as dt
import math
import sys
import time

import psycopg

from . import db

DEFAULT_PERIOD = "5y"
CHUNK = 200        # 이 행 수마다 DB 에 저장. 중간에 죽어도 여기까지는 남는다
MAX_RETRIES = 4    # 종목당 최대 시도 횟수
BASE_DELAY = 2.0   # 지수 백오프 기준(초): 2, 4, 8 ...
THROTTLE = 0.15    # 종목 사이 간격(초). yfinance 를 몰아치지 않는다


def _clean(value) -> float | None:
    """NaN·inf 를 None 으로. psycopg 가 NaN 을 그대로 넣으면 숫자 컬럼이 더럽다."""
    if value is None:
        return None
    f = float(value)
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def rows_from_history(ticker: str, df) -> list[db.PriceRow]:
    """yfinance history DataFrame 을 stock_price 행으로 바꾼다.

    close 가 결측인 날은 버린다 (스키마 NOT NULL). volume 은 없으면 None.
    네트워크 없이 테스트되는 순수 함수다.
    """
    rows: list[db.PriceRow] = []
    for index, row in df.iterrows():
        close = _clean(row.get("Close"))
        if close is None:
            continue
        trade_date = index.date() if hasattr(index, "date") else index
        vol = _clean(row.get("Volume"))  # None·NaN·inf 를 걸러 int(inf) 예외를 막는다
        volume = None if vol is None else int(vol)
        rows.append(
            (
                ticker,
                trade_date,
                _clean(row.get("Open")),
                _clean(row.get("High")),
                _clean(row.get("Low")),
                close,
                volume,
            )
        )
    return rows


def fetch_history(ticker: str, start: dt.date | None, period: str):
    """종목 한 개의 일봉을 받는다. 지수 백오프로 재시도한다.

    start 가 있으면 그 날부터(포함), 없으면 period 전체. 다 실패하면 예외를 올린다 —
    호출부(run)가 잡아서 그 종목만 건너뛴다.
    """
    import yfinance as yf

    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            t = yf.Ticker(ticker)
            if start is not None:
                df = t.history(
                    start=start.isoformat(), auto_adjust=False, actions=False
                )
            else:
                df = t.history(period=period, auto_adjust=False, actions=False)
            # 빈 DataFrame 은 오류가 아니다 — 새 거래일이 없거나 상장 전일 수 있다.
            return df
        except Exception as exc:  # noqa: BLE001 — 429·연결 끊김 등 전부 재시도 대상
            last_err = exc
            if attempt < MAX_RETRIES - 1:
                time.sleep(BASE_DELAY * (2**attempt))
    assert last_err is not None
    raise last_err


def select_targets(
    master: list[str], tickers: list[str] | None, limit: int | None
) -> tuple[list[str], list[str]]:
    """적재 대상과 '마스터에 없어 제외된 티커'를 가른다. 순수 함수(테스트용).

    tickers 가 None 이면 마스터 전체. 지정하면 마스터에 실재하는 것만 남긴다 —
    stock_price.ticker 는 stock 을 FK 참조하므로, 없는 심볼을 넣으면 save 가 FK
    위반으로 run 전체를 중단시킨다. 여기서 미리 걸러 그 경로를 막는다.
    """
    if tickers is None:
        targets = list(master)
        unknown: list[str] = []
    else:
        mset = set(master)
        targets = [t for t in tickers if t in mset]
        unknown = [t for t in tickers if t not in mset]
    if limit is not None:
        targets = targets[:limit]
    return targets, unknown


def run(
    *,
    period: str = DEFAULT_PERIOD,
    tickers: list[str] | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> int:
    with psycopg.connect(db.dsn()) as conn:
        targets, unknown = select_targets(db.all_tickers(conn), tickers, limit)
        if unknown:
            print(
                f"마스터에 없어 제외: {', '.join(unknown)}",
                file=sys.stderr,
            )
        if not targets:
            print(
                "적재할 종목이 없다. 마스터(universe)를 먼저 돌렸는가?",
                file=sys.stderr,
            )
            return 0

        last = db.last_trade_dates(conn)
        print(
            f"주가 적재 대상 {len(targets)}종목 "
            f"(기존 {sum(1 for t in targets if t in last)} · 신규 {sum(1 for t in targets if t not in last)})",
            file=sys.stderr,
        )

        buffer: list[db.PriceRow] = []
        inserted = 0
        ok = empty = failed = empty_new = 0

        for i, ticker in enumerate(targets, 1):
            start = last.get(ticker)  # 있으면 그 날부터(포함), 없으면 None → period 전체
            try:
                df = fetch_history(ticker, start, period)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"  건너뜀 {ticker}: {exc}", file=sys.stderr)
                continue

            rows = rows_from_history(ticker, df)
            if rows:
                ok += 1
                if not dry_run:
                    buffer.extend(rows)
            else:
                empty += 1
                if start is None:
                    # 초기 적재(마지막 trade_date 없음)인데 0행이면 정상적인 "신규
                    # 거래일 없음"이 아니라 스로틀·차단·상장전 의심 신호다. 증분의
                    # 정상 빈 결과와 구분해 센다 (조용한 대량 실패 감지).
                    empty_new += 1
                    print(
                        f"  주의 {ticker}: 초기 적재인데 0행 (차단·상장전 의심)",
                        file=sys.stderr,
                    )

            # 청크가 차면 저장. 마지막 flush 는 루프 밖에서 무조건 한 번 더 한다 —
            # 마지막 종목이 실패로 continue 하거나 빈 결과여도 잔여 버퍼가 남지 않게.
            if not dry_run and len(buffer) >= CHUNK:
                inserted += db.save_prices(conn, buffer)
                buffer.clear()

            if i % 100 == 0 or i == len(targets):
                print(
                    f"  {i}/{len(targets)}  적재 {ok} · 신규데이터없음 {empty} · 실패 {failed} · 행 {inserted}",
                    file=sys.stderr,
                )
            time.sleep(THROTTLE)

        # 루프 후 무조건 최종 flush (P1-A). continue·빈결과로 끝나도 여기서 저장된다.
        if not dry_run and buffer:
            inserted += db.save_prices(conn, buffer)
            buffer.clear()

        if dry_run:
            print(
                f"[dry-run] 저장 안 함. 받은 종목 {ok} · 데이터없음 {empty} · 실패 {failed}",
                file=sys.stderr,
            )
        else:
            print(
                f"주가 적재 완료: 종목 {ok} · 데이터없음 {empty}"
                f"(초기적재 빈결과 {empty_new}) · 실패 {failed} · 행 {inserted}",
                file=sys.stderr,
            )

    # 한 종목도 못 받았는데 대상은 있었다면 프로바이더 전면 장애로 본다 — 종료코드를
    # 1 로 올려 cron 이 성공(0)으로 오인하지 않게 한다 (P1-B, 조용한 대량 실패).
    if not dry_run and ok == 0 and len(targets) > 0:
        print(
            "한 종목도 적재하지 못했다 — 야후 차단·네트워크 장애 의심. 종료코드 1.",
            file=sys.stderr,
        )
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="yfinance 일봉 적재·증분 갱신")
    parser.add_argument(
        "--period",
        default=DEFAULT_PERIOD,
        help=f"기존 행이 없는 종목의 초기 적재 기간 (기본 {DEFAULT_PERIOD})",
    )
    parser.add_argument(
        "--tickers",
        help="쉼표로 구분한 특정 종목만 (예: AAPL,MSFT). 기본은 마스터 전체",
    )
    parser.add_argument("--limit", type=int, help="앞에서 N종목만 (시험용)")
    parser.add_argument(
        "--dry-run", action="store_true", help="DB 에 저장하지 않고 받기만"
    )
    args = parser.parse_args()

    tickers = None
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]

    return run(
        period=args.period,
        tickers=tickers,
        limit=args.limit,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
