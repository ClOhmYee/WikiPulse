"""yfinance longBusinessSummary 수집 (WP-34 앞단)

    python -m stock.summaries

임베딩 입력이 되는 사업 설명이다. 표본 200종목 보유율 100% 실측.
yfinance 는 잘 끊겨서, 아직 설명이 없는 종목부터 이어서 받고 DB 에 바로 쓴다.
"""

from __future__ import annotations

import sys
import time

import psycopg

from . import db

CHUNK = 50  # 이 개수마다 DB 에 저장. 중간에 죽어도 여기까지는 남는다


def run() -> int:
    import yfinance as yf

    with psycopg.connect(db.dsn()) as conn:
        pending = db.tickers_missing_summary(conn)
        if not pending:
            print("설명을 받을 종목이 없다. 마스터(universe)를 먼저 돌렸는가?", file=sys.stderr)
            return 0

        print(f"설명 수집 대상 {len(pending)}종목", file=sys.stderr)
        buffer: list[tuple[str, str]] = []
        got = miss = 0

        for i, ticker in enumerate(pending, 1):
            try:
                summary = yf.Ticker(ticker).info.get("longBusinessSummary")
            except Exception:
                summary = None

            if summary:
                buffer.append((ticker, summary))
                got += 1
            else:
                miss += 1

            if len(buffer) >= CHUNK or i == len(pending):
                if buffer:
                    db.save_summaries(conn, buffer)
                    buffer.clear()
                print(f"  {i}/{len(pending)}  확보 {got} · 없음 {miss}", file=sys.stderr)
            time.sleep(0.05)

    print(f"설명 수집 완료: 확보 {got} · 없음 {miss}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(run())
