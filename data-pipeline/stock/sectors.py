"""yfinance 산업(sector) 수집 (WP-204)

    python -m stock.sectors                          # sector 가 NULL 인 전 종목
    python -m stock.sectors --tickers BA,DAL         # 그중 특정 종목만
    python -m stock.sectors --limit 20 --dry-run     # DB 안 건드리고 20종목만 시험

종목 탐색 목록·상세의 "산업" 칸이다. `stock.sector` 는 V1 부터 있었지만 채우는
코드가 없어 운영 DB 5,396종목이 전부 NULL 이었다.

왜 summaries 를 넓히지 않고 따로 뒀나
    summaries 는 설명이 NULL 인 종목만 돈다. 운영 DB 는 설명이 이미 다 차 있어서,
    거기 sector 를 끼우면 정작 채워야 할 종목이 대상에 안 들어온다. 그래서 sector
    NULL 을 기준으로 "아직 안 한 것부터 이어서" 도는 독립 모듈로 뒀다.

⚠️ yfinance info 에 sector 가 없는 종목이 있다(SPAC·ADR·소형주 등). 그런 종목은
NULL 로 남고 화면에 "산업 미제공"으로 뜨는 게 정상이다 — 몇 개가 채워졌는지는
실행 결과로 기록하고 미리 단정하지 않는다.
"""

from __future__ import annotations

import argparse
import sys
import time

import psycopg

from . import db
from .prices import _yahoo_symbol, select_targets

CHUNK = 50        # 이 개수마다 DB 에 저장. 중간에 죽어도 여기까지는 남는다
THROTTLE = 0.2    # 종목 사이 간격(초). info 는 무거운 호출이라 몰아치지 않는다


def sector_from_info(info) -> str | None:
    """yfinance info 에서 sector 를 꺼낸다. 없거나 빈 문자열이면 None. 순수 함수(테스트용)."""
    if not isinstance(info, dict):
        return None
    value = info.get("sector")
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def run(
    *,
    tickers: list[str] | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    throttle: float = THROTTLE,
) -> int:
    import yfinance as yf

    with psycopg.connect(db.dsn()) as conn:
        missing = db.tickers_missing_sector(conn)
        targets, skipped = select_targets(missing, tickers, limit)
        if skipped:
            master = set(db.all_tickers(conn))
            unknown = [t for t in skipped if t not in master]
            filled = [t for t in skipped if t in master]
            if unknown:
                print(f"마스터에 없어 제외: {', '.join(unknown)}", file=sys.stderr)
            if filled:
                print(f"이미 산업이 있어 건너뜀: {', '.join(filled)}", file=sys.stderr)
        if not targets:
            print("산업을 받을 종목이 없다.", file=sys.stderr)
            return 0

        print(f"산업 수집 대상 {len(targets)}종목", file=sys.stderr)
        buffer: list[tuple[str, str]] = []
        got = miss = failed = 0

        for i, ticker in enumerate(targets, 1):
            try:
                sector = sector_from_info(yf.Ticker(_yahoo_symbol(ticker)).info)
            except Exception as exc:  # noqa: BLE001 — 그 종목만 건너뛴다
                failed += 1
                print(f"  건너뜀 {ticker}: {exc}", file=sys.stderr)
                sector = None
            else:
                if sector:
                    got += 1
                    if not dry_run:
                        buffer.append((ticker, sector))
                else:
                    miss += 1

            if len(buffer) >= CHUNK or i == len(targets):
                if buffer:
                    db.save_sectors(conn, buffer)
                    buffer.clear()
                print(
                    f"  {i}/{len(targets)}  확보 {got} · 없음 {miss} · 실패 {failed}",
                    file=sys.stderr,
                )
            time.sleep(throttle)

    prefix = "[dry-run] 저장 안 함. " if dry_run else ""
    print(f"{prefix}산업 수집 완료: 확보 {got} · 없음 {miss} · 실패 {failed}", file=sys.stderr)

    # 하나도 못 받았는데 실패만 있으면 야후 차단·네트워크 장애다. cron 이 성공으로
    # 오인하지 않게 1 을 낸다. "없음"(info 에 sector 가 없는 종목)은 실패가 아니다.
    if got == 0 and failed > 0:
        print("대량 실패 의심(야후 차단·네트워크 장애). 종료코드 1.", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="yfinance 산업(sector) 수집")
    parser.add_argument(
        "--tickers",
        help="쉼표로 구분한 특정 종목만 (예: BA,DAL). 기본은 sector 가 NULL 인 전 종목",
    )
    parser.add_argument("--limit", type=int, help="앞에서 N종목만 (시험용)")
    parser.add_argument("--dry-run", action="store_true", help="DB 에 저장하지 않고 받기만")
    parser.add_argument(
        "--throttle",
        type=float,
        default=THROTTLE,
        help=f"종목 사이 간격(초). 야후에 차단당하면 올린다 (기본 {THROTTLE})",
    )
    args = parser.parse_args()

    tickers = None
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]

    return run(
        tickers=tickers,
        limit=args.limit,
        dry_run=args.dry_run,
        throttle=args.throttle,
    )


if __name__ == "__main__":
    sys.exit(main())
