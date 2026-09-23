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
# 서킷 브레이커: 연속으로 이만큼 예외가 나면 야후 차단으로 보고 중단한다(prices 와
# 같은 값). yfinance 1.7.0 은 재시도 후에도 429 면 YFRateLimitError 를 던진다.
# "없음"(info 에 sector 가 없음)은 카운트하지 않는다 — 없는 심볼은 예외 없이
# 1키 dict 를 주고(2026-09-23 실측), SPAC·워런트는 연속으로 나올 수 있다.
CIRCUIT_BREAK = 25


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
        # 조회 트랜잭션을 바로 닫는다. 안 닫으면 첫 저장까지(전부 "없음"이거나
        # dry-run 이면 실행 내내) stock 에 락을 쥔 채 idle in transaction 으로 남아,
        # 그 사이 도는 마이그레이션의 ALTER 를 막는다.
        conn.commit()
        if not targets:
            print("산업을 받을 종목이 없다.", file=sys.stderr)
            return 0

        print(f"산업 수집 대상 {len(targets)}종목", file=sys.stderr)
        buffer: list[tuple[str, str]] = []
        got = miss = failed = 0
        consecutive_failed = 0
        tripped = False

        for i, ticker in enumerate(targets, 1):
            try:
                sector = sector_from_info(yf.Ticker(_yahoo_symbol(ticker)).info)
            except Exception as exc:  # noqa: BLE001 — 그 종목만 건너뛴다
                failed += 1
                consecutive_failed += 1
                print(f"  건너뜀 {ticker}: {exc}", file=sys.stderr)
            else:
                if sector:
                    got += 1
                    consecutive_failed = 0
                    if not dry_run:
                        buffer.append((ticker, sector))
                else:
                    miss += 1

            if len(buffer) >= CHUNK:
                db.save_sectors(conn, buffer)
                buffer.clear()
            if i % CHUNK == 0 or i == len(targets):
                print(
                    f"  {i}/{len(targets)}  확보 {got} · 없음 {miss} · 실패 {failed}",
                    file=sys.stderr,
                )
            if consecutive_failed >= CIRCUIT_BREAK:
                tripped = True
                print(
                    f"서킷 브레이커: {consecutive_failed}종목 연속 실패 — 야후 차단 의심. "
                    f"{i}/{len(targets)}에서 중단한다. --throttle 을 올려 나중에 재실행하라.",
                    file=sys.stderr,
                )
                break
            time.sleep(throttle)

        # 최종 저장은 루프 밖에서 무조건 한다 — 브레이커로 break 해도 받은 값이 남게.
        if buffer:
            db.save_sectors(conn, buffer)
            buffer.clear()

    prefix = "[dry-run] 저장 안 함. " if dry_run else ""
    print(f"{prefix}산업 수집 완료: 확보 {got} · 없음 {miss} · 실패 {failed}", file=sys.stderr)

    # ⚠️ 차단이 예외가 아니라 빈 응답으로 오면 전부 "없음"으로 세어진다. 정상일 수도
    # 있어(SPAC 만 남은 경우) 실패로 치지 않고 경고만 한다.
    if got == 0 and failed == 0 and miss > 0:
        print("전부 \"없음\"이다 — 대상이 정말 sector 가 없는 종목인지, 차단인지 확인하라.",
              file=sys.stderr)

    # 브레이커가 걸렸거나, 하나도 못 받았는데 실패가 있으면 야후 차단·네트워크 장애다.
    # cron 이 성공으로 오인하지 않게 1 을 낸다. "없음"은 실패가 아니다.
    if tripped or (got == 0 and failed > 0):
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
